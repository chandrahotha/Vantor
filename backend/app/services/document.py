"""Document service — validation, hashing, storage (local driver; S3 later).

Rules (production, never faked):
- Extension allowlist + size cap enforced server-side (env MAX_UPLOAD_MB,
  ALLOWED_UPLOAD_EXT). Magic-byte sniff: PDF=%PDF, PNG, JPEG, ZIP (docx/xlsx),
  plain text fallback. Mismatch => quarantine, never silent accept.
- SHA-256 over bytes; storage key `tenant/sha256[0:2]/sha256`; dedupe per tenant
  via unique (tenant, sha256) — re-upload returns the existing row.
- Every read re-verifies the hash; tampered bytes => 409 + quarantine.
- Scanned/no-text PDFs are quarantined with explicit reason downstream (Wave 2);
  Wave 1 stores bytes + metadata honestly (no fake extraction).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
ALLOWED_UPLOAD_EXT = {e.strip().lower() for e in os.getenv("ALLOWED_UPLOAD_EXT", "pdf,docx,xlsx,csv,png,jpg,jpeg,tiff").split(",") if e.strip()}


class DocumentError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_filename(filename: str) -> str:
    name = (filename or "").strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not name or len(name) > 255 or name.startswith(".") or '"' in name or "\x00" in (filename or ""):
        raise DocumentError("DOC_NAME_INVALID", "Invalid filename")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_UPLOAD_EXT:
        raise DocumentError("DOC_TYPE_BLOCKED", f"Extension .{ext} is not allowed")
    return name


def sniff_kind(head: bytes, filename: str) -> str:
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"PK\x03\x04"):
        return "zip"  # docx/xlsx are ZIP containers
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"csv", "txt", "md"}:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            return "unknown"
        return "text"
    if ext in {"tiff", "tif"}:
        return "tiff"
    return "unknown"


def check_size(size: int) -> None:
    if size <= 0:
        raise DocumentError("DOC_EMPTY", "Empty file")
    if size > MAX_UPLOAD_MB * 1024 * 1024:
        raise DocumentError("DOC_TOO_LARGE", f"File exceeds {MAX_UPLOAD_MB} MB")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_root() -> Path:
    root = Path(os.getenv("UPLOAD_DIR", "uploads"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def storage_path(tenant_id: str, digest: str) -> Path:
    safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_")[:64] or "unknown"
    p = storage_root() / safe_tenant / digest[0:2] / digest
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def verify_bytes(path: Path, digest: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest() == digest
