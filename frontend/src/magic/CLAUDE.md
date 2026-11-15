# Magic Module

Frontend for the magic system's Soul Tether, Thread, CharacterResonance,
Thread Hub Summary, Thread mutations, and teaching offers surfaces.
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
- `ResonanceBalance` — `{ resonance_id, balance, lifetime_earned, flavor_text }` (generated)
- `NearXPLockProspect` — `{ thread_id, boundary_level, xp_cost, dev_points_to_boundary }` (generated)
- `ThreadHubSummary` — response for `GET /api/magic/thread-hub-summary/` (generated)
- `PullPreviewRequest` — `components['schemas']['ThreadPullPreviewRequestRequest']` (generated)
- `PreviewedEffect` — `components['schemas']['ResolvedPullEffect']` — preview effect shape
- `PullPreviewResponse` — `components['schemas']['ThreadPullPreviewResponse']` (generated;
  fields: resonance_cost, anima_cost, affordable, resolved_effects, capped_intensity)

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

**Soul Tether / Audere respond + detail re-exports** (generated via `@extend_schema`, #920 —
these endpoints use plain `serializers.Serializer` classes, now annotated so drf-spectacular
emits real components; re-exported instead of hand-rolled so they can't drift):

- `SoulTetherDetail` — `components['schemas']['SoulTetherDetail']` — response for
  `GET /api/magic/soul-tether/{relationship_id}/`
- `DissolveRequest` — `components['schemas']['DissolveRequest']`
- `SineatingRequest` — `components['schemas']['SineatingRequestRequest']` (request body → "Request" suffix)
- `SineatingOffer` — `components['schemas']['SineatingOffer']`
- `SineatingRespondRequest` — `components['schemas']['SineatingRespondRequest']` (units_accepted=0 declines)
- `SineatingResult` — `components['schemas']['SineatingResult']`
- `RescueRequest` — `components['schemas']['SoulTetherRescueRequest']`
- `RescueOutcome` — `components['schemas']['RescueOutcome']`
- `StageAdvanceRespondRequest` — `components['schemas']['StageAdvanceRespondRequest']` (units_committed=0 declines)
- `StageAdvanceBonusResult` — `components['schemas']['StageAdvanceBonusResult']`
- `AudereRespondRequest` / `AudereOfferResult` — `audere/respond/` request + result
- `AudereMajoraRespondRequest` / `AudereMajoraCrossingResult` — `audere-majora/respond/` request + result
- `EligiblePath` / `PendingAudereMajoraOffer` / `PaginatedPendingAudereMajoraOfferList` —
  the Crossing offer list (`eligible_paths` typed via `@extend_schema_field` on the serializer)
- `PathOptions` — `components['schemas']['PathOptions']` — `{ current_path: PathListItem | null, options: PathListItem[] }`
  returned by `GET /api/progression/path-options/`; reused beyond Audere Majora (transition-generic)
- `PathListItem` — `components['schemas']['PathList']` — a single path item: `{ id, name, stage, stage_display, description, ... }`

**PathIntent local types** (hand-rolled; no generated schema component):

- `PathIntentDetail` — `{ id: number, intended_path: EligiblePath & Record<string, unknown>, declared_at: string }` — a declared intent row
- `PathIntentResponse` — `{ intent: PathIntentDetail | null }` — GET /api/progression/path-intent/ response

**Local types** (no 1:1 serializer to re-export):

- `WeaveThreadRequest` — body for POST /threads/ (weave new thread). `target_persona_id`
  (optional) is RELATIONSHIP_TRACK-only — the generated `ThreadRequest` schema already
  carries it (#2159 Task 3's backend contract), re-declared here since this type is
  hand-rolled rather than a 1:1 schema re-export.
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
- `getThreadResonanceOptions(id, move?)` — GET `/api/magic/threads/{id}/resonance-options/` →
  `ThreadResonanceOptions` (`{ritual_id, offering_required, offering_count,
unavailable_reason, options: [{resonance_id, resonance_name, affinity_name,
conversion_type, projected_points, qualifying}]}`; owner-only, slice 6 of #4672).
  `move` is `{fromResonance?, amount?}`, sent as `from_resonance` / `amount`: which of the
  thread's own resonance rows the points come from (default the leading one) and how many
  (default all of the row). `projected_points` is what the target's row would gain (#5123)

**Thread mutations:**

- `weaveThread(body)` — POST `/api/magic/threads/` → `Thread`
- `patchThreadNarrative(id, body)` — PATCH `/api/magic/threads/{id}/` → `Thread`
- `retireThread(id)` — DELETE `/api/magic/threads/{id}/` → `void`
- `crossXPLock(threadId, body)` — POST `/api/magic/threads/{id}/cross_xp_lock/` → `CrossXPLockResponse` (`{thread_id, unlocked_level, xp_spent}`)
- `imbueThread(body)` — wraps `performRitual` with imbuing ritual id + kwargs
- `imbueThreadAuto(characterSheetId, threadId, amount, resonanceId?)` — resolves the Rite of
  Imbuing via the serialized `is_imbuing` flag (NOT `service_function_path`,
  which the serializer never sends — the old filter made web imbuing dead on
  every server, #audit2), then POSTs `rituals/perform/` with
  `{ thread_id, amount, resonance_id? }` (`resonance_id` is the held resonance that pays;
  omitted, the thread's leading resonance pays, #5123). The canonical rite is CEREMONY-kind and the web is
  its client-hosted UI, so the backend fuses the `imbue` finisher into that
  one POST (performing the ceremony alone would only mint the pending effect).
- `previewPull(body)` — POST `/api/magic/thread-pull-preview/` → `PullPreviewResponse`.
  The request may carry `payers` (thread id to the resonance paying for it; a thread left
  out is paid by its leading resonance). The response's `per_thread` lists, for each pulled
  thread, one `PayerOption` per resonance the character holds: `{resonance_id,
resonance_name, cost, balance, affordable, effects, level_read}`, the effects being that
  payer's own on that thread (never summed across threads) and `level_read` the thread
  level they were read at (#5123)

**Teaching offer mutations:**

- `acceptTeachingOffer(offerId, body?)` — POST `/api/magic/teaching-offers/{id}/accept/` → `AcceptTeachingOfferResponse`

**Soul Tether mutations:**

- `dissolveSoulTether(body)` — POST `/api/magic/soul-tether/dissolve/` → `void`
- `requestSineating(body)` — POST `/api/magic/soul-tether/sineating/request/` → `SineatingOffer`
- `respondToSineating(body)` — POST `/api/magic/soul-tether/sineating/respond/` → `SineatingResult`
- `performRescue(body)` — POST `/api/magic/soul-tether/rescue/` → `RescueOutcome`
- `respondToStageAdvance(body)` — POST `/api/magic/soul-tether/stage-advance/respond/` → `StageAdvanceBonusResult`

**PathIntent reads (progression, #954):**

- `getPathIntent(characterId)` — GET `/api/progression/path-intent/` (`X-Character-ID` header) → `PathIntentResponse`
- `getNextPathOptions(characterId)` — GET `/api/progression/path-options/` (`X-Character-ID` header) → `PathOptions`

**PathIntent mutations (progression, #954):**

- `putPathIntent(characterId, pathId)` — PUT `/api/progression/path-intent/` (`X-Character-ID` header), body `{ path_id }` → `PathIntentResponse` (declare intent)
- `deletePathIntent(characterId)` — DELETE `/api/progression/path-intent/` (`X-Character-ID` header) → `void` (clear intent)

**Test helper:**

- `__resetImbuingRitualIdCacheForTests()` — resets the imbuing-ritual-id module cache;
  call in `beforeEach` for any test that exercises imbue logic

**Motif style bindings (#2030):**

Wire contract: `MotifStyleViewSet` (`src/world/magic/views_motif_style.py`) —
`list`/`bind`/`unbind` dispatch `ListMotifStylesAction` / `BindMotifStyleAction` /
`UnbindMotifStyleAction` (`src/actions/definitions/motif_style.py`). These endpoints
are plain views (no `@extend_schema` yet), so the generated schema records "No
response body" for them — `MotifStyleBindingsResponse` / `BindMotifStyleRequest` /
`UnbindMotifStyleRequest` in `types.ts` are hand-rolled to mirror the action `data`
dicts instead. `GET /api/items/styles/` IS a generated `ReadOnlyModelViewSet`
(`items` app), so `PaginatedStyleList`/`StyleCatalogEntry` are re-exported cleanly.

**Cross-character scoping (#2030 review fix):** all three functions take a
`characterId` and send it as the `X-Character-ID` header — same mechanism as
`getPathIntent`/`putPathIntent` below. The backend (`MotifStyleViewSet`) resolves
that header (validated as owned via `CharacterContextMixin`) ahead of the caller's
active puppet, so viewing a non-puppeted alt's sheet reads/writes THAT alt's
bindings, not the puppet's. Falls back to the active puppet when the header is
omitted; a header naming an unowned character 404s rather than silently acting
as the puppet.

- `getMotifStyleBindings(characterId)` — GET `/api/magic/motif-styles/`
  (`X-Character-ID` header) → `MotifStyleBindingsResponse` (`{ bindings: MotifStyleBinding[] }`)
- `bindMotifStyle(characterId, body)` — POST `/api/magic/motif-styles/bind/`
  (`X-Character-ID` header), body `{ style_id, resonance_id }`. 400s (audacity cap
  exceeded, unclaimed resonance, unknown style) carry a `{detail}` string via
  `readErrorDetail`.
- `unbindMotifStyle(characterId, body)` — POST `/api/magic/motif-styles/unbind/`
  (`X-Character-ID` header), body `{ style_id }`. 400 (style not bound) carries a
  `{detail}` string.
- `getStyleCatalog()` — GET `/api/items/styles/` → `PaginatedStyleList`. Paginated
  (page_size=50, `ItemTemplatePagination`); the bind form only fetches the first
  page for the current catalog size — revisit if the catalog grows past 50 rows.

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
- `magicKeys.pathOptions(characterId)` → `['magic', 'path-options', characterId]`
- `magicKeys.pathIntent(characterId)` → `['magic', 'path-intent', characterId]`
- `magicKeys.motifStyleBindings(characterId)` → `['magic', 'motif-styles', 'bindings', characterId]`
- `magicKeys.styleCatalog()` → `['magic', 'motif-styles', 'catalog']`
- `magicKeys.techniqueProgress(characterId)` → `['magic', 'technique-progress', characterId]`

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
- `usePathIntent(characterId)` — GET `/api/progression/path-intent/`; disabled when `characterId ≤ 0`
- `useNextPathOptions(characterId)` — GET `/api/progression/path-options/`; returns `PathOptions`
  (current path + active next-stage children); disabled when `characterId ≤ 0`
- `useMotifStyleBindings(characterId)` — GET `/api/magic/motif-styles/`
  (`X-Character-ID` header); the given character's current Style bindings; disabled
  when `characterId ≤ 0`
- `useStyleCatalog()` — GET `/api/items/styles/`; the Style catalog for the bind form's picker
- `useTechniqueProgress(characterId)` — GET `/api/magic/technique-progress/`
  (`X-Character-ID` header); the given character's in-progress training meters;
  disabled when `characterId ≤ 0`

**Mutation hooks:**

- `useDissolveSoulTether()` — invalidates `soulTetherDetail(id)` + `soulTether()`
- `useRequestSineating()` — invalidates `sineatingPending()`
- `useRespondToSineating()` — invalidates `sineatingPending()` + `soulTether()`
- `usePerformRescue()` — invalidates `soulTether()`
- `useRespondToStageAdvance()` — invalidates `stageAdvancePending()` + `soulTether()`
- `useWeaveThread()` — invalidates `threadList`, `threadHubSummary`
- `usePatchThreadNarrative(id)` — invalidates `thread(id)`, `threadList`
- `useRetireThread()` — invalidates `threadList`, `threadHubSummary`
- `useThreadResonanceOptions(threadId, enabled, move?)` — read hook for the retune dialog's
  options (`threadResonanceOptions(id, fromResonance, amount)`, `gcTime: 0`, fetched only
  while the dialog is open; each from-row or amount is its own query)
- `useRetuneThread()` — performs the retune rite through `performRitual`; invalidates
  `threads()`, `thread-hub-summary`, `characterResonances()`
- `useImbueThread()` — takes `{ characterSheetId, threadId, amount, resonanceId? }`;
  invalidates `thread(id)`, `threadHubSummary`, `characterResonanceList`
- `useCrossXPLock()` — takes `{ threadId, body }`;
  invalidates `thread(id)`, `threadHubSummary`
- `useAcceptTeachingOffer()` — takes `{ offerId, body? }`;
  invalidates `teachingOffers`, `threadHubSummary`
- `useDeclarePathIntent()` — takes `{ characterId, pathId }`; calls `api.putPathIntent`;
  invalidates `pathIntent(characterId)` on success
- `useClearPathIntent()` — takes `characterId`; calls `api.deletePathIntent`;
  invalidates `pathIntent(characterId)` on success
- `useBindMotifStyle(characterSheetId)` / `useUnbindMotifStyle(characterSheetId)` — call
  `api.bindMotifStyle`/`api.unbindMotifStyle` with `characterSheetId` (backs the
  `X-Character-ID` header, scoping the mutation to that character); both invalidate
  `motifStyleBindings(characterSheetId)` plus the character-sheet query
  (`['character-sheets', characterSheetId]`, per `character_sheets/queries.ts`'
  `useCharacterSheetQuery`) — the sheet's `magic.motif.resonances[*].styles` mirrors
  the same bindings
- `useTrainTechnique(characterSheetId)` — takes `{techniqueId, body?}`; calls
  `api.trainTechnique(characterSheetId, techniqueId, body)`; invalidates
  `techniqueProgress(characterSheetId)` on success so the refetched
  progress/teacher/weekly-remaining figures reflect the session immediately, plus
  `['character-sheets', characterSheetId]` (unconditional, mirroring
  `useBindMotifStyle`/`useUnbindMotifStyle`) — a completed session mints a
  `CharacterTechnique`, which `SpellbookTab` renders from the sheet payload, not
  from the meter list, so without this the new technique wouldn't appear until an
  unrelated refetch

**Note:** `previewPull` is NOT a hook — it's a plain `api.previewPull(body)` async function.
Pull previews are user-driven and ephemeral; components should debounce calls manually.

**Technique progress meters (#2739):**

- `getTechniqueProgress(characterId)` — GET `/api/magic/technique-progress/`
  (`X-Character-ID` header) → `TechniqueProgressMeter[]` (bare array — the
  view's `list` returns `Response(serializer.data)` directly, no pagination
  class). Wire contract: `TechniqueProgressViewSet`
  (`src/world/magic/views_technique_progress.py`).
- `trainTechnique(characterId, techniqueId, body?)` — POST
  `/api/magic/technique-progress/{technique_id}/train/` (`X-Character-ID`
  header), body `TrainTechniqueRequest` (`{ap_to_invest?}`) → `TrainTechniqueResult`.
  `techniqueId` is the `Technique` pk (matching `TrainTechniqueAction`'s own
  kwarg), not the `TechniqueProgress` row's pk. 400s (no meter, weekly cap hit,
  can't afford the AP, stale meter) carry a `{detail}` string via `readErrorDetail`.

### `__tests__/queries.test.tsx`

Unit tests for read and mutation hooks. Uses `vi.fn()` mocks of `api.*` (no msw).

Covers: `useSoulTetherDetail`, `usePendingSineatingOffers`, `usePendingStageAdvanceOffers`,
`useThreads`, `useCharacterResonances`, `useDissolveSoulTether`, `useRespondToSineating`,
`useThreadHubSummary`, `useThread`, `useTeachingOffers`, `useWeaveThread`,
`usePatchThreadNarrative`, `useRetireThread`, `useImbueThread`, `useCrossXPLock`,
`useAcceptTeachingOffer`, `useNextPathOptions`, `useMotifStyleBindings`/
`useBindMotifStyle`/`useUnbindMotifStyle` (character-id threading into the api call +
query key, #2030 review fix), `useTrainTechnique` (character-id threading + the
`createWrapperWithClient`/`invalidateSpy` idiom pinning that a completed session
invalidates BOTH `techniqueProgress(characterSheetId)` and
`['character-sheets', characterSheetId]`, #2739 review fix), and `magicKeys` shape
assertions.

The imbue tests call `__resetImbuingRitualIdCacheForTests()` in `beforeEach`.

### `__tests__/alterationQueries.test.tsx`

8 unit tests covering `usePendingAlterations` (fetch happy path; no fetch while logged out via the auth guard), `useAlterationLibrary` (enabled/disabled by pendingId), `useResolveAlteration` (payload pass-through, cache invalidation), and `magicKeys` shape assertions.

### `components/alterations/AlterationResolveDialog.tsx`

Two-tab dialog (Library / Author) for resolving a single `PendingAlteration`. Library tab renders affinity-ordered `AlterationLibraryEntry` cards from `useAlterationLibrary`; selecting a card and confirming ("Accept this mark") submits `{ library_template_id }` via `useResolveAlteration`. Author tab renders `AlterationAuthorForm`. Both `TabsContent`s use `forceMount` (inactive panel hidden via CSS) so authored prose survives tab switches. On server error, a `role="alert"` banner renders the `AlterationResolveError` message plus any orphaned field errors (keys the author form doesn't render).

### `components/alterations/AlterationAuthorForm.tsx`

Controlled form for the scratch-authoring resolution path (caps arrive via the `caps` prop, derived by the dialog from `getTierCaps(pending)`). Magnitude fields are native `<select>`s offering only `0..cap`. The damage-type `<select>` is always visible but disabled at `weakness_magnitude === 0` and submit-required when > 0. At tiers 4–5 the visibility switch renders checked and disabled (`is_visible_at_rest` forced `true` in the payload). Both description textareas show “n / 40 minimum” counters; `MIN_ALTERATION_DESCRIPTION_LENGTH` gates submit client-side.

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
`XPLockBoundaryPanel`, `PullEffectPreview`, `ThreadRenameDialog`, `ThreadRetireDialog`, and
`ThreadResonanceDialog` (opened by the "Change resonance" button, shown on a live thread).
The Resonance stat says the thread's mix in words (`threadMixInWords`), and `ImbuePanel`
gets every resonance the character holds from `useCharacterResonances` (#5123).

### `pages/WeavingTeachingOffersPage.tsx`

Teaching-offer inbox at `/threads/teaching`. Lists incoming `ThreadWeavingTeachingOffer`
rows via `TeachingOfferCard`; each card opens `AcceptOfferDialog` to pay XP and accept.

### `aura.ts`, `auraQueries.ts`, `components/AuraHalo.tsx` (#5123)

The aura in words and as a halo. `aura.ts` is the one place an aura's figures become language
(never a number to a player): `shareInWords(share, total)` (the backend `share_in_words`
thresholds in `world/magic/services/drift.py`, so every surface reads alike), `auraSentence(shares)`
("Mostly primal, a third abyssal."), `wordsToPart(words)` (the midpoint of a word's band, for
sizing a segment where the API sends only a word), `affinitySlug` and `haloGradient(segments)` (the
conic gradient over the `--aura-*` tokens in `character_sheets/sheet.css`). `auraQueries.ts` holds
`useCharacterAuras(characterId | null, enabled)` (GET `/api/magic/character-auras/[?character=]`,
the owner's own auras with `settled_percent`, `unsettled`, `unsettled_line`, `mire_share_words`) and
`useAcceptAura()` (POST `.../{id}/accept/`; invalidates the aura keys and `['character-sheets', id]`).
They live apart from `api.ts` and `queries.ts`, so a test that mocks `@/magic/queries` wholesale
must also mock `@/magic/auraQueries`. `AuraHalo` replaces the old `AuraStrip`: props `shares`,
optional `settled` (a dashed ring of who they are), `mire {words, part}` (a Sineater's Mire share
drawn apart from their own Abyssal, with a key), `unsettled` and `unsettledLine` (restless halo,
the Unsettled status and the ruled line in place of the split sentence), `size 'full' | 'mini'`,
`sentence` and `children`; it imports `sheet.css` itself so the creation page gets the colours,
and renders nothing without shares. The sheet payload carries no settled or unsettled data: the
settled ring, the Mire key and the Unsettled status show to the owner only (`isMyCharacter`,
read from `useCharacterAuras`); everyone else sees the halo and the words. Mounted by
`SpellbookTab` (with a "Settle your aura" button while unsettled) and by the Gift stage's resonance
step in character creation (`character-creation/components/gift/ResonanceWeights.tsx`, with
`auraSentence` of the weighted picks).

### `components/KindledResonancesPanel.tsx` (#5124)

"Your resonances" (demo Screen 1): each resonance she holds with its affinity, "Kindled,
<strength word>" or "Not kindled" (dimmed), and the reasons in player words; no numbers. Reads
`useKindledResonances(characterSheetId)` (`GET /api/magic/kindled-resonances/`, refetched every
30 s). Mounted in the scene tools (`SceneDetailPage`) and in the combat rail beside Dig deep
(`YourTurn`); renders nothing for a character with no resonance.

### `components/ReflectingOnRow.tsx` (#5124)

The optional "Reflecting on" row of a pose and of a journal entry (demo Screen 5): the
unsettling resonance and each unreflected kindled deed as pills, then Embrace or Disown once one
is picked; picking the same pill again clears it; a note says a new reflection replaces a waiting
one when `replaces_waiting` is set. Reads `useReflectionOptions(characterSheetId)`
(`GET /api/magic/reflectables/`) and renders nothing when there is nothing to reflect on. State
is a `ReflectionDraft` (`reflection.ts`); `reflectionFields(draft)` gives the three
`reflect_*` fields a request carries. Mounted by `CommandInput` (pose mode, not Commands or
companion; a scene pose sends the fields to `submit-pose`, an out-of-scene one dispatches the
registry `pose` action) and by `JournalEntryFields` (the desk and the composer dialog).

### `components/threads/ResonanceBalanceCard.tsx`

HoverCard showing a single resonance balance (current balance + lifetime earned + flavor text).
Used in `ThreadHubPage` to render the balance grid.

### `components/threads/ThreadStateBadge.tsx`

Small badge that maps a thread's `state` field to a colored label (Active, Dormant, Retired, etc.).

### `components/threads/ThreadCard.tsx`

Card for a single thread in the hub grid. Shows name, state badge, the thread's resonance
mix in words ("mostly Fury, some Domination"; the leading resonance's name when the thread
has no rows), XP-lock level, and a link to the detail page.

### `components/threads/ImbuePanel.tsx`

Panel in `ThreadDetailPage` for spending resonance to imbue a thread. Calls `useImbueThread`.
With more than one held resonance (`held` prop) it shows a "Spend" pill per resonance with
its balance, starting on the thread's leading resonance; the amount stepper stops at the
picked resonance's balance and the pick goes out as `resonanceId`. Every held resonance is
offered, whatever the thread's Gift lists (a Gift's `resonances` limits nothing). The panel is
keyed on the thread id (`ThreadDetailPage`) and starts on the first held resonance when the
leader is not one of them. With one offered resonance that is the
leader there is no choice to show and nothing is sent.

### `components/threads/PayerOptions.tsx`, `PerkInspect.tsx` (#5123)

The pull's "Pay with" choice, for one pulled thread, drawn from `per_thread` in the pull
preview. `PayerOptions` lists each payer with `cost` Name `· you have` balance and its own
perk rows (label, value, flavor snippet), starting on the thread's leading resonance (or
the first that can pay when the leader cannot); a payer that cannot afford the cost cannot be picked, and one the thread never took in
reads "No perks on this thread". A thread holding one resonance shows "Pays with X" and its
perks with no radio, unless its own resonance cannot pay: `showsPayerChoice` (`burn.ts`) is
true for several rows or an unaffordable own resonance, and the picker's tier strip uses the
same rule. `ThreadMakeup` is the "Level 3 · mostly Fury,
some Domination" line (just "Level 3" for one resonance). "Inspect perks" opens `PerkInspect`: per perk the amount, how it was
worked out (authored value x level multiplier), its source ("{Resonance} pull perk for {kind}
threads, tier N") and "Thread level used" (`level_read`, with a note when the payer is not the
leading resonance). Perk labels and values come from `effectLabel` / `effectValue` in
`burn.ts`; a capability perk reads "Grants {capability_name}" with its `capability_value`, a resistance "Resistance to {damage type}" (the preview effect carries `capability_name`, `capability_value`, `resistance_damage_type_name`; no perk has an authored duration). Mounted in `ThreadPullPicker` rows (the cast flow) and `ThreadPullDialog`
(combat declarations).

### `components/threads/ThreadPullPicker.tsx` and `ThreadPullDialog.tsx`

Both pick a tier and pulled threads; each pulled thread is paid by one resonance. A payer
list (`PayerOptions`) keeps the player's pick (`onSelect`) apart from what the pull has to
name (`onResolve`): the picked or starting payer, only while the list shows the choice and
the payer is not the leading resonance, otherwise nobody. A list that unmounts reports
nothing (a name filter only hides a pulled thread's row); the pulls keep only the payers of
threads still pulled. So a pick made at tier 3, where the leader cannot pay, does not follow the player to
tier 1, where the row reads "Pays with Leader" and nothing is sent. The picker takes
`payers` (the picks), `onPayerChange` and `onPayerResolve`; `useCastPullSelection` keeps
`payerPicks` / `setPayer` and `payers` / `resolvePayer`, and sends `payers` as `pull.payers`
(a thread without one is paid by its leading resonance). The tier strip stays open while ANY
held resonance can pay. The dialog does the same with its own state, sends the named payers
to the preview and returns them on `PullSelection.payers` beside `resonances` (the distinct
payers, which a mixed pull's burn picks from). The dialog offers Gift threads (its always-in-action kinds mirror the server's; only a social pull excludes a Gift thread, via `exclude_gift`, #1919, which the dialog never sends) and a thread while any held
resonance has a balance, and its cost line reads "3 Fury, 3 Domination" from the named
payers, not a flat total.
In combat, `combat/dodging.ts` (`roundPullRequest`) and `combat/sections/YourTurn.tsx` forward
`selection.payers` as the `pull_payers` kwarg (and `payers` on the burn preview), so a pick made
in the dialog reaches the declaration.

### `components/threads/XPLockBoundaryPanel.tsx`

Panel in `ThreadDetailPage` for crossing an XP-lock boundary. Shows cost/prospect info
and calls `useCrossXPLock`.

### `components/threads/PullEffectPreview.tsx`

Panel in `ThreadDetailPage` for previewing a thread pull (read-only). Calls `api.previewPull`
and shows resolved effects and affordability. Pull commit now rides cast/clash.

### `components/threads/ThreadRenameDialog.tsx`

Dialog for renaming a thread (patching `name` + `description`). Calls `usePatchThreadNarrative`.

### `components/threads/ThreadResonanceDialog.tsx`

Moves a thread to another resonance (slice 6 of #4672, Screen 6 of the #4735 demo). Reads
`useThreadResonanceOptions`; shows the server's `unavailable_reason` in place of the "Change
to" pills when the thread cannot move (no rite, a sanctum thread, a signed technique thread,
no options). A thread holds several resonance rows (`thread.resonances`), so the dialog
has a "Move from" pill per row (hidden for a one-row thread; default the leading row) and a
"Points to move" stepper with an "All" reset (default all of the row); both go to the options
endpoint, and `projected_points` is what the target's row gains. Each "Change to" pill carries
a swatch for the move kind (retune / Fall / Redemption, keyed on `conversion_type`). Offering
pills appear only when `offering_required`, and exactly `min(offering_count,
qualifying.length)` picks enable the button. Performs via `useRetuneThread` with `kwargs:
{thread_id, target_resonance, from_resonance?, amount?}` (`amount` only when the player chose
one); a 400 shows the server's detail; a result naming a different thread navigates to it
(`result.thread_id`). Tests: `__tests__/ThreadResonanceDialog.test.tsx`.

### `components/pillClass.ts`

`pillClass(selected)`: the outlined / filled pill classes shared by
`SettleAuraDialog` and `ThreadResonanceDialog`.

### `components/threads/ThreadRetireDialog.tsx`

Confirmation dialog for retiring a thread. Calls `useRetireThread`.

### `components/threads/WeaveThreadWizard.tsx`

Multi-step wizard for weaving a new thread. Step 1: select `TargetKind` (TRAIT, TECHNIQUE,
FACET, SANCTUM, COVENANT_ROLE, and RELATIONSHIP_TRACK are all live; RELATIONSHIP_CAPSTONE
is the one kind still stubbed "coming soon", #2033). The bare ROOM anchor was removed
(#879/#1199) — room-anchored threads now use the dedicated SANCTUM slot-based weaving flow,
not this generic wizard. Step 2: select anchor — for RELATIONSHIP_TRACK this is a "with
whom" partner-then-type picker (#2159, #3957): partner choices come from one
`@/relationships/api.listMyTies()` call, kept where the tie holds at least one UNENDED
label whose `type` is among `ThreadHubSummary.weavable_relationship_type_ids`; a tie
payload already carries its labels, so there is no per-partner detail fetch. Companion
ties are dropped (no persona to weave with). Picking a partner reveals only that
partner's qualifying types, still within step 2 (`renderRelationshipTrackStep2`), and the
submitted `target_id` is a `RelationshipType` catalogue id, NOT a row on the tie. The
tier minimum is deliberately not checked client-side — the server refuses with the
sentence the player should read. The payload adds `target_persona_id` (the partner's
primary Persona pk, resolved via `@/relationships/api.getPersonaIdForSheet`, which wraps
`/api/personas/?character_sheet=`) for this kind only —
`ThreadSerializer._resolve_partner_sheet` requires it server-side. Step 3: name +
description + confirm. Calls `useWeaveThread`.

### `components/threads/TeachingOfferCard.tsx`

Card for a single `ThreadWeavingTeachingOffer` in `WeavingTeachingOffersPage`. Shows offer
details and opens `AcceptOfferDialog`. Teacher is shown via the anonymity-respecting
`RosterTenure.display_name` (e.g. "2nd player of Ariel") surfaced as
`teacher_display_name` on the serializer.

### `components/threads/AcceptOfferDialog.tsx`

Dialog for accepting a teaching offer. Shows XP cost and calls `useAcceptTeachingOffer`.

### `components/glimpse/GlimpseFlow.tsx` + `glimpseTypes.ts` (#2427; CG mount replaced #3675 fix round 1)

Shared, purely presentational guided flow for authoring "The Glimpse" — props
in (`heading` (optional, defaults `'The Glimpse'`), `tags`, `selectedTagIds`,
`prose`, `showDeferralControls`, `storyHint` (optional, printed under the
story `Textarea`)), callbacks out (`onChangeAxis`, `onChangeProse`, `onSkip`);
no queries or mutations inside. `glimpseTypes.ts` is the single definition of
`GlimpseTagOption` (backs `GET /api/character-creation/glimpse-tags/`, and
carries `offers: TagOffer[]` per tag, #3675); the character-creation module
re-exports it from `types.ts` rather than redeclaring it. Renders the
`heading` at the top, then a Radix accordion (TONE single-select,
CONSEQUENCE/WITNESS multi-select; axes with zero catalog tags don't render a
step; each tag Card is `role="button" tabIndex={0}` with an explicit
`onKeyDown` for Enter/Space activation, review fix), SENSORY tags as toggle
chips (native `<button>`s, keyboard-operable for free) inside the
always-visible story `Textarea`. `AXIS_STEPS` (the axis order + arity) is
exported so `GlimpseAxes` (below) can reuse it without redeclaring it.

**Only one mount left:** the character sheet's live editor
(`components/glimpse/GlimpseEditorDialog.tsx`, below), unchanged. The CG
mount used to be `GiftStage` → `GlimpseSection` → this component (with a
`renderOffers` slot, #3675 Task 13), but that shipped a demo-fidelity defect
(the shadcn accordion hid two axes at a time, one axis' worth of offers
merged multiple tags under one heading, and the section heading duplicated
`GiftStage`'s own). Fix round 1 replaced the CG mount entirely with
`character-creation/components/gift/GlimpseAxes.tsx`; see that module's own
`CLAUDE.md` entry for its folio-grammar layout. `GlimpseFlowProps` no longer
carries `renderOffers` at all (removed, unused now that no caller passes it).

### `components/glimpse/GlimpseEditorDialog.tsx` (#2427 Task 6)

The "finish later" Glimpse editor on the own-character sheet — a `Dialog`
(same `@/components/ui/dialog` primitives `CodexModal` uses) hosting
`GlimpseFlow` in live mode. Opened from `SpellbookTab`'s aura card via a
"Finish your Glimpse" button, gated on `isMyCharacter && aura.can_finish_glimpse`
(mirrors the `MotifStylePanel` own-view gate). Catalog comes from
`useGlimpseTags()` (`@/character-creation/queries` — the same catalog CG's
`GlimpseSection` reads); selection/prose are seeded from the sheet payload's
`magic.aura.glimpse_tags`/`glimpse_story`; writes go through the Task 4 aura
action mutations below. `showDeferralControls={false}` — closing the dialog
IS the deferral (unlike CG, which offers an explicit "skip" button).

**ID-space note:** CG's `GlimpseSection` no longer links glimpse suggestions
by draft-held distinction id at all (#3675 retired
`draft_data.glimpse_linked_distinction_ids`; offers are chapter-scoped
picks synced immediately through `useSyncDistinctions`, see
`ChapterOffers`). This dialog's own linking is a separate, still-live
feature: linking a character's _existing_ `CharacterDistinction` rows to
their Glimpse, by **CharacterDistinction row id**, the id the aura's
`link-glimpse-distinction`/`unlink-glimpse-distinction` endpoints require,
which is exactly what `CharacterSheetDistinction.id` already carries.
`linkedDistinctionIds` (this file's own local variable, not a `GlimpseFlow`
prop) is derived from the sheet payload's `distinctions[*].is_from_glimpse`
flag (`world.character_sheets.types.DistinctionEntry`, #2427 backend
touch-up: `CharacterDistinction.from_glimpse_id is not None`);
`linkableDistinctions` maps the same list to `{id, name}`. No separate
fetch; both come from the sheet payload `SpellbookTab` already has.

**Mutation hooks** (`@/magic/queries`, wrap the Task 4
`CharacterAuraViewSet` actions — `src/world/magic/views.py`):
`useSetGlimpseTags(auraId, characterSheetId)`,
`useSetGlimpseProse(auraId, characterSheetId)`,
`useToggleGlimpseDistinction(auraId, characterSheetId)` (wraps
link+unlink behind one `toggle(characterDistinctionId, isCurrentlyLinked)`
call). All three invalidate `['character-sheets', characterSheetId]` on
success — the same key `useCharacterSheetQuery` reads — rather than trying
to read the aura action responses (`CharacterAuraSerializer` output doesn't
carry `glimpse_tags`/`glimpse_story`/`can_finish_glimpse`; those live only in
the sheet payload's `AuraData`). Request bodies in `magic/types.ts`
(`SetGlimpseTagsRequest`/`SetGlimpseProseRequest`/
`GlimpseDistinctionLinkRequest`) are aliases onto the generated schema
(`GlimpseSetTagsRequest`/`GlimpseSetProseRequest`/`GlimpseDistinctionLinkRequest`
components) — the four `CharacterAuraViewSet` `@action` methods now carry
`@extend_schema(request=...)` (`src/world/magic/views.py`), so drf-spectacular
types each body against its real input serializer instead of falling back to
the ViewSet's own `CharacterAuraSerializer`.

### `XpKudosPage.alterationGate.test.tsx` (in `src/progression/`)

3 tests for the `AlterationGateAlert` rendered within `XpKudosPage`: alert is shown when `usePendingAlterations` returns open alterations, names the affected character(s), and is absent when the list is empty.

### `components/PathIntentCard.tsx` (#954)

Card rendered on `MagicProgressionPage` that shows the character's current Path and lets
them declare which next-stage path they intend to pursue. Consumes `useNextPathOptions(characterId)`
and `usePathIntent(characterId)`. Framed as **"Your Path"** in all player-facing copy — never
"Audere Majora" (keep the transition name out of the UI). When `options` is empty the card
renders a "nothing to choose yet" sentinel (`data-testid="path-options-empty"`); when no
current path exists, the card renders nothing. Selecting an option and confirming calls
`useDeclarePathIntent`; "Clear" calls `useClearPathIntent`. The declared option shows a
"declared" badge.

### `pages/MagicProgressionPage.tsx` (#954)

Landing page for the player's magic progression surface, at `/magic/progression` (lazy-loaded
via `React.lazy`). Hosts `PathIntentCard` and future progression widgets. `PathIntentCard` is
passed the active character-sheet id from the account context (rendered as `<PathIntentCard characterId={characterSheetId ?? 0} />`; disabled when `characterSheetId` is null).

### `__tests__/PathIntentCard.test.tsx` (#954)

5 unit tests (real hooks + mocked `../api`). Covers: no render when no current path
(`OPTIONS_NONE`); current path + selectable options rendered + no "Audere Majora" text; empty
message for terminal path (no further options); declare calls `putPathIntent(characterId, pathId)`;
Clear calls `deletePathIntent(characterId)` and shows "declared" badge.

### `components/MotifStylePanel.tsx` (#2030)

Card rendered in `SpellbookTab.tsx` (#1446, this module), own-view only,
below the read-only Motif card. Lists the current `MotifStyleBinding`s of the
character named by `characterSheetId` (passed to `useMotifStyleBindings`, plus
`useBindMotifStyle`/`useUnbindMotifStyle` — all three thread it into the
`X-Character-ID` header so the panel reads/writes THAT character's bindings even
when it isn't the account's active puppet, #2030 review fix) grouped by resonance
(`data-testid="motif-style-group-{resonance_id}"`), each with an "Unbind" button
(`useUnbindMotifStyle`). A bind form (native `<select>`s — a style from
`useStyleCatalog`, a resonance from `useCharacterResonances`) submits via
`useBindMotifStyle`; the Bind button stays disabled until both are chosen. Always
renders (never gated to a "nothing to see" empty div) — when the character has no
claimed resonances the form area explains "Claim a resonance first…"
(`data-testid="motif-style-no-resonances"`) instead of showing selects with nothing
to bind to. Server 400s (audacity cap exceeded, unclaimed resonance, style not
bound) surface via each mutation's `.error.message`
(`data-testid="motif-style-bind-error"` / `"motif-style-unbind-error"`).

### `components/MotifFacetPanel.tsx` (#5021)

Mounted in `SpellbookTab.tsx` below `MotifStylePanel`, own view only; renders nothing
without a claimed resonance. One group per claimed resonance
(`data-testid="motif-facet-group-{resonance_id}"`): the facets tied to it as chips, each
with an "Untie <name>" button, and a `FacetPicker` (no `canCreate`) excluding those already
tied. Reads `useMotifStyleBindings(characterSheetId).data.facet_bindings`
(`MotifFacetBinding`), `useCharacterResonances`, `useFacets` (`@/character-creation/queries`);
writes through `useSetMotifFacet(characterSheetId)` (`{facet_id, resonance_id, tie}` →
`api.setMotifFacet`, POST `motif-styles/bind-facet/` or `unbind-facet/` with the
`X-Character-ID` header; invalidates the bindings and the character sheet). A refusal's
`detail` shows verbatim (`role="alert"`). Tests: `components/MotifFacetPanel.test.tsx`.

### `components/MotifStylePanel.test.tsx` (#2030)

9 unit tests (mocks `../queries`, no msw — mirrors `SineatingRequestDialog.test.tsx`'s
idiom). Covers: bindings grouped by resonance; empty-bindings message; unbind fires
`{ style_id }`; bind form submits `{ style_id, resonance_id }`; Bind stays disabled
until both selects have a value; "claim a resonance first" empty state (and no
selects rendered); the bind and unbind mutations' 400 `detail` messages both render;
`useMotifStyleBindings`/`useBindMotifStyle`/`useUnbindMotifStyle` are all called with
`characterSheetId` (cross-character scoping, #2030 review fix).

### `components/FacetPicker.tsx` + `facetKey.ts` (#4197)

The one way to pick a facet from the flat vocabulary: the deity page (`pantheon`) and item
crafting (`inventory/AttachFacetDialog`) both mount it. Props: `facets` (the vocabulary the
caller already loaded, `{id, name}[]`), `exclude`, `onPick(facet)`, `canCreate` (staff only),
`label`. Closed it is a `+ {label}` button; open it is a cmdk popover: type to search what
exists; a spelling of two or more letters that resolves to nothing (by `facetKey`, the
TypeScript mirror of `services.facets.facet_key`) asks `useNearFacets` (debounced 250 ms,
`GET /api/magic/facets/near/`) and shows the answers under "Did you mean"; with `canCreate`
and no key-equal answer it offers `Create "<spelling>"`, which `useCreateFacet` POSTs and
then picks. The server's answer is the truth (a spelling that resolves comes back with
`matched: true`); `facetKey` only decides what the picker shows while typing.

### `components/__tests__/FacetPicker.test.tsx` (#4197)

Search picks an existing facet; a new spelling shows its near-matches and, for staff, the
create item that POSTs and picks the result; a player never sees create; a spelling that
already resolves never offers it. `facetKey`'s cases are pinned beside the Python ones.

### `components/TechniqueProgressPanel.tsx` (#2739 Task 3)

Card rendered in `SpellbookTab.tsx`, own-view only, below `MotifStylePanel` — the
player-facing meter panel that makes the training-check loop (Task 1's
`TrainTechniqueAction`, Task 2's web endpoints) visible in the game UI. Lists the
character's `useTechniqueProgress(characterSheetId)` rows, one card per meter: technique
name, a `Progress` bar + `points_accumulated`/`total_required` fraction, a "Taught by
`teacher_name`" or "Self-study" badge, `weekly_remaining` (when non-null), an optional
AP-to-invest number input, and a Train button. Submitting calls
`useTrainTechnique(characterSheetId).mutate({ techniqueId, body })` — `body` is omitted
(server default) when the AP input is blank. On success the session outcome renders
inline (`data-testid="technique-progress-result-{techniqueId}"` — "you've learned X!"
when `technique_acquired`, else `"{outcome_name}: {points_after}/{total_required}."`,
mirroring `TrainTechniqueAction`'s own message); the query invalidation refetches the row
so the bar/fraction/weekly-remaining stay live. On a 400 the server's `detail` message
renders under the row that triggered it
(`data-testid="technique-progress-error-{techniqueId}"`). Empty state is a single quiet
line (`data-testid="technique-progress-empty"`, "Nothing in training right now.") rather
than an empty card.

### `components/TechniqueProgressPanel.test.tsx` (#2739 Task 3)

8 unit tests (mocks `../queries`, no msw — mirrors `MotifStylePanel.test.tsx`'s idiom).
Covers: meter rows render name/fraction/teacher-or-self-study/weekly-remaining;
`useTechniqueProgress`/`useTrainTechnique` are both called with `characterSheetId`; the
empty state; the train mutation payload with and without an AP input value; a
non-integer AP input (e.g. `2.5`) is treated as unset rather than sent fractional; the
success-outcome line after a train call resolves; the 400 `detail` message renders under
the row that failed.

### Settle your aura: conversion offers and accepting (#4733, #5123)

A deed in the main affinity in a live scene opens a conversion offer; the player answers it with
the drift correction rite (Atone). Accepting the changes to the aura needs no offer. Mirrors the
entry-flourish front end (gate, dialog, 5 s poll).

**Wire contract** (`/api/magic/drift-correction/`, generated types, re-exported in `types.ts`):

- `getPendingDriftConversionOffers()` - GET `pending/` -> `PaginatedDriftConversionOfferList`.
  Account-scoped (`character_id` names the character the offer was made for). Each `DriftConversionOffer` is
  `{ id, scene_id, character_id, caps[], rite_ready, rite_not_ready_message }` (`rite_ready` is false while
  the rite, its check type or a tier's share is missing; the message is the rite's own refusal, empty
  while ready); each cap is `{ target_resonance {id, name, affinity},
cap_remaining, focus_bonus, sources[], qualifying_components[] }`. A source is
  `{ resonance_id, resonance_name, balance, multiplier (decimal string), conversion_type
('FALL' | 'REDEMPTION'), max_amount, projected_output }` (`projected_output` is for
  `max_amount`); a component is `{ item_id, name, mode ('material' | 'facet' | 'keepsake') }`.
- `convertDrift(body)` - POST `convert/`, body `{ offer_id, source_resonance_id,
target_resonance_id, amount, component_ids }` -> `DriftCorrectionResult`
  (`attempted_amount`, `converted_amount`, `granted_amount`, `outcome_name`,
  `success_level`, `conversion_type`, `focus_bonus`). A refusal is 400 `{detail}` (the view returns its request-validation failures in the same
  shape, field names dropped, so the player only ever reads the sentence), thrown by
  `readErrorDetail` so the dialog shows `error.message`.
- `declineDriftConversion({ offer_id })` - POST `decline/` -> `{ detail }`.

**Hooks:** `usePendingDriftConversionOffers(enabled?)` (`magicKeys.driftConversionPending()`,
polls every 5 s, no `throwOnError`), `useConvertDrift()` (invalidates the pending key and
`characterResonanceList()`), `useDeclineDriftConversion()` (invalidates the pending key).

**Components:** `DriftConversionOfferGate` (strip headed "Settle your aura" + auto-open once per
offer id via `useAutoOpenOncePerOffer`; takes `sceneId` and shows the offer whose `scene_id` matches
it, polling only once the scene is known; keeps the result line after an exhausted offer leaves the
inbox; only an `aria-hidden` glow behind the strip pulses, so its words keep full contrast; it reads
the aura of the offer's own `character_id` through `useCharacterAuras` and only while an offer is
open, so Accept never writes to another character's aura) and `SettleAuraDialog` (Screen 4, one
framed box titled with the unsettled line, falling back to "Settle your aura", with up to two exits
side by side, each with a small `AuraHalo` of the aura after it).

- **Atone** shows only with an open offer (in a scene). Per cap, a system line "The <sources with a
  balance, joined with commas and 'and'> you gained turns to <target>." beside the cap remaining; a
  quiet row with the source picker (a plain chip when there is one source) and an amount bounded by
  the chosen source's `max_amount`, defaulting to it; single-select component pills `<name> ·
<mode>`, the chosen one filled `bg-primary text-primary-foreground`, the rest outlined; a rate line
  built from the source's `multiplier` ("Redemption: 12 Ruin becomes about 6 Dawnlight", plus "; a
  focus adds N" only when `focus_bonus > 0`); the result and error lines; and "Begin the rite"
  (primary), disabled until a component is chosen and the amount is valid. While `rite_ready` is
  false each block shows `rite_not_ready_message` in place of the component pills and the button
  stays disabled. The yield for a typed amount is `max(1, floor(amount * multiplier))`, the
  server's own rounding.
- **Accept the changes to your Aura** shows whenever the character is unsettled, with or without an
  offer; opened from the sheet outside a scene it is the only exit. A line "You become more
  <affinity>." (the aura's `unsettled_affinity_name`, the affinity the accept action itself names;
  the server's own line replaces it after) and an Accept button that calls `useAcceptAura`.
- The footer "Not now" declines an open offer, else just closes; the character stays unsettled.
  The word "accepted" is never shown to the player.

**Mounts (once per surface):** `SceneDetailPage` (`isActive` guard, beside
`EntryFlourishOfferGate`, `sceneId` from the scene) and `GamePage`'s `GameCenter` (when the
session has a scene, `sceneId` from the session's scene); the sheet's `SpellbookTab` opens
`SettleAuraDialog` itself with no offer. Tests that mock `@/magic/queries` wholesale
(`SceneDetailPage.test.tsx`) must add the three drift hooks and mock `@/magic/auraQueries`
(`GamePage.test.tsx` and `SceneDetailPage.test.tsx` do, so the gate never fetches).

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
- **Serializer mapping** (all generated via `@extend_schema`, #920):
  - `SoulTetherDetailSerializer` → `SoulTetherDetail`
  - `SineatingOfferSerializer` → `SineatingOffer`
  - `SineatingResultSerializer` → `SineatingResult`
  - `RescueOutcomeSerializer` → `RescueOutcome`
  - `StageAdvanceBonusResultSerializer` → `StageAdvanceBonusResult`
  - `SineatingPendingOfferSerializer` → `SineatingPendingOffer`
  - `PendingStageAdvanceOfferSerializer` → `PendingStageAdvanceOffer`
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

**`SoulTetherDetail` is now generated (#920), re-exported — do not hand-roll it.**
`SoulTetherDetailView.get` carries `@extend_schema(responses={200: SoulTetherDetailSerializer})`,
so `components['schemas']['SoulTetherDetail']` exists. Same pattern for every soul-tether /
Audere respond + detail endpoint: annotate the view (or `@extend_schema_field` a method field),
run `just gen-api-types`, and re-export — never re-introduce a hand-rolled mirror that can drift.

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
