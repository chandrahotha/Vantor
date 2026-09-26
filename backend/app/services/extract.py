"""Text extraction — dependency-free, honest about limits (CostPilot pattern).

- PDF: Tj/TJ text-showing operators + FlateDecode streams via zlib/regex stdlib.
  No text layer (scanned) => ExtractedResult(text="", scanned=True) so callers
  quarantine with an explicit reason instead of pretending a read.
- DOCX/XLSX: ZIP containers — document.xml / sharedStrings+sheetData via
  xml.etree + zipfile stdlib.
- CSV/MD/TXT: utf-8 decode (BOM-tolerant).
- Anything else / tampered bytes => DocumentError, never a guess.
"""
from __future__ import annotations

import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass


class ExtractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExtractedResult:
    text: str
    pages: int
    scanned: bool
    kind: str


_TJ_RE = re.compile(rb"\((?:\\.|[^\\()])*\)\s*Tj", re.DOTALL)
_TJ_ARR_RE = re.compile(rb"\[(?:[^\[\]]*)\]\s*TJ", re.DOTALL)
_STR_RE = re.compile(rb"\((?:\\.|[^\\()])*\)")
_FLATE_RE = re.compile(rb"<<(.*?)stream\r?\n", re.DOTALL)
_ESCAPES = {rb"\n": "\n", rb"\r": "\r", rb"\t": "\t", rb"\(": "(", rb"\)": ")", rb"\\": "\\"}


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
    # Page count from the page tree (`/Type /Page`, not `/Pages`), not from
    # Flate stream objects — a page's content, fonts and images are all streams,
    # so counting streams was wildly wrong (a 1-page PDF with 2 font streams
    # reported 2 pages).
    pages = max(len(re.findall(rb"/Type\s*/Page\b(?!s)", data)), 1)

    texts: list[str] = []
    for m in _FLATE_RE.finditer(data):
        header, start = m.group(1), m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        chunk = data[start:end].rstrip(b"\r\n")
        if b"/FlateDecode" in header:
            try:
                chunk = zlib.decompress(chunk)
            except Exception:
                continue
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


def _zip_xml_text(data: bytes, parts: list[str]) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError("DOC_ZIP_INVALID", "Not a valid ZIP container") from exc
    out: list[str] = []
    for part in parts:
        try:
            raw = zf.read(part)
        except KeyError:
            continue
        try:
            root = ET.fromstring(raw)
        except Exception:
            continue
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag in {"t", "v", "inlineStr"} and el.text:
                out.append(el.text.strip())
    return "\n".join(t for t in out if t)


def _xlsx_text(data: bytes) -> str:
    """All sheets, not just sheet1: workbooks with data in later sheets used to
    silently lose it. Shared strings are resolved per cell where possible."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception as exc:
        raise ExtractError("DOC_ZIP_INVALID", "Not a valid XLSX container") from exc
    names = zf.namelist()
    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        try:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for el in root.iter():
                if el.tag.endswith("}t") and el.text:
                    shared.append(el.text)
        except Exception:
            pass
    sheet_names = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
    out: list[str] = []
    for sheet in sheet_names:
        try:
            root = ET.fromstring(zf.read(sheet))
        except Exception:
            continue
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag == "v" and el.text:
                out.append(el.text.strip())
            elif tag == "t" and el.text:
                out.append(el.text.strip())
    if not out and shared:
        out = shared
    return "\n".join(t for t in out if t)


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
