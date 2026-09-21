# Issue #3949 evidence

Baseline reviewed: `origin/main` `c40bcef394371ac88093c20626ddc8f85e12dbd6` (post-#3933/#3942).

## Automated evidence

- `pnpm test`: full frontend suite.
- `pnpm typecheck`: TypeScript build check.
- `pnpm build`: production Vite build and static collection.
- Focused tests cover account/context storage isolation, logout cleanup, storage failures, stale action results, attached-action dedupe, navigation protection, websocket transport, and keyboard sidebar resizing.

## Review checklist

- Unscoped legacy preference, anchor, and thread-tab values are ignored.
- Account-scoped drafts, anchors, preferences, and tabs are cleared on logout or account switch.
- REST prose links pending actions atomically where supported; explicit attachments run only after prose acceptance and are guarded by one correlation id.
- `beforeunload` protects tab close; history navigation asks for confirmation.
- One visible `Roleplay` section owns the live web RP feed.
- Sidebar resize exposes a keyboard/pointer control bounded to 240–360px and the layout switches below 960px.

The issue-linked PR is #3954. The evidence document was refreshed with the shared attachment-guard and pose-renderer deduplication review. This evidence does not modify or close #3751.
