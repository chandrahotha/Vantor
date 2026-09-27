# Task Catalog

For every finding:

1. Reproduce or verify it.
2. Write regression test.
3. Implement canonical fix.
4. Search repository for duplicate patterns.
5. Run full affected tests.
6. Add operational/monitoring evidence where relevant.
7. Update documentation.

This repository-level repetition is intentional: a fix is incomplete if another router or frontend surface still implements the old behavior.
