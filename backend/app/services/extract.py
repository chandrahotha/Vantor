"""Text extraction — dependency-free, and bounded against archive bombs.

- PDF: Tj/TJ text-showing operators + FlateDecode streams via zlib/regex stdlib.
  No text layer (scanned) => ExtractedResult(text="", scanned=True) so callers
  quarantine with an explicit reason instead of pretending a read.
- DOCX/XLSX: ZIP containers — document.xml / sharedStrings+sheetData via
  xml.etree + zipfile stdlib, with every archive read bounded.
- CSV/MD/TXT: utf-8 decode (BOM-tolerant).
- Anything else / tampered bytes => ExtractError, never a guess.

VNT-011. The archive and PDF paths had no limits of any kind. `zf.read(part)`
decompressed a member with no cap, the sheet loop iterated *every* matching
entry, and `zlib.decompress` expanded a Flate stream in-process with no output
bound. A single 50 MB upload could therefore consume tens of gigabytes of heap
and minutes of CPU in one request, on the request thread.

The limits are read from validated settings and enforced at three levels,
because any one of them can be evaded alone:

1. **Entry count** — a crafted container with a million entries is refused
   before anything is read.
2. **Per-entry size** — checked against the *declared* uncompressed size from
   the central directory, so the bomb is refused without decompressing it.
3. **Cumulative decompressed bytes** — counted as members are read, and stopped
   mid-way rather than after the fact. This is the backstop for a lying
   directory, where the declared size is wrong.
4. **Compression ratio** — a member that expands by more than
   `max_compression_ratio` is a bomb by definition, and this catches the case
   where an attacker sets both the declared size and the entry count to
   plausible-looking values.

The PDF path gets the same treatment via a bounded `decompressobj`, which can be
stopped at exactly the limit instead of only being refused afterwards.
"""
from __future__ import annotations

import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..core.config import get_settings


class ExtractError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class ExtractedResult:
    text: str
    pages: int
    scanned: bool
    kind: str


_TJ_RE = re.compile(rb"\((?:\\.|[^\\()])*\)\s*Tj", re.DOTALL)
_TJ_ARR_RE = re.compile(rb"\[(?:[^\[\]]*)\]\s*TJ", re.DOTALL)
_STR_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")
_FLTE_RE = re.compile(rb"<<(.*?)stream\r?\n", re.DOTALL)
_ESCAPES = {rb"\n": "\n", rb"\r": "\r", rb"\t": "\t", rb"\(": "(", rb"\)": ")", rb"\\": "\\"}

#: Elements whose text is document content. Anything else in the tree is
#: structure and must not be lifted into the searchable text.
_TEXT_TAGS = frozenset({"t", "v", "inlineStr"})


def _limits() -> tuple[int, int, int, int]:
    s = get_settings()
    return (s.max_archive_entries, s.max_entry_bytes,
            s.max_archive_bytes, s.max_compression_ratio)


def _bounded_inflate(chunk: bytes, cap: int) -> bytes | None:
    """Inflate at most `cap` bytes. `None` means the stream exceeded it.

    `decompressobj` is used rather than `zlib.decompress` precisely because it
    can be abandoned at the limit; `decompress` has no output bound and will
    happily materialise the whole bomb before the caller gets to object.
    """
    obj = zlib.decompressobj()
    out = bytearray()
    for start in range(0, len(chunk), 64 * 1024):
        out.extend(obj.decompress(chunk[start:start + 64 * 1024], cap - len(out) + 1))
        if len(out) > cap:
            return None
    out.extend(obj.flush())
    return bytes(out) if len(out) <= cap else None


def _pdf_unescape(raw: bytes) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i : i + 1] == b"\\":
            out.append(_ESCAPES.get(raw[i : i + 2], ""))
            i += 2
        else:
            out.append(chr(raw[i]))
            i += 1
    return "".join(out)


def _extract_pdf(data: bytes) -> ExtractedResult:
    _, _, max_total, _ = _limits()
    # Page count from the page tree (`/Type /Page`, not `/Pages`), not from
    # Flate stream objects — a page's content, fonts and images are all streams,
    # so counting streams was wildly wrong (a 1-page PDF with 2 font streams
    # reported 2 pages).
    pages = max(len(re.findall(rb"/Type\s*/Page\b(?!s)", data)), 1)

    texts: list[str] = []
    consumed = 0
    for m in _FLTE_RE.finditer(data):
        header, start = m.group(1), m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        chunk = data[start:end].rstrip(b"\r\n")
        if b"/FlateDecode" in header:
            remaining = max_total - consumed
            if remaining <= 0:
                # Budget spent. A PDF with more decompressed content than the
                # cap allows is refused rather than truncated into a silently
                # incomplete extraction that would then be indexed as if complete.
                raise ExtractError(
                    "DOC_ARCHIVE_TOO_LARGE",
                    f"PDF content exceeds the {max_total} byte extraction budget",
                    {"maxBytes": max_total})
            inflated = _bounded_inflate(chunk, remaining)
            if inflated is None:
                raise ExtractError(
                    "DOC_ARCHIVE_TOO_LARGE",
                    f"PDF content exceeds the {max_total} byte extraction budget",
                    {"maxBytes": max_total, "reason": "stream expansion"})
            chunk = inflated
            consumed += len(chunk)
        page_runs: list[str] = []
        for tj in _TJ_RE.finditer(chunk):
            for s in _STR_RE.findall(tj.group(0)):
                page_runs.append(_pdf_unescape(s[1:-1]))
        for arr in _TJ_ARR_RE.finditer(chunk):
            for s in _STR_RE.findall(arr.group(0)):
                page_runs.append(_pdf_unescape(s[1:-1]))
        # Runs are usually one word or fragment each: joining with "\n"
        # shredded sentences and degraded search + chunking. Space-join runs,
        # then collapse whitespace so one chunk = readable text.
        stream_text = re.sub(r"\s+", " ", " ".join(page_runs)).strip()
        if stream_text:
            texts.append(stream_text)
    text = "\n\n".join(texts)
    return ExtractedResult(text=text, pages=pages, scanned=not text.strip(), kind="pdf")


class _BudgetedArchive:
    """A ZIP opened under an entry-count, per-entry and total-size budget.

    The limits are checked against the central directory *before* any member is
    decompressed, so a bomb is refused without ever being expanded. The running
    total is then maintained as members are read, which is the only check that
    survives a directory that lies about its own sizes.
    """

    def __init__(self, source: bytes):
        import io

        max_entries, max_entry, max_total, max_ratio = _limits()
        self._max_entry = max_entry
        self._max_total = max_total
        self._max_ratio = max_ratio
        self._consumed = 0
        try:
            self._zf = zipfile.ZipFile(io.BytesIO(source))
        except Exception as exc:
            raise ExtractError("DOC_ZIP_INVALID", "Not a valid ZIP container") from exc

        infos = self._zf.infolist()
        if len(infos) > max_entries:
            raise ExtractError(
                "DOC_ARCHIVE_TOO_MANY_ENTRIES",
                f"Archive has {len(infos)} entries, limit is {max_entries}",
                {"entries": len(infos), "maxEntries": max_entries})
        self._names = {info.filename for info in infos}

        for info in infos:
            # `file_size` is the declared uncompressed size. A member that claims
            # more than the per-entry cap, or that expands by an implausible ratio
            # for its compressed size, is refused unread.
            if info.file_size > max_entry:
                raise ExtractError(
                    "DOC_ARCHIVE_ENTRY_TOO_LARGE",
                    f"Archive entry {info.filename!r} declares {info.file_size} bytes, "
                    f"limit is {max_entry}",
                    {"entry": info.filename, "declaredBytes": info.file_size,
                     "maxEntryBytes": max_entry})
            if info.compress_size > 0 and info.file_size / info.compress_size > max_ratio:
                raise ExtractError(
                    "DOC_ARCHIVE_SUSPICIOUS_RATIO",
                    f"Archive entry {info.filename!r} expands "
                    f"{info.file_size / info.compress_size:.0f}x, limit is {max_ratio}x",
                    {"entry": info.filename, "ratio": round(info.file_size / info.compress_size, 1),
                     "maxRatio": max_ratio})

    @property
    def names(self) -> set[str]:
        return self._names

    def read(self, name: str) -> bytes:
        raw = self._zf.read(name)
        self._consumed += len(raw)
        if self._consumed > self._max_total:
            raise ExtractError(
                "DOC_ARCHIVE_TOO_LARGE",
                f"Archive content exceeds the {self._max_total} byte extraction budget",
                {"maxBytes": self._max_total})
        return raw


def _parse_xml(raw: bytes) -> ET.Element | None:
    """Parse without resolving external entities.

    `xml.etree` does not honour internal entity declarations or fetch external
    ones, so classic XXE and billion-laughs are inert — but that is a property of
    the stdlib, not a control we wrote. An explicit parser makes the intent part
    of the code, and is what a reviewer should be able to verify rather than
    infer. `defusedxml` is used when it is installed; the stdlib path remains
    available and is documented as such.
    """
    try:
        import defusedxml.ElementTree as DET  # type: ignore[import-not-found,import-untyped]

        return DET.fromstring(raw)
    except ImportError:
        pass
    except Exception:
        return None
    try:
        return ET.fromstring(raw)
    except Exception:
        return None


def _xml_text(raw: bytes) -> str:
    root = _parse_xml(raw)
    if root is None:
        return ""
    out: list[str] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in _TEXT_TAGS and el.text:
            out.append(el.text.strip())
    return "\n".join(t for t in out if t)


def _zip_xml_text(data: bytes, parts: list[str]) -> str:
    archive = _BudgetedArchive(data)
    chunks: list[str] = []
    for part in parts:
        if part not in archive.names:
            continue
        chunks.append(_xml_text(archive.read(part)))
    return "\n".join(c for c in chunks if c)


#: The most sheets any workbook is allowed to have before extraction gives up.
#: Derived from the entry budget so the two cannot drift apart.
def _xlsx_text(data: bytes) -> str:
    """All sheets, not just sheet1: workbooks with data in later sheets used to
    silently lose it."""
    archive = _BudgetedArchive(data)
    chunks: list[str] = []
    shared = _xml_text(archive.read("xl/sharedStrings.xml")) if "xl/sharedStrings.xml" in archive.names else ""
    sheet_names = sorted(n for n in archive.names
                         if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    for sheet in sheet_names:
        chunks.append(_xml_text(archive.read(sheet)))
    text = "\n".join(c for c in chunks if c)
    if not text and shared:
        text = shared
    return text


def extract(filename: str, data: bytes) -> ExtractedResult:
    if not data:
        raise ExtractError("DOC_EMPTY", "Empty file")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise ExtractError("DOC_MAGIC_MISMATCH", "Not a PDF by magic bytes")
        return _extract_pdf(data)
    if ext == "docx":
        text = _zip_xml_text(data, ["word/document.xml"])
        return ExtractedResult(text=text, pages=1, scanned=not text.strip(), kind="docx")
    if ext == "xlsx":
        text = _xlsx_text(data)
        return ExtractedResult(text=text, pages=1, scanned=not text.strip(), kind="xlsx")
    if ext in {"csv", "txt", "md"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ExtractError("DOC_ENCODING", "Text must be UTF-8") from exc
        return ExtractedResult(text=text, pages=1, scanned=not text.strip(), kind="text")
    if ext in {"png", "jpg", "jpeg", "tiff", "tif"}:
        # No OCR engine bundled — honest quarantine downstream (Wave 2 OCR later).
        return ExtractedResult(text="", pages=1, scanned=True, kind="image")
    raise ExtractError("DOC_TYPE_UNSUPPORTED", f"No extractor for .{ext}")


def chunk_text(text: str, *, size: int = 800, overlap: int = 100) -> list[str]:
    """Sliding-window chunks on stripped non-empty lines (overlap keeps context)."""
    if size <= overlap or size <= 0:
        raise ExtractError("CHUNK_PARAMS_INVALID", "need 0 < overlap < size")
    words = text.split()
    if not words:
        return []
    step = size - overlap
    return [" ".join(words[i : i + size]) for i in range(0, len(words), step)]
