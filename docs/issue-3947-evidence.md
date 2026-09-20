# Issue #3947 exact-revision evidence

Reviewed head revision: `8cd7fce46` (`Keep temporary pose reads tab local`).

Core implementation revision: `fc22fa2ad` (`Authorize narrative play read receipts and counts`).

The revision includes:

- Canonical viewer-visible `(interaction_id, timestamp)` authorization for explicit read batches.
- Uniform rejection and transaction-scoped no-partial-write behavior for invalid, stale, hidden, deleted, or timestamp-mismatched pairs.
- Timestamp-aware receipt lookup/counting and account-wide direct unread counts with own-pose exclusion.
- Tab-local ephemeral dwell state, foreground/final-body sentinel tracking, and collapsed-pose exclusion.
- Backend and hook regression tests.

Validation at the reviewed head revision:

- `uv run arx test world.scenes.tests.test_play_views world.scenes.tests.test_interaction_read_receipt world.scenes.tests.test_attention_services` — 56 tests passed.
- `pnpm vitest run src/game/hooks/usePoseReadTracking.test.ts` (from `frontend`) — 10 tests passed.
- `pnpm typecheck` (from `frontend`) — passed.
- Repository pre-commit hooks — passed.

Remaining validation blocker:

- `just test-affected` could not start because `src/.env` is absent (`MAINT_URL` unset). `just test-fast world.scenes` used a stale cached SQLite schema and failed with missing `django_content_type`; focused tests above passed with their own test database.
