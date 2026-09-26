# Golden Test Matrix — PO Price Intelligence Engine

- GT-01: identical comparable PO
- GT-02: currency mismatch
- GT-03: UOM mismatch
- GT-04: missing freight
- GT-05: stale history
- GT-06: outlier above threshold
- GT-07: dismiss with reason
- GT-08: contract-price mismatch

Every golden test stores canonical input JSON, expected output JSON, expected rule/policy version and expected result hash or tolerance where mathematically appropriate.
