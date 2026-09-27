# Ocr

OCR must be an explicit asynchronous stage. Scanned documents become `processing_ocr`, then `ready` only when text confidence/quality checks pass. Never claim extracted text when no text layer exists.
