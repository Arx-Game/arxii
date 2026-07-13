# Crossover - Crossover Invite Management

Frontend for the `world.stories` crossover invite system. Allows GMs to send
crossover invites to other stories' Lead GMs, manage incoming/sent invites, and
view linked stories' stakes summaries on the scene page.

## Key Files

### `api.ts`

REST API client for `/api/crossover-invites/` and `/api/episode-scenes/`.

- **Invite reads:** `listCrossoverInvites(params?)` — paginated list filtered by status/event/story
- **Invite writes:** `createCrossoverInvite(body)`, `acceptCrossoverInvite(id, body)`,
  `declineCrossoverInvite(id, responseNote?)`, `withdrawCrossoverInvite(id)`
- **EpisodeScene reads:** `listEpisodeScenesForScene(sceneId)` — for the linked-stories panel
- **Stakes reads:** `getStakesSummary(beatId)` — per-beat stakes summary from `/api/beats/{id}/stakes-summary/`

### `queries.ts`

React Query hooks with a `crossoverKeys` query key factory.

- **Reads:** `useCrossoverInvites(params?)`, `useEpisodeScenesForScene(sceneId)`
- **Mutations:** `useCreateCrossoverInvite()`, `useAcceptCrossoverInvite()`,
  `useDeclineCrossoverInvite()`, `useWithdrawCrossoverInvite()` — all invalidate
  `['crossover']` on success

### `types.ts`

TypeScript aliases for generated types from `@/generated/api`. Re-exports
`CrossoverInvite`, `CrossoverInviteStatus`, `EpisodeScene`, `Beat`, and
body interfaces for create/accept.

### `components/`

| File                               | Purpose                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------- |
| `CrossoverInviteComposeDialog.tsx` | GM dialog to send a crossover invite (event + story + episode + message pickers) |
| `CrossoverInviteCard.tsx`          | Single invite card with context-dependent actions (accept/decline/withdraw)      |
| `AcceptInviteDialog.tsx`           | Lead GM dialog to accept an invite (episode picker + response note)              |
| `LinkedStoriesPanel.tsx`           | Scene page panel showing linked stories' beats and stakes summaries              |

### `pages/`

| File                     | Route              | Auth           |
| ------------------------ | ------------------ | -------------- |
| `CrossoverInboxPage.tsx` | `/crossover/inbox` | ProtectedRoute |

`CrossoverInboxPage` — shows incoming invites (received — partitioned by
`from_gm_account !== account.id`) and sent invites. The API queryset already
scopes to sent-or-received; the frontend partitions client-side using
`from_gm_account` (added to `CrossoverInviteSerializer` for this purpose,
since the account payload does not include the GMProfile ID).

## Data Flow

- **REST API:** `/api/crossover-invites/` (list/create), `/api/crossover-invites/{id}/accept/`,
  `/api/crossover-invites/{id}/decline/`, `/api/crossover-invites/{id}/withdraw/`
- **EpisodeScene:** `/api/episode-scenes/?scene={id}` (requires `scene` filter field
  added to `EpisodeSceneFilter` for this feature)
- **Stakes:** `/api/beats/{id}/stakes-summary/` (existing endpoint, privacy-filtered)

## Integration Points

- **Backend:** `world.stories` models (`CrossoverInvite`, `EpisodeScene`, `Beat`)
- **StoryDetailPage:** Compose dialog button in the header actions area
- **SceneDetailPage:** `LinkedStoriesPanel` below the header, conditionally rendered
- **Navigation:** "Crossover" link in the Header nav links array
- **Events:** Event picker reuses `fetchEvents` from `@/events/queries`
- **Stories:** Story/episode pickers reuse `listStories`/`listEpisodes` from `@/stories/api`

## Common Gotchas

**`from_gm_account` field is necessary for inbox partitioning.** The account
payload (`/api/user/`) does not include the GMProfile ID (per the project's
AGENTS.md gotcha). Without the `from_gm_account` field on
`CrossoverInviteSerializer`, the frontend cannot distinguish sent from received
invites.

**`EpisodeSceneSerializer` returns strings, not IDs.** The `episode` and `scene`
fields are `StringRelatedField` (display strings). The `episode_id` and `scene_id`
fields (added as `IntegerField(read_only=True)`) provide the numeric IDs needed
to fetch beats via `listBeats({ episode: episodeId })`.

**`EpisodeSceneFilter` did not support filtering by scene.** The `scene` filter
field was added to `EpisodeSceneFilter` for the linked-stories panel to query
`GET /api/episode-scenes/?scene={id}`.

**Linked-stories panel renders nothing for non-crossover scenes.** If no
EpisodeScene rows exist for the scene, the panel returns `null` — no visual
artifact on normal scenes.
