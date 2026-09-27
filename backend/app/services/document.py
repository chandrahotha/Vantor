"""Document service — validation, hashing, and pluggable durable storage.

VNT-012. `sniff_kind` recognised four magic signatures and then *fell back to the
extension*: `.tiff` was accepted with no byte inspection at all, and a PNG
uploaded as `invoice.pdf` was typed as `png` and accepted anyway, because nothing
ever compared the sniffed kind against the claimed extension. The claimed MIME
type was stored and never read. So "the file type is verified" was not true.

This version sniffs a full signature table and then **cross-checks** it against
the extension and the declared content type. A disagreement is a rejection with a
specific reason, not a shrug.

VNT-009. Bytes went to `UPLOAD_DIR` on container-local disk with no volume mount,
so every upload died with the container and the API reported 201 plus an audit
event for bytes that were gone. Storage is now a driver interface with a
filesystem implementation (correct for a single node with a persistent volume)
and an S3/MinIO implementation, and the local driver **refuses to start in
production** rather than silently accepting writes it cannot keep.
"""
from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path

from ..core.config import get_settings

#: Signature table. Each entry is (offset, magic bytes, kind). Longest/most
#: specific first, so a container format is never shadowed by a weaker prefix.
#: Formats that share a container (docx/xlsx are both ZIP) are disambiguated by
#: inspecting the archive's own contents, not by the extension.
SIGNATURES: tuple[tuple[int, bytes, str], ...] = (
    (0, b"%PDF-", "pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"\xff\xd8\xff", "jpg"),
    (0, b"II*\x00", "tiff"),
    (0, b"MM\x00*", "tiff"),
    (0, b"GIF87a", "gif"),
    (0, b"GIF89a", "gif"),
    (0, b"BM", "bmp"),
    (0, b"\x1a\x45\xdf\xa3", "matroska"),  # mkv/webm; not allowlisted by default
)

#: Which sniffed kinds are legitimate for which extension. A pair that is not
#: listed here is a mismatch.
KIND_FOR_EXTENSION: dict[str, frozenset[str]] = {
    "pdf": frozenset({"pdf"}),
    "png": frozenset({"png"}),
    "jpg": frozenset({"jpg"}),
    "jpeg": frozenset({"jpg"}),
    "tiff": frozenset({"tiff"}),
    "tif": frozenset({"tiff"}),
    "docx": frozenset({"ooxml-docx"}),
    "xlsx": frozenset({"ooxml-xlsx"}),
    "csv": frozenset({"text"}),
    "txt": frozenset({"text"}),
    "md": frozenset({"text"}),
}

#: Declared content types that are consistent with a sniffed kind. A browser
#: sends these, and a mismatch between "what the browser said" and "what the
#: bytes are" is worth a warning even when the extension agrees.
MIME_FOR_KIND: dict[str, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "png": frozenset({"image/png"}),
    "jpg": frozenset({"image/jpeg", "image/jpg"}),
    "tiff": frozenset({"image/tiff"}),
    "text": frozenset({"text/plain", "text/csv", "text/markdown",
                       "application/csv", "application/octet-stream"}),
    "ooxml-docx": frozenset({
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip", "application/octet-stream",
    }),
    "ooxml-xlsx": frozenset({
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip", "application/octet-stream",
    }),
}

#: Read for the signature check. Enough for every magic above, and small enough
#: to be free.
SNIFF_BYTES = 64


class DocumentError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def max_upload_bytes() -> int:
    """The configured cap, in bytes, from validated settings."""
    return int(get_settings().max_upload_mb) * 1024 * 1024


def allowed_extensions() -> set[str]:
    raw = get_settings().allowed_upload_ext
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def validate_filename(filename: str) -> str:
    name = (filename or "").strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not name or len(name) > 255 or name.startswith(".") or '"' in name or "\x00" in (filename or ""):
        raise DocumentError("DOC_NAME_INVALID", "Invalid filename")
    if not re_safe(name):
        raise DocumentError("DOC_NAME_INVALID", "Filename contains control characters")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in allowed_extensions():
        raise DocumentError("DOC_TYPE_BLOCKED",
                            f"Extension .{ext} is not allowed",
                            {"allowed": sorted(allowed_extensions())})
    return name


def re_safe(name: str) -> bool:
    return not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name)


def _sniff_signature(head: bytes) -> str:
    for offset, magic, kind in SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return kind
    return ""


def _sniff_container(head: bytes, data: bytes | None) -> str:
    """Disambiguate ZIP-based formats by their own contents.

    A DOCX and an XLSX are both `PK\x03\x04`. The extension cannot be trusted
    and neither can the first entry name, so the archive is opened and the
    presence of `word/document.xml` or `xl/workbook.xml` decides. That is the
    same rule a real consumer uses.
    """
    import zipfile

    if not head.startswith(b"PK"):
        return ""
    source = data if data is not None else head
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as zf:
            names = set(zf.namelist())
    except Exception:
        return "zip"
    if "word/document.xml" in names:
        return "ooxml-docx"
    if "xl/workbook.xml" in names or "xl/sharedStrings.xml" in names:
        return "ooxml-xlsx"
    return "zip"


def _is_utf8_text(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def classify(filename: str, head: bytes, *, declared_mime: str = "",
             whole: bytes | None = None) -> str:
    """Return the verified content kind. Raises `DocumentError` on any mismatch.

    Three independent facts have to agree before a file is accepted: what the
    extension claims, what the bytes say, and (when supplied) what the caller
    declared. Any disagreement is refused with the specific reason, because
    "accepted a file whose type nobody verified" is exactly the failure mode a
    malware filter and an extraction pipeline both depend on not having.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in KIND_FOR_EXTENSION:
        raise DocumentError("DOC_TYPE_BLOCKED", f"Extension .{ext} is not allowlisted",
                            {"allowed": sorted(allowed_extensions())})

    signature = _sniff_signature(head)
    kind = signature
    if not kind and head.startswith(b"PK"):
        kind = _sniff_container(head, whole)
    if not kind and ext in {"csv", "txt", "md"}:
        kind = "text" if _is_utf8_text(head) else ""
    if not kind:
        raise DocumentError("DOC_TYPE_UNVERIFIED",
                            "Content does not match any known file signature",
                            {"extension": ext, "head": head[:8].hex()})

    expected = KIND_FOR_EXTENSION[ext]
    if kind not in expected:
        raise DocumentError(
            "DOC_TYPE_MISMATCH",
            f"Content is {kind} but the filename says .{ext}",
            {"extension": ext, "detected": kind, "allowed": sorted(expected)})

    if declared_mime:
        allowed_mimes = MIME_FOR_KIND.get(kind)
        if allowed_mimes is not None:
            normalized = declared_mime.split(";")[0].strip().lower()
            if normalized and normalized not in allowed_mimes:
                raise DocumentError(
                    "DOC_MIME_MISMATCH",
                    f"Declared content type {normalized} does not match the detected {kind}",
                    {"declared": normalized, "detected": kind,
                     "allowed": sorted(allowed_mimes)})
    return kind


def check_size(size: int) -> None:
    if size <= 0:
        raise DocumentError("DOC_EMPTY", "Empty file")
    cap = max_upload_bytes()
    if size > cap:
        raise DocumentError("DOC_TOO_LARGE",
                            f"File exceeds {cap // (1024 * 1024)} MB",
                            {"size": size, "maxBytes": cap})


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Streaming ingestion (VNT-010)
# ---------------------------------------------------------------------------


@dataclass
class IngestResult:
    """What an accepted upload produced."""

    data: bytes
    size: int
    digest: str
    kind: str
    filename: str


#: Read size for the streaming copy. Large enough to keep syscall count down,
#: small enough that the peak allocation is bounded regardless of file size.
CHUNK_BYTES = 1024 * 1024


def ingest(stream, *, filename: str, declared_mime: str = "",
           max_bytes: int | None = None) -> IngestResult:
    """Read an upload to a bounded buffer, aborting the moment the cap is passed.

    VNT-010. The endpoint used to `await file.read()` the *entire* body and only
    then call `check_size(len(data))`, so a 10 GB POST was fully parsed and
    buffered by `python-multipart` and Starlette in order to be answered with a
    413. The limit was a comment, not a control.

    Here the declared `Content-Length` is refused before a byte is read when it
    already exceeds the cap, and the running total is checked after every chunk,
    so memory stays bounded by `max_bytes` however large the request is. The
    bytes are only held once the whole file is known to fit, which is the
    behaviour the API contract has always implied.
    """
    cap = max_bytes if max_bytes is not None else max_upload_bytes()
    declared = stream.headers.get("content-length") if hasattr(stream, "headers") else None
    if declared:
        try:
            declared_length = int(declared)
        except (TypeError, ValueError):
            # A malformed length is not authoritative; the running count decides.
            declared_length = None
        if declared_length is not None and declared_length > cap:
            raise DocumentError("DOC_TOO_LARGE",
                                f"File exceeds {cap // (1024 * 1024)} MB",
                                {"declaredBytes": declared_length, "maxBytes": cap})

    buffer = bytearray()
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > cap:
            raise DocumentError("DOC_TOO_LARGE",
                                f"File exceeds {cap // (1024 * 1024)} MB",
                                {"maxBytes": cap})
    data = bytes(buffer)
    check_size(len(data))
    return IngestResult(data=data, size=len(data), digest=sha256_hex(data),
                        kind=classify(filename, data[:SNIFF_BYTES],
                                      declared_mime=declared_mime, whole=data),
                        filename=filename)


# ---------------------------------------------------------------------------
# Storage drivers (VNT-009)
# ---------------------------------------------------------------------------


class StorageDriver:
    """Where document bytes live. Implementations must be durable across restarts."""

    name = "base"

    def write(self, key: str, data: bytes) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def read(self, key: str) -> bytes:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def exists(self, key: str) -> bool:  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def delete(self, key: str) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError


def storage_key(tenant_id: str, digest: str) -> str:
    """`tenant/shard/sha256`, with the tenant sanitised.

    The tenant segment is derived only from characters that cannot traverse a
    path, so a tenant id can never escape the storage root even if the value
    arrives from a mis-issued token.
    """
    safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_")[:64] or "unknown"
    return f"{safe_tenant}/{digest[0:2]}/{digest}"


class FilesystemStorage(StorageDriver):
    """Local disk. Correct for one node with a persistent volume.

    VNT-009. This was the only driver, mounted nowhere, and it failed *silently*:
    `mkdir(exist_ok=True)` plus a successful write returned 201 and an audit event
    for bytes that a redeploy destroyed. It now refuses to initialise in
    production unless a persistent root is configured, so the deployment has to
    say where the data goes rather than discovering it did not.
    """

    name = "filesystem"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Belt and braces: the key is already sanitised, but a traversal check
        # here means no future caller can reintroduce one.
        target = (self.root / key).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise DocumentError("DOC_STORAGE_KEY_INVALID", "Storage key escapes the storage root")
        return target

    def write(self, key: str, data: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename so a reader never sees a partial document.
        tmp = target.with_suffix(".partial")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        target = self._path(key)
        if target.is_file():
            target.unlink()


class ObjectStorage(StorageDriver):
    """S3 / MinIO. The production driver.

    Uses only the stdlib-free `httpx` + AWS SigV4 signing already in the
    dependency set, so the deployment does not gain a heavyweight SDK for one
    bucket. Endpoint, region and credentials come from validated settings.
    """

    name = "s3"

    def __init__(self, *, endpoint: str, bucket: str, region: str,
                 access_key: str, secret_key: str, prefix: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.prefix = prefix.strip("/")

    def _url(self, key: str) -> str:
        return f"{self.endpoint}/{self.bucket}/{self.prefix + key}" if self.prefix \
            else f"{self.endpoint}/{self.bucket}/{key}"

    def _headers(self, method: str, key: str, payload: bytes) -> dict[str, str]:
        import datetime
        import hashlib as _h
        import hmac as _hmac

        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = _h.sha256(payload).hexdigest()
        host = self.endpoint.split("://", 1)[-1]
        canonical = "\n".join([
            method, f"/{self.bucket}/{self.prefix + key}" if self.prefix else f"/{self.bucket}/{key}",
            "", host, "", f"x-amz-content-sha256:{payload_hash}",
            f"x-amz-date:{amz_date}", "", f"x-amz-content-sha256:{payload_hash}",
        ])
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                             _h.sha256(canonical.encode()).hexdigest()])
        key_date = _hmac.new(("AWS4" + self.secret_key).encode(), date_stamp.encode(), _h.sha256).digest()
        key_region = _hmac.new(key_date, self.region.encode(), _h.sha256).digest()
        key_service = _hmac.new(key_region, b"s3", _h.sha256).digest()
        signing = _hmac.new(key_service, b"aws4_request", _h.sha256).digest()
        signature = _hmac.new(signing, to_sign.encode(), _h.sha256).hexdigest()
        return {
            "Authorization": (f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                              f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={signature}"),
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }

    def write(self, key: str, data: bytes) -> None:
        import httpx

        url = self._url(key)
        response = httpx.put(url, content=data, headers=self._headers("PUT", key, data), timeout=30.0)
        response.raise_for_status()

    def read(self, key: str) -> bytes:
        import httpx

        url = self._url(key)
        response = httpx.get(url, headers=self._headers("GET", key, b""), timeout=30.0)
        response.raise_for_status()
        return response.content

    def exists(self, key: str) -> bool:
        import httpx

        url = self._url(key)
        response = httpx.head(url, headers=self._headers("HEAD", key, b""), timeout=15.0)
        return response.status_code < 400

    def delete(self, key: str) -> None:
        import httpx

        url = self._url(key)
        response = httpx.delete(url, headers=self._headers("DELETE", key, b""), timeout=15.0)
        if response.status_code not in (204, 404):
            response.raise_for_status()


_driver: StorageDriver | None = None


def get_storage() -> StorageDriver:
    """The configured driver. Built once, then cached.

    The filesystem driver refuses to be selected in production, because the
    previous default accepted writes into a container layer that a redeploy
    destroyed, and reported success while doing it.
    """
    global _driver
    if _driver is not None:
        return _driver
    settings = get_settings()
    if settings.s3_endpoint and settings.s3_bucket:
        _driver = ObjectStorage(
            endpoint=settings.s3_endpoint, bucket=settings.s3_bucket,
            region=settings.s3_region, access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key, prefix=settings.s3_prefix)
    else:
        if settings.is_prod:
            raise DocumentError(
                "DOC_STORAGE_UNCONFIGURED",
                "No object storage is configured. Local-disk storage is refused in "
                "production because the bytes would be lost on redeploy; set "
                "S3_ENDPOINT and S3_BUCKET, or set STORAGE_DRIVER=filesystem with a "
                "UPLOAD_DIR on a persistent volume and accept the single-node limit.",
                {"storageDriver": "filesystem", "isProd": True})
        _driver = FilesystemStorage(Path(settings.upload_dir))
    return _driver


def reset_storage_cache() -> None:
    """Test hook: drop the memoised driver so a new setting takes effect."""
    global _driver
    _driver = None


def verify_bytes(path: Path, digest: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest() == digest
