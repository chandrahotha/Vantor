<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# Document Pipeline

Target pipeline: receive -> stream/hash -> object store -> malware/type validation -> quarantine/scan -> extraction -> OCR where configured -> chunk -> embedding -> index -> evidence-ready. Each stage has an immutable status and retry policy.
