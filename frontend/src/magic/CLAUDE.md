# Magic Module

Frontend for the magic system's Soul Tether, Thread, and CharacterResonance surfaces.
Implemented in Phase 3 of the Soul Tether UI (branch: soul-tether-ui).

## File Inventory

### `types.ts`

TypeScript types for the magic module.

**Re-exports from generated schema** (clean generated shapes):

- `Thread` — `components['schemas']['Thread']`
- `PaginatedThreadList` — paginated Thread list
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

### `api.ts`

REST API client for all soul-tether, thread, and character-resonance endpoints.

**Reads:**

- `getSoulTetherDetail(relationshipId)` — GET `/api/magic/soul-tether/{relationship_id}/`
- `getPendingSineatingOffers()` — GET `/api/magic/soul-tether/sineating/pending/`
- `getPendingStageAdvanceOffers()` — GET `/api/magic/soul-tether/stage-advance/pending/`
- `getPendingSineatingOffer(id)` — GET `/api/magic/soul-tether/sineating/pending/{id}/`
- `getPendingStageAdvanceOffer(id)` — GET `/api/magic/soul-tether/stage-advance/pending/{id}/`
- `getThreads()` — GET `/api/magic/threads/`
- `getCharacterResonances()` — GET `/api/magic/character-resonances/`

**Mutations:**

- `dissolveSoulTether(body)` — POST `/api/magic/soul-tether/dissolve/` → `void`
- `requestSineating(body)` — POST `/api/magic/soul-tether/sineating/request/` → `SineatingOffer`
- `respondToSineating(body)` — POST `/api/magic/soul-tether/sineating/respond/` → `SineatingResult`
- `performRescue(body)` — POST `/api/magic/soul-tether/rescue/` → `RescueOutcome`
- `respondToStageAdvance(body)` — POST `/api/magic/soul-tether/stage-advance/respond/` → `StageAdvanceBonusResult`

### `queries.ts`

React Query hooks with a `magicKeys` query key factory.

**Key factory:**

- `magicKeys.all` → `['magic']`
- `magicKeys.soulTether()` → `[..., 'soul-tether']`
- `magicKeys.soulTetherDetail(id)` → `[..., 'detail', id]`
- `magicKeys.sineatingPending()` → `[..., 'sineating', 'pending']`
- `magicKeys.stageAdvancePending()` → `[..., 'stage-advance', 'pending']`
- `magicKeys.threadList()` → `['magic', 'threads', 'list']`
- `magicKeys.characterResonanceList()` → `['magic', 'character-resonances', 'list']`

**Read hooks:**

- `useSoulTetherDetail(relationshipId)` — disabled when id ≤ 0
- `usePendingSineatingOffers()`
- `usePendingStageAdvanceOffers()`
- `useThreads()`
- `useCharacterResonances()` — replaces the inline hook in ResonancePickerField (TODO follow-up)

**Mutation hooks:**

- `useDissolveSoulTether()` — invalidates `soulTetherDetail(id)` + `soulTether()`
- `useRequestSineating()` — invalidates `sineatingPending()`
- `useRespondToSineating()` — invalidates `sineatingPending()` + `soulTether()`
- `usePerformRescue()` — invalidates `soulTether()`
- `useRespondToStageAdvance()` — invalidates `stageAdvancePending()` + `soulTether()`

### `__tests__/queries.test.tsx`

Unit tests for read and mutation hooks. Uses `vi.fn()` mocks of `api.*` (no msw).

Covers: `useSoulTetherDetail`, `usePendingSineatingOffers`, `usePendingStageAdvanceOffers`,
`useThreads`, `useCharacterResonances`, `useDissolveSoulTether`, `useRespondToSineating`,
and `magicKeys` shape assertions.

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
