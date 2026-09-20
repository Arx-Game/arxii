# Issue #3947 implementation plan

Stakeholder decisions (issue comment, 2026-09-20):
- Durable receipts are only for retained content; ephemeral read state is session/tab-local.
- `directUnread` is account-wide across all personas; roster badges remain persona-specific.
- Explicit read requests carry canonical `(id, timestamp)` pairs. Each pair is authorized independently against canonical visibility/context and exact stored timestamp.
- Any malformed, stale, hidden, deleted, mismatched, or unauthorized pair rejects the whole batch uniformly and writes no receipts.

Execution plan:
1. Re-read the current `origin/main` reader/read-receipt implementation and existing backend/frontend tests.
2. Add a canonical pair authorization service/queryset seam. Make explicit read POST validation all-or-nothing, timestamp-aware, context-safe, and idempotent. Keep mark-all-before-snapshot using the same visibility seam. Exclude ephemeral poses from durable receipt writes and derive retained counts from exact `(id,timestamp)` receipts.
3. Fix conversation `unread` and account-level `directUnread`, while preserving persona-specific roster attention counts and excluding the viewer's own poses.
4. Update frontend reader contracts and tracking: only mark retained poses after foreground final-body dwell; use tab/session-local state for ephemeral poses; do not mark background/collapsed/offscreen/tall incomplete content.
5. Add focused backend and frontend tests for authorization failures/no partial writes, equal timestamps/idempotency, ephemeral IDs, privacy/context boundaries, own-pose exclusion, gaps/counts, and dwell/tab/final-body behavior. Add actual-app browser coverage where existing harness supports it.
6. Regenerate API schema/types if needed, run focused tests then `just test-affected` and frontend typecheck/tests, record exact revision evidence, commit, push, open issue-linked PR (without changing #3751), and report URL/tests/blockers.

Ambiguities will be escalated before making product decisions.
