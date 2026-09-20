# Issue #3949 implementation plan

Baseline: branch from `origin/main` at `c40bcef39` (post-#3933/#3942), reviewed issue #3949 and approved stakeholder comment.

## Scope and approach
1. **Storage/account lifecycle**: remove unscoped legacy preference fallback; namespace anchors and thread-tab persistence by stable account/context; add shared account-scoped cleanup for drafts, anchors, preferences, and tab layouts on logout/account change; keep storage failures visible without breaking in-memory play.
2. **Delivery contract**: centralize correlated client request IDs and stale-result guards across REST pose, websocket action, companion, and fallback paths; ensure retries reuse IDs only for unchanged payload/context; prevent concurrent responses from clearing newer drafts.
3. **Attached actions**: keep one request ID through the prose send and defer non-atomic action execution until prose acceptance (or use the existing atomic pose linkage where supported); make action retry/result handling idempotent and never run twice.
4. **Navigation safety**: add native `beforeunload` for non-empty/stranded drafts and an in-app confirmation guard for internal route navigation; surface storage failures and stranded drafts clearly.
5. **Accessible layout**: expose the sidebar separator as a keyboard/pointer/touch resize control (240–360px), preserve the below-960px pane transition, and add tests for zoom/mobile visual viewport/safe-area/focus/scrollbar behavior. Keep one visible authoritative RP/feed block and do not duplicate #3933 reconnect/feed cleanup.
6. **Evidence/tests**: extend focused Vitest tests for all transport/concurrency/storage/logout/responsive/navigation cases; run frontend typecheck, affected tests, build/e2e journey where available; capture exact revision and report blockers.

## Non-goals
- Do not modify or close #3751.
- Do not reimplement #3933/#3942 reconnect/feed cleanup.
- Do not migrate unscoped legacy values; ignore/discard them per approved decision.
