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
- `ResonanceBalance` — `{ resonance_id, balance, lifetime_earned, flavor_text }`
- `NearXPLockProspect` — `{ thread_id, boundary_level, xp_cost, dev_points_to_boundary }`
- `ThreadHubSummary` — response for `GET /api/magic/thread-hub-summary/`
- `WeaveThreadRequest` — body for POST /threads/ (weave new thread)
- `PatchThreadRequest` — `{ name?, description? }` for PATCH /threads/{id}/
- `CrossXPLockRequest` — `{ character_sheet_id, resonance }` for cross-xp-lock action
- `CrossXPLockResponse` — alias of `Thread`
- `ImbueRequest` — `{ ritual_id, character_sheet_id, kwargs: { thread_id, amount } }`
- `ImbueResponse` — `{ success, message? }`
- `PullPreviewRequest` — `{ character_sheet_id, resonance_id, tier, thread_ids }`
- `PreviewedEffect` — effect shape in preview response
- `PullPreviewResponse` — `{ resonance_cost, anima_cost, previewed_effects }`
- `ResolvedPullEffect` — effect shape in commit response
- `PullCommitRequest` — `{ character_sheet_id, resonance_id, tier, thread_ids, action_context? }`
- `PullCommitResponse` — `{ resonance_spent, anima_spent, resolved_effects }`
- `AcceptTeachingOfferRequest` — `{ learner_sheet_id? }`
- `AcceptTeachingOfferResponse` — alias of `ThreadWeavingTeachingOffer`
- `RoomBrief` — `{ id, name, location_name, property_ids }` for rooms-by-property

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
- `crossXPLock(threadId, body)` — POST `/api/magic/threads/{id}/cross_xp_lock/` → `Thread`
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
