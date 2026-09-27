# Pagination Filtering Sorting

All large collections use bounded cursor pagination. Sorting fields must be allowlisted. Search uses indexed strategies, not leading-wildcard scans at scale. Cursor must be tenant-visible and stable across ties.
