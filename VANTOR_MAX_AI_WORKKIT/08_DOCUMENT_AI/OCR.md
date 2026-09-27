<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Ocr

OCR must be an explicit asynchronous stage. Scanned documents become `processing_ocr`, then `ready` only when text confidence/quality checks pass. Never claim extracted text when no text layer exists.
