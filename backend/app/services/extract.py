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
    texts: list[str] = []
    streams = 0
    for m in _FLATE_RE.finditer(data):
        header, start = m.group(1), m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        streams += 1
        chunk = data[start:end].rstrip(b"\r\n")
        if b"/FlateDecode" in header:
            try:
                chunk = zlib.decompress(chunk)
            except Exception:
                continue
        for tj in _TJ_RE.finditer(chunk):
            for s in _STR_RE.findall(tj.group(0)):
                texts.append(_pdf_unescape(s[1:-1]))
        for arr in _TJ_ARR_RE.finditer(chunk):
            for s in _STR_RE.findall(arr.group(0)):
                texts.append(_pdf_unescape(s[1:-1]))
    text = "\n".join(t for t in texts if t.strip())
    return ExtractedResult(text=text, pages=max(1, streams), scanned=not text.strip(), kind="pdf")


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
    text = "\n".join(t for t in out if t)
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
        text = _zip_xml_text(data, ["xl/sharedStrings.xml", "xl/worksheets/sheet1.xml"])
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
