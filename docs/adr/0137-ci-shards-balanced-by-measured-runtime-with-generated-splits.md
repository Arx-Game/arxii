# CI shards balanced by measured runtime; oversized apps split via generated module labels

The backend CI shard matrix (8 shards as of 2026-07-17, up from 6) is balanced by
**estimated runtime** — fresh per-app `def test_` counts × the measured sec/test ratio of
the shard each app last ran in — not by raw test count; count-balancing left equal-count
shards 328s vs 447s apart because seconds-per-test varies ~40% between apps. An app too
big for one shard's budget (world.magic, ~3,050 tests) is **split below the app level by
`tools/split_test_labels.py`**, which re-discovers the app's test modules from disk on
every CI run, deterministically partitions them, and asserts a disjoint complete cover
before emitting anything, so a new test module can never fall between the halves.
The pre-existing `shard-coverage` pre-commit hook (`tools/lint_shard_coverage.py`) was
extended rather than duplicated: it now also requires test-bearing packages without an
`apps.py`, understands split parts, rejects dotted sub-app labels, and counts
ancestor-label coverage — closing the gaps that had quietly dropped `core` and
integration_tests' root-level modules from CI (and double-run `web.admin`'s). Its old
`apps.py`-only discovery was exactly why those went dark. **Rejected: static module
lists in ci.yml** (rot silently — the exact hazard being fixed; unreviewably long);
**rejected: larger paid runners** (spends money on a problem shard count still solves;
revisit if shard count stops scaling). Refresh procedure lives in the matrix comment in
`.github/workflows/ci.yml`.
