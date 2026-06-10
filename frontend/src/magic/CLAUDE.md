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

**Alteration resolution re-exports** (generated schema):

- `PendingAlteration` — `components['schemas']['PendingAlteration']` — open scar waiting for player resolution; carries `character_id` / `character_name` fields for per-character attribution
- `PaginatedPendingAlterationList` — paginated list wrapper returned by the list endpoint
- `AlterationResolveResponse` — `components['schemas']['AlterationResolutionResponse']` — `{ status, event_id }`
- `AlterationLibraryEntry` — `components['schemas']['LibraryEntry']` — staff-curated library entry returned by the `{id}/library/` action (bare array, not paginated)

**Alteration resolution local types** (not inferrable from generated schema):

- `AlterationResolvePayload` — union of `AlterationLibraryPickPayload` (`{ library_template_id: number }`) and `AlterationScratchPayload`. The generated `AlterationResolutionRequest` marks default-valued magnitude fields as required, so it is unusable for library picks; always use this union type.
- `AlterationScratchPayload` — scratch authoring body: `name`, `player_description`, `observer_description`, `weakness_damage_type_id` (number|null), `weakness_magnitude`, `resonance_bonus_magnitude`, `social_reactivity_magnitude`, `is_visible_at_rest`. `parent_template_id` is deliberately omitted (staff-only lineage concept).
- `AlterationTierCaps` — `{ social_cap, weakness_cap, resonance_cap, visibility_required }` (source of truth: `ALTERATION_TIER_CAPS` in `src/world/magic/constants.py`)
- `MIN_ALTERATION_DESCRIPTION_LENGTH` — module-level constant (40)

**Helper:**

- `getTierCaps(pending)` — returns the typed `AlterationTierCaps` for a `PendingAlteration`. `tier_caps` is a `SerializerMethodField` → generated as an untyped dict; always use this helper instead of casting the raw field.

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

REST API client for all soul-tether, thread, character-resonance, thread-spending, and alteration-resolution endpoints.

**Alteration resolution reads:**

- `getPendingAlterations()` — GET `/api/magic/pending-alterations/` → `PaginatedPendingAlterationList` (server defaults to status=OPEN rows)
- `getAlterationLibrary(pendingId)` — GET `/api/magic/pending-alterations/{id}/library/` → `AlterationLibraryEntry[]` (bare array — `pagination_class=None` on this action)

**Alteration resolution mutations:**

- `resolveAlteration(pendingId, payload)` — POST `/api/magic/pending-alterations/{id}/resolve/` → `AlterationResolveResponse` (`{ status: 'resolved', event_id }`). `payload` is `AlterationResolvePayload` (not the generated `AlterationResolutionRequest`).

**Error class:**

- `AlterationResolveError` — typed error thrown when the resolve endpoint returns 400. Carries `.fieldErrors` (`Record<string, string[]>`, `detail` excluded) and `.message` (first `non_field_errors` entry, or the `detail` string, or a generic fallback). The backend validator raises everything as `non_field_errors`, so the dialog banner is the dominant error path; per-field keys (e.g. `name`) render under their inputs.

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
- `magicKeys.pendingAlterations()` → `['magic', 'pending-alterations']`
- `magicKeys.alterationLibrary(id)` → `['magic', 'pending-alterations', 'library', id]`
- `magicKeys.soulTether()` → `[..., 'soul-tether']`
- `magicKeys.soulTetherDetail(id)` → `[..., 'detail', id]`
- `magicKeys.sineatingPending()` → `[..., 'sineating', 'pending']`
- `magicKeys.stageAdvancePending()` → `[..., 'stage-advance', 'pending']`
- `magicKeys.threadList()` → `['magic', 'threads', 'list']`
- `magicKeys.thread(id)` → `['magic', 'threads', id]`
- `magicKeys.threadHubSummary()` → `['magic', 'thread-hub-summary']`
- `magicKeys.characterResonanceList()` → `['magic', 'character-resonances', 'list']`
- `magicKeys.teachingOffers()` → `['magic', 'teaching-offers', 'list']`

**Alteration read hooks:**

- `usePendingAlterations()` — auth-guarded (`enabled: !!account`; no fetch while logged out); polls every 30 s via `refetchInterval`. `throwOnError` is deliberately NOT set — the hook backs the site-wide banner, which must degrade to rendering nothing on fetch errors instead of crashing every page through the error boundary.
- `useAlterationLibrary(pendingId)` — takes `number | null` (null = dialog closed → disabled); fetches tier-matched `AlterationLibraryEntry[]` for the dialog's Library tab.

**Alteration mutation hooks:**

- `useResolveAlteration()` — calls `POST {id}/resolve/`; invalidates `pendingAlterations()` on success.

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

### `__tests__/alterationQueries.test.tsx`

8 unit tests covering `usePendingAlterations` (auth-guard, 30 s poll, returns undefined when logged out), `useAlterationLibrary` (enabled/disabled by pendingId), and `useResolveAlteration` (mutation dispatches, cache invalidation).

### `components/alterations/AlterationResolveDialog.tsx`

Two-tab dialog (Library / Author) for resolving a single `PendingAlteration`. Library tab renders affinity-ordered `AlterationLibraryEntry` cards from `useAlterationLibrary`; selecting a card and confirming ("Accept this mark") submits `{ library_template_id }` via `useResolveAlteration`. Author tab renders `AlterationAuthorForm`. Both `TabsContent`s use `forceMount` (inactive panel hidden via CSS) so authored prose survives tab switches. On server error, a `role="alert"` banner renders the `AlterationResolveError` message plus any orphaned field errors (keys the author form doesn't render).

### `components/alterations/AlterationAuthorForm.tsx`

Controlled form for the scratch-authoring resolution path. Magnitude fields are `<select>` elements constrained to `0..tierCap` (cap read from `getTierCaps(tier)`). Damage type is a required `<select>` gated to visible only when `weakness_magnitude > 0`. At tiers 4–5, `is_visible` is forced to `true` and the toggle is hidden. All description fields display a 40-character counter; `MIN_ALTERATION_DESCRIPTION_LENGTH` is the minimum enforced client-side.

### `__tests__/AlterationResolveDialog.test.tsx`

10 E2E-ish tests (real hooks + dialog, mocked `../api` transport). Covers: exact library payload (`{ library_template_id }`), server `non_field_errors` in the banner, empty-library pointer, accept-disabled-until-selection, exact 8-key scratch payload, 40-char description gating, weakness>0-requires-damage-type, magnitude options capped at tier cap, tier-4 forced visibility, and tab-switch prose persistence.

### `components/alterations/PendingAlterationBanner.tsx`

Site-wide alert bar rendered in `Layout` directly below `Header` (all viewport modes, including `/game`). Consumes `usePendingAlterations()` (30 s poll, auth-guarded). Not dismissable — the scar gates XP spending, so it stays until resolved. Singular copy names the character + tier ("Velenosa carries an unresolved Touched Mage Scar. That character's XP spending is blocked…"); 2+ uses a count form. Links to `/magic/alterations`. Renders nothing when clean, loading, errored, or logged out.

### `__tests__/PendingAlterationBanner.test.tsx`

4 tests covering: hidden when the list is empty, visible with character-naming copy + `/magic/alterations` link for one pending, count form for 2+, and no fetch at all when logged out.

### `pages/AlterationResolutionPage.tsx`

Lazy `ProtectedRoute` at `/magic/alterations`. Lists every OPEN `PendingAlteration` for the account. Renders an explicit error state (distinct from the empty-list state) when the query fails. Each row opens `AlterationResolveDialog`. After all alterations are resolved the page shows an empty-state message rather than redirecting.

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

### `XpKudosPage.alterationGate.test.tsx` (in `src/progression/`)

3 tests for the `AlterationGateAlert` rendered within `XpKudosPage`: alert is shown when `usePendingAlterations` returns open alterations, names the affected character(s), and is absent when the list is empty.

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

## Shared Hooks Outside This Module

**`useDamageTypes` lives in `frontend/src/conditions/queries.ts`.**
Consolidated there from an inline query that previously lived in `TechniqueBuilderPage`. Both
the alteration author form and the technique builder import it from that path. Do not inline
a new damage-type query here.

## Common Gotchas

**`tier_caps` is a `SerializerMethodField` — use `getTierCaps()`, not the raw field.**
The generated schema types `tier_caps` as an untyped dict (`Record<string, unknown>`). Always
call `getTierCaps(pending)` from `frontend/src/magic/types.ts` to get a properly typed
`AlterationTierCaps` object.

**The resolve endpoint accepts two mutually-exclusive payload shapes.**
`AlterationResolvePayload` is a union: `{ library_template_id: number }` for a library pick,
or `AlterationScratchPayload` for scratch authoring. The generated
`AlterationResolutionRequest` marks default-valued magnitude fields as required, so it cannot
express the library-pick shape; do not use it for this endpoint.

**The library endpoint returns a bare array, not a paginated object.**
`GET /api/magic/pending-alterations/{id}/library/` has `pagination_class=None` on that
action. `useAlterationLibrary(id).data` is `AlterationLibraryEntry[]`, not a paginated
wrapper. The `@extend_schema` decorator on the backend makes the generated schema reflect
this accurately.

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
