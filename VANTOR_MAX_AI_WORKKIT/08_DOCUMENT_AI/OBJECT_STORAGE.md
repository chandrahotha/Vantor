# Object Storage

Production object model: tenant namespace + content hash/version. Store object metadata in DB; bytes in S3-compatible storage. Use encryption, lifecycle, retention and integrity verification. Provide reconciliation for missing/orphan objects.
