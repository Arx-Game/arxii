# Issue #3948 implementation plan

Stakeholder decisions (issue #3948 approval comment, 2026-09-20):
- Preserve #3759: 90-day default history with an older-date override, rendered-text search, authorized cursor resolution, context/surrounding cursors, read-only reference mode, live-state restoration, and kind/participant/character/relevant/all-accessible filters.
- Return only viewer-visible titles, participants, locations, and excerpts. Use generic labels for masked identities.
- Treat stale or invalid cursors as explicit reload/retry errors; never silently change pages.
- Leave tabletalk/OOC channels unavailable until #3299.
- Keep the existing Copy/Share deep-link shape unless evidence requires a new permanent URL.

Dependency: this branch starts at PR #3953 (`pr-3953`) so it uses its canonical read receipt API (`(interaction_id, timestamp)` authorization and timestamp-aware unread state) without duplicating or reverting that work. If #3953 is amended or merged, rebase and resolve against its final revision.

Execution plan:
1. Map all history/search/conversation/thread/reference endpoints, serializers, cursor helpers, and frontend query consumers; record current API shapes and boundaries.
2. Add typed cursor/date contracts and signed/versioned cursor payloads bound to viewer, context, filters, and snapshot. Resolve cursors through the same authorization queryset and return explicit stale/reload errors.
3. Implement database-bounded keyset paging: apply visibility, date, kind, participant, character/relevance, and search constraints before slicing; order by `(timestamp, id)` for equal timestamps/concurrent arrivals; enrich only the page.
4. Complete surrounding/context paging and thread/reference earlier/later network paging without exposing inaccessible rows. Preserve target reveal, parent navigation, Copy/Share links, browser Back/deep links, and complete Return-to-live state.
5. Wire every frontend cursor consumer (history, searches, conversations, poses, threads, context, reference) and thread/reference network paging while keeping channels gated on #3299.
6. Add focused backend/frontend tests for query bounds, date/cursor errors, cursor binding, equal timestamps, snapshot/concurrent arrivals, filters, redaction, inaccessible targets, long threads, reference return, and stale reload/retry. Record fixture vs live PostgreSQL/browser evidence with exact revision.
7. Run focused tests, affected tests, frontend typecheck, commit, push, open an issue-linked PR, and report URL/tests/blockers. Do not modify or close #3751.

No additional product behavior will be invented; unresolved choices will be escalated before implementation.
