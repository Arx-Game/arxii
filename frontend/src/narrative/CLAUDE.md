# Narrative - IC Message Delivery UI

Frontend for the `world.narrative` backend app. Inline message rendering in
the main game text feed (light red), a browseable messages section on the
character-sheet page, and the unread counter badge in top-level navigation.
Implemented in Phase 4 Wave 1.

## File Inventory

### `api.ts`

`apiFetch` wrappers grouped by feature:

**Phase 4 — message delivery:**

- `getMyMessages(params?)` — `GET /api/narrative/my-messages/` with optional
  filter params (`acknowledged`, `category`, `related_story`)
- `acknowledgeMessage(deliveryId)` — `POST /api/narrative/deliveries/{id}/acknowledge/`

**Phase 5 — gemit + mute:**

- `getGemits(params?)` — `GET /api/narrative/gemits/` (paginated, `related_era` filter)
- `sendGemit(body)` — `POST /api/narrative/gemits/` (staff only)
- `sendStoryOOC(storyId, body)` — `POST /api/stories/{id}/send-ooc/` (Lead GM/staff)
- `getStoryMutes()` — `GET /api/narrative/story-mutes/` (current user's mute list)
- `muteStory(storyId)` — `POST /api/narrative/story-mutes/` (idempotent)
- `unmuteStory(storyId)` — `DELETE /api/narrative/story-mutes/{id}/`

### `queries.ts`

React Query hooks:

**Phase 4 — message delivery:**

- `narrativeKeys` — query key factory (`all`, `myMessages(params)`)
- `useMyMessages(params?)` — paginated hook with `throwOnError: true`
- `useUnreadNarrativeCount()` — derived hook: calls `getMyMessages({ acknowledged: false })`
  and returns `data?.count ?? 0`; drives the nav badge
- `useAcknowledgeMessage()` — mutation that invalidates the `myMessages` cache
  and updates the unread count

**Phase 5 — gemit + mute:**

- `useGemits(params?)` — paginated gemit history
- `useSendGemit()` — staff broadcast mutation; invalidates `gemits` cache
- `useSendStoryOOC()` — Lead GM/staff OOC notice mutation
- `useStoryMutes()` — current user's mute list
- `useIsStoryMuted(storyId)` — derived hook returning `boolean`
- `useMuteStory()` / `useUnmuteStory()` — toggle mutations; invalidate `storyMutes` cache

### `types.ts`

Re-exports from `@/generated/api`:

- `NarrativeMessage` — full message type
- `NarrativeMessageDelivery` — delivery join type (includes `acknowledged_at`)
- `NarrativeCategory` — TextChoices union: `story` / `atmosphere` / `visions` /
  `happenstance` / `system`
- `MyMessagesResponse` — paginated list shape

### `components/`

**Phase 4 — message delivery:**

| File                       | Purpose                                                                                                             |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `CategoryBadge.tsx`        | Colored badge for narrative category                                                                                |
| `MessageRow.tsx`           | Single message row — body, category badge, timestamp, acknowledge button                                            |
| `MessagesSection.tsx`      | Full messages section embedded in the character-sheet page; category filter tabs, unread-first ordering, pagination |
| `UnreadNarrativeBadge.tsx` | Red badge shown in the top-level nav when there are unread messages; navigates to the messages section on click     |

**Phase 5 — gemit + mute:**

| File                      | Purpose                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------ | -------- | ------------------------------------------------------------- |
| `GemitRenderer.tsx`       | Inline green `                                                                             | G[GEMIT] | n` display block for real-time and historical gemit rendering |
| `GemitHistorySection.tsx` | Paginated gemit history list in the character-sheet page (or standalone dialog)            |
| `SendGemitDialog.tsx`     | Staff-only dialog: compose body + optional era ID + broadcast action                       |
| `SendStoryOOCDialog.tsx`  | Lead GM/staff dialog: compose OOC notice → fans out to all story participants              |
| `MuteStoryToggle.tsx`     | Bell icon button on `StoryDetailPage` — mutes/unmutes real-time narrative push for a story |

### `pages/`

**Phase 4:** The narrative app owned no top-level page. Its UI surfaced through three
integration points:

1. **Inline game text feed** — real-time `|R[NARRATIVE]|n` tagged messages
   rendered in `frontend/src/game/` (the main game view)
2. **Character-sheet messages section** — `MessagesSection` imported by
   `frontend/src/roster/pages/CharacterSheetPage.tsx`
3. **Top-level nav badge** — `UnreadNarrativeBadge` imported by
   `frontend/src/components/Header.tsx`

**Phase 5 — dedicated page:**

| File                   | Route                      | Auth           |
| ---------------------- | -------------------------- | -------------- |
| `MuteSettingsPage.tsx` | `/narrative/mute-settings` | ProtectedRoute |

`MuteSettingsPage` lists all stories the current user has muted, with per-row
Unmute button and a "Manage muted stories" link surfaced in `MessagesSection`.

## Data Flow

- **REST API**: `GET /api/narrative/my-messages/` (paginated, filterable) and
  `POST /api/narrative/deliveries/{id}/acknowledge/`
- **Real-time**: WebSocket session channel delivers `|R[NARRATIVE]|n` tagged
  messages. The main text-feed component already splits and color-tags messages;
  narrative messages are displayed inline in the feed exactly like scene output
  but in light red. A WebSocket event also increments the Redux unread counter
  so the nav badge updates without polling.

## Integration Points

- **Backend Models**: `world.narrative.NarrativeMessage` (immutable after send)
  and `NarrativeMessageDelivery` (join table; `acknowledged_at` nullable)
- **Game text feed** (`frontend/src/game/`): real-time inline rendering of
  `|R[NARRATIVE]|n` color-tagged output from the WebSocket session channel
- **Character sheet** (`frontend/src/roster/pages/CharacterSheetPage.tsx`):
  `MessagesSection` is embedded as a named section after the existing sheet data
- **Navigation** (`frontend/src/components/Header.tsx`): `UnreadNarrativeBadge`
  uses `useUnreadNarrativeCount()` and links to the character-sheet messages anchor

## Common Gotchas

**Unread count is polled, not pushed (except via WS).** `useUnreadNarrativeCount()` hits
`/api/narrative/my-messages/?acknowledged=false` on mount and after each
acknowledge mutation. Real-time increments arrive via the WebSocket session
channel and dispatch to the Redux store. If the WebSocket is not connected
(no puppeted character), the count only updates on page load and after
explicit acknowledge.

**`MessagesSection` is not behind a ProtectedRoute.** The component is
embedded inside the character sheet which already requires authentication;
the component itself does not add another auth guard.

**Backend recipients are character sheets, not accounts.** The narrative
`NarrativeMessageDelivery` is keyed to `recipient_character_sheet`. The
`/api/narrative/my-messages/` endpoint scopes delivery rows to the
current session's puppeted character sheet, not the account. If no
character is puppeted, the endpoint returns an empty list.
