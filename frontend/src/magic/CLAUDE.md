# Magic Module

Frontend for the magic system's Soul Tether, Thread, CharacterResonance,
Thread Hub Summary, Thread mutations, teaching offers, and rooms-by-property surfaces.
Implemented in Phase 3 of the Soul Tether UI (branch: soul-tether-ui);
extended in the thread-spending-ui-design branch (Tasks 8–10).

## File Inventory

### `types.ts`

TypeScript types for the magic module.

**Re-exports from generated schema** (clean generated shapes):

- `Thread` — `components['schemas']['Thread']`
- `PaginatedThreadList` — paginated Thread list
- `Ritual` — `components['schemas']['Ritual']`
- `ThreadWeavingTeachingOffer` — `components['schemas']['ThreadWeavingTeachingOffer']`
- `PaginatedTeachingOfferList` — `components['schemas']['PaginatedThreadWeavingTeachingOfferList']`
- `TargetKind` — `components['schemas']['TargetKindEnum']`
- `CharacterResonance` — `components['schemas']['CharacterResonance']` — identity anchor + currency bucket
- `SineatingPendingOffer` — `components['schemas']['SineatingPendingOffer']` — Sineater inbox row
- `PaginatedSineatingPendingOfferList`
- `PendingStageAdvanceOffer` — `components['schemas']['PendingStageAdvanceOffer']` — stage-advance inbox row
- `PaginatedPendingStageAdvanceOfferList`
- `CrossXPLockRequest` — `{ boundary_level: number }` (generated via `@extend_schema`)
- `CrossXPLockResponse` — `{ thread_id, unlocked_level, xp_spent }` (generated via `@extend_schema`)
- `AcceptTeachingOfferRequest` — `{ learner_sheet_id? }` (generated via `@extend_schema`)
- `AcceptTeachingOfferResponse` — `{ id, unlock_id, xp_spent }` (generated via `@extend_schema`)
- `RoomBrief` — `{ id, name }` (generated via `@extend_schema`; no location_name or property_ids)
- `ResonanceBalance` — `{ resonance_id, balance, lifetime_earned, flavor_text }` (generated)
- `NearXPLockProspect` — `{ thread_id, boundary_level, xp_cost, dev_points_to_boundary }` (generated)
- `ThreadHubSummary` — response for `GET /api/magic/thread-hub-summary/` (generated)
- `PullPreviewRequest` — `components['schemas']['ThreadPullPreviewRequestRequest']` (generated)
- `PreviewedEffect` — `components['schemas']['ResolvedPullEffect']` — preview effect shape
- `PullPreviewResponse` — `components['schemas']['ThreadPullPreviewResponse']` (generated;
  fields: resonance_cost, anima_cost, affordable, resolved_effects, capped_intensity)
- `ResolvedPullEffect` — `components['schemas']['ResolvedPullEffectCommit']` — commit effect shape
- `PullCommitRequest` — `components['schemas']['ThreadPullCommitRequestRequest']` (generated)
- `PullCommitResponse` — `components['schemas']['ThreadPullCommitResponse']` (generated)

**Local types** (the generated schema leaves these as `content?: never`):

- `SoulTetherDetail` — response shape for `GET /api/magic/soul-tether/{relationship_id}/`
  (from `SoulTetherDetailSerializer`; fields: relationship_id, is_soul_tether, soul_tether_role,
  sinner/sineater sheet ids, hollow_current/max, sineater_lifetime_helped, corruption/strain stages)
- `DissolveRequest` — `{ actor_sheet_id, relationship_id }`
- `SineatingRequest` — body for POST sineating/request/ (`actor_sheet_id`, `sineater_sheet_id`,
  `resonance_id`, `max_units`, `scene_id`)
- `SineatingOffer` — response from sineating/request/ (SineatingOfferSerializer shape)
- `SineatingRespondRequest` — `{ sinner_sheet_id, sineater_sheet_id, units_accepted }` (0=decline)
- `SineatingResult` — response from sineating/respond/ (SineatingResultSerializer shape)
- `RescueRequest` — body for POST rescue/ (`actor_sheet_id`, `sinner_sheet_id`, `resonance_id`, `scene_id`)
- `RescueOutcome` — response from rescue/ (RescueOutcomeSerializer shape)
- `StageAdvanceRespondRequest` — `{ sinner_sheet_id, sineater_sheet_id, units_committed }` (0=decline)
- `StageAdvanceBonusResult` — response from stage-advance/respond/ (StageAdvanceBonusResultSerializer shape)
- `WeaveThreadRequest` — body for POST /threads/ (weave new thread)
- `PatchThreadRequest` — `{ name?, description? }` for PATCH /threads/{id}/
- `ImbueRequest` — `{ ritual_id, character_sheet_id, kwargs: { thread_id, amount } }`
- `ImbueResponse` — `{ success, message? }`
- `TetherBond` — `{ relationship_id, bonded_character_sheet_id, bonded_character_name, soul_tether_role }`

### `api.ts`

REST API client for all soul-tether, thread, character-resonance, and thread-spending endpoints.

**Reads:**

- `getSoulTetherDetail(relationshipId)` — GET `/api/magic/soul-tether/{relationship_id}/`
- `getPendingSineatingOffers()` — GET `/api/magic/soul-tether/sineating/pending/`
- `getPendingStageAdvanceOffers()` — GET `/api/magic/soul-tether/stage-advance/pending/`
- `getPendingSineatingOffer(id)` — GET `/api/magic/soul-tether/sineating/pending/{id}/`
- `getPendingStageAdvanceOffer(id)` — GET `/api/magic/soul-tether/stage-advance/pending/{id}/`
- `getThreads()` — GET `/api/magic/threads/`
- `getThread(id)` — GET `/api/magic/threads/{id}/`
- `getCharacterResonances()` — GET `/api/magic/character-resonances/`
- `getThreadHubSummary(characterSheetId?)` — GET `/api/magic/thread-hub-summary/`
- `getTeachingOffers()` — GET `/api/magic/teaching-offers/`
- `getRoomsByProperty(propertyIds)` — GET `/api/magic/rooms-by-property/?property_id=...`

**Thread mutations:**

- `weaveThread(body)` — POST `/api/magic/threads/` → `Thread`
- `patchThreadNarrative(id, body)` — PATCH `/api/magic/threads/{id}/` → `Thread`
- `retireThread(id)` — DELETE `/api/magic/threads/{id}/` → `void`
- `crossXPLock(threadId, body)` — POST `/api/magic/threads/{id}/cross_xp_lock/` → `CrossXPLockResponse` (`{thread_id, unlocked_level, xp_spent}`)
- `imbueThread(body)` — wraps `performRitual` with imbuing ritual id + kwargs
- `imbueThreadAuto(characterSheetId, threadId, amount)` — resolves ritual id then imbues
- `previewPull(body)` — POST `/api/magic/thread-pull-preview/` → `PullPreviewResponse`
- `commitPull(body)` — POST `/api/magic/thread-pull-commit/` → `PullCommitResponse`

**Teaching offer mutations:**

- `acceptTeachingOffer(offerId, body?)` — POST `/api/magic/teaching-offers/{id}/accept/` → `AcceptTeachingOfferResponse`

**Soul Tether mutations:**

- `dissolveSoulTether(body)` — POST `/api/magic/soul-tether/dissolve/` → `void`
- `requestSineating(body)` — POST `/api/magic/soul-tether/sineating/request/` → `SineatingOffer`
- `respondToSineating(body)` — POST `/api/magic/soul-tether/sineating/respond/` → `SineatingResult`
- `performRescue(body)` — POST `/api/magic/soul-tether/rescue/` → `RescueOutcome`
- `respondToStageAdvance(body)` — POST `/api/magic/soul-tether/stage-advance/respond/` → `StageAdvanceBonusResult`

**Test helper:**

- `__resetImbuingRitualIdCacheForTests()` — resets the imbuing-ritual-id module cache;
  call in `beforeEach` for any test that exercises imbue logic

### `queries.ts`

React Query hooks with a `magicKeys` query key factory.

**Key factory:**

- `magicKeys.all` → `['magic']`
- `magicKeys.soulTether()` → `[..., 'soul-tether']`
- `magicKeys.soulTetherDetail(id)` → `[..., 'detail', id]`
- `magicKeys.sineatingPending()` → `[..., 'sineating', 'pending']`
- `magicKeys.stageAdvancePending()` → `[..., 'stage-advance', 'pending']`
- `magicKeys.threadList()` → `['magic', 'threads', 'list']`
- `magicKeys.thread(id)` → `['magic', 'threads', id]`
- `magicKeys.threadHubSummary()` → `['magic', 'thread-hub-summary']`
- `magicKeys.characterResonanceList()` → `['magic', 'character-resonances', 'list']`
- `magicKeys.teachingOffers()` → `['magic', 'teaching-offers', 'list']`

**Read hooks:**

- `useSoulTetherDetail(relationshipId)` — disabled when id ≤ 0
- `usePendingSineatingOffers()`
- `usePendingStageAdvanceOffers()`
- `useThreads()`
- `useThread(id)` — disabled when id ≤ 0
- `useCharacterResonances()` — replaces the inline hook in ResonancePickerField (TODO follow-up)
- `useThreadHubSummary(characterSheetId?)` — optional alt-guard param
- `useTeachingOffers()`

**Mutation hooks:**

- `useDissolveSoulTether()` — invalidates `soulTetherDetail(id)` + `soulTether()`
- `useRequestSineating()` — invalidates `sineatingPending()`
- `useRespondToSineating()` — invalidates `sineatingPending()` + `soulTether()`
- `usePerformRescue()` — invalidates `soulTether()`
- `useRespondToStageAdvance()` — invalidates `stageAdvancePending()` + `soulTether()`
- `useWeaveThread()` — invalidates `threadList`, `threadHubSummary`
- `usePatchThreadNarrative(id)` — invalidates `thread(id)`, `threadList`
- `useRetireThread()` — invalidates `threadList`, `threadHubSummary`
- `useImbueThread()` — takes `{ characterSheetId, threadId, amount }`;
  invalidates `thread(id)`, `threadHubSummary`, `characterResonanceList`
- `useCrossXPLock()` — takes `{ threadId, body }`;
  invalidates `thread(id)`, `threadHubSummary`
- `useCommitPull()` — invalidates `threadHubSummary`, `characterResonanceList`
- `useAcceptTeachingOffer()` — takes `{ offerId, body? }`;
  invalidates `teachingOffers`, `threadHubSummary`

**Note:** `previewPull` is NOT a hook — it's a plain `api.previewPull(body)` async function.
Pull previews are user-driven and ephemeral; components should debounce calls manually.

### `__tests__/queries.test.tsx`

Unit tests for read and mutation hooks. Uses `vi.fn()` mocks of `api.*` (no msw).

Covers: `useSoulTetherDetail`, `usePendingSineatingOffers`, `usePendingStageAdvanceOffers`,
`useThreads`, `useCharacterResonances`, `useDissolveSoulTether`, `useRespondToSineating`,
`useThreadHubSummary`, `useThread`, `useTeachingOffers`, `useWeaveThread`,
`usePatchThreadNarrative`, `useRetireThread`, `useImbueThread`, `useCrossXPLock`,
`useCommitPull`, `useAcceptTeachingOffer`, and `magicKeys` shape assertions.

The imbue tests call `__resetImbuingRitualIdCacheForTests()` in `beforeEach`.

### `pages/ThreadHubPage.tsx`

Thread hub landing page at `/threads`. Shows `ThreadHubSummary` (prospect badges, resonance
balances, near-XP-lock prospects), a grid of `ThreadCard` items, and a "Weave Thread" button
that opens `WeaveThreadWizard`. Links to `/threads/:id` and `/threads/teaching`.

### `pages/ThreadDetailPage.tsx`

Thread detail page at `/threads/:id`. Renders the full thread record with `ImbuePanel`,
`XPLockBoundaryPanel`, `PullEffectPreview`, `ThreadRenameDialog`, and `ThreadRetireDialog`.

### `pages/WeavingTeachingOffersPage.tsx`

Teaching-offer inbox at `/threads/teaching`. Lists incoming `ThreadWeavingTeachingOffer`
rows via `TeachingOfferCard`; each card opens `AcceptOfferDialog` to pay XP and accept.

### `components/threads/ResonanceBalanceCard.tsx`

HoverCard showing a single resonance balance (current balance + lifetime earned + flavor text).
Used in `ThreadHubPage` to render the balance grid.

### `components/threads/ThreadStateBadge.tsx`

Small badge that maps a thread's `state` field to a colored label (Active, Dormant, Retired, etc.).

### `components/threads/ThreadCard.tsx`

Card for a single thread in the hub grid. Shows name, state badge, resonance, XP-lock level,
and a link to the detail page.

### `components/threads/ImbuePanel.tsx`

Panel in `ThreadDetailPage` for spending resonance to imbue a thread. Calls `useImbueThread`.

### `components/threads/XPLockBoundaryPanel.tsx`

Panel in `ThreadDetailPage` for crossing an XP-lock boundary. Shows cost/prospect info
and calls `useCrossXPLock`.

### `components/threads/PullEffectPreview.tsx`

Panel in `ThreadDetailPage` for previewing and committing a thread pull. Calls `api.previewPull`
then `useCommitPull`. Shows resolved effects and affordability.

### `components/threads/ThreadRenameDialog.tsx`

Dialog for renaming a thread (patching `name` + `description`). Calls `usePatchThreadNarrative`.

### `components/threads/ThreadRetireDialog.tsx`

Confirmation dialog for retiring a thread. Calls `useRetireThread`.

### `components/threads/WeaveThreadWizard.tsx`

Multi-step wizard for weaving a new thread. Step 1: select `TargetKind` (FACET and
COVENANT_ROLE fully enabled; TRAIT/TECHNIQUE/ROOM/Relationship stubbed "coming soon").
Step 2: select anchor. Step 3: name + description + confirm. Calls `useWeaveThread`.

### `components/threads/TeachingOfferCard.tsx`

Card for a single `ThreadWeavingTeachingOffer` in `WeavingTeachingOffersPage`. Shows offer
details and opens `AcceptOfferDialog`. Teacher is shown via the anonymity-respecting
`RosterTenure.display_name` (e.g. "2nd player of Ariel") surfaced as
`teacher_display_name` on the serializer.

### `components/threads/AcceptOfferDialog.tsx`

Dialog for accepting a teaching offer. Shows XP cost and calls `useAcceptTeachingOffer`.

### `components/ThreadList.tsx` (legacy)

Early thread list component — renders a flat list of threads filtered by optional `targetKind`.
No longer imported by any page or component; retained for its unit test coverage. Candidate
for removal once the hub/detail pages are confirmed stable.

## Data Flow

- **GET soul-tether detail:** `useSoulTetherDetail(relationshipId)` → `SoulTetherDetail`
  — shows Hollow state, corruption stage, lifetime helped
- **Sineating request:** Sinner calls `useRequestSineating` → Sineater sees offer in
  `usePendingSineatingOffers` → Sineater calls `useRespondToSineating`
- **Stage-advance prompt:** Server fires the prompt → Sineater sees it in
  `usePendingStageAdvanceOffers` → Sineater calls `useRespondToStageAdvance`
- **Rescue:** Sineater calls `usePerformRescue` (stage 3+ required server-side)
- **Dissolve:** Either party calls `useDissolveSoulTether`

## Integration Points

- **NOT here:** Soul Tether _formation_ (acceptance) goes through
  `POST /api/magic/rituals/perform/` via `usePerformRitual` in the rituals module.
- **Backend:** `world.magic` — services/soul_tether.py, views.py, urls.py
- **Serializer mapping:**
  - `SoulTetherDetailSerializer` → `SoulTetherDetail` (local type, not in generated schema)
  - `SineatingOfferSerializer` → `SineatingOffer` (local type)
  - `SineatingResultSerializer` → `SineatingResult` (local type)
  - `RescueOutcomeSerializer` → `RescueOutcome` (local type)
  - `StageAdvanceBonusResultSerializer` → `StageAdvanceBonusResult` (local type)
  - `SineatingPendingOfferSerializer` → `SineatingPendingOffer` (generated schema)
  - `PendingStageAdvanceOfferSerializer` → `PendingStageAdvanceOffer` (generated schema)
- **Consumers (Phase 3 Tasks 3.2–3.7):** SoulTetherPanel, SineatingInbox,
  SineatingRespondDialog, StageAdvanceInbox, RescueDialog, DissolveDialog

## Common Gotchas

**`SoulTetherDetail` is a local type, NOT in the generated schema.**
The generated `magic_soul_tether_retrieve` operation has `content?: never` because
`SoulTetherDetailSerializer` derives from `serializers.Serializer`, not a ModelSerializer,
and drf-spectacular cannot infer the response shape. The fields are taken directly from
`SoulTetherDetailSerializer` field declarations.

**`soul_tether_role` is a string, not a union.**
The `SoulTetherRole` TextChoices (`ABYSSAL` / `CELESTIAL`) are not exposed in the generated
schema. Use string comparison rather than importing a local enum.

**Dissolve returns `void`.**
`POST /api/magic/soul-tether/dissolve/` returns HTTP 200 with no body. The `api.dissolveSoulTether`
function returns `Promise<void>`. The mutation hook `useDissolveSoulTether` has no `data`.

**`units_accepted=0` and `units_committed=0` are declines.**
Both `useRespondToSineating` and `useRespondToStageAdvance` accept 0 as a valid input — it
signals decline (not an error). The returned result will have `declined: true`.

**`CharacterResonance[]` (not paginated).**
The `GET /api/magic/character-resonances/` response is a bare array, not a paginated object.
`useCharacterResonances().data` is `CharacterResonance[]`, not `PaginatedList`.

**Path param is `relationship_id`, not a soul-tether id.**
`useSoulTetherDetail(relationshipId)` takes a `CharacterRelationship` PK. Either the Sinner's
or the Sineater's directional row PK is accepted by the backend.
