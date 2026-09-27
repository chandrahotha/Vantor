<!-- vantor-brain-link -->
> 🧠 **Vantor Brain:** [BRAIN.md](../../docs/BRAIN.md) · [Docs index](../../docs/README.md)

# RFQ/Quote/Award State Machine

RFQ Draft -> Sent -> Response -> Evaluated -> Awarded/Closed. Quote Submitted -> Evaluated -> Awarded OR Rejected. Award must be unique and atomic.

Every transition requires an explicit command, preconditions, actor authority, audit event and concurrency rule.
