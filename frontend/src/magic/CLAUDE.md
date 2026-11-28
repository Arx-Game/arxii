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
- `SineatingDeclineRequest` — `components['schemas']['SineatingDeclineRequest']` (`{ actor_sheet_id, sinner_sheet_id }`)
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
- `getSineatingOptions(characterSheetId)` — GET `/api/magic/sineating-options/?character_sheet=<id>` →
  `SineatingOption[]` (the page's `results`): `{ role ('entreat' | 'perform'), partner_sheet_id,
partner_name, max_units, resonance_name }`, every Sineater present the character can entreat and every plea
  they can answer
- `getPendingStageAdvanceOffers()` — GET `/api/magic/soul-tether/stage-advance/pending/`
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
- `declineSineating(body)` — POST `/api/magic/soul-tether/sineating/decline/` → `{ detail }` (the line the
  Sineater is told; a refusal is 400 `{detail}`)
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
- `magicKeys.sineatingOptions(sheetId)` → `['magic', 'sineating-options', sheetId]`
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
- `useSineatingOptions(characterSheetId, enabled?)` — polled every 5 s so a plea made in the scene
  reaches the Sineater's composer without a reload; off while `enabled` is false (no active scene)
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
- `useDeclineSineating()` — invalidates every `sineatingOptions`
- `useRefreshSineating(characterSheetId)` — not a mutation: the callback the composer runs once a Sineating
  posts (re-reads the options, the Soul Tether and `reflectionOptionsAll`, since a Sineater now carries a
  Mire to reflect on)
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

Covers: `useSoulTetherDetail`, `usePendingStageAdvanceOffers`,
`useThreads`, `useCharacterResonances`, `useDissolveSoulTether`,
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
("Mostly primal, a third abyssal."), `affinitySlug` and `haloGradient(segments)` (the
conic gradient over the `--aura-*` tokens in `character_sheets/sheet.css`). `auraQueries.ts` holds
`useCharacterAuras(characterId | null, enabled)` (GET `/api/magic/character-auras/[?character=]`,
the owner's own auras with `settled_percent`, `unsettled`, `unsettled_line`). The aura carries no Mire
(#5177): the Mire is corruption a Sineater carries for each Sinner, shown on the Soul Tether panel.
The accept endpoint and `useAcceptAura` are gone (#5124): nothing settles without a reflection.
They live apart from `api.ts` and `queries.ts`, so a test that mocks `@/magic/queries` wholesale
must also mock `@/magic/auraQueries`. `AuraHalo` replaces the old `AuraStrip`: props `shares`,
optional `settled` (a dashed ring of who they are), `unsettled` and `unsettledLine` (restless halo,
the Unsettled status and the ruled line in place of the split sentence), `size 'full' | 'mini'`,
`sentence` and `children`; it imports `sheet.css` itself so the creation page gets the colours,
and renders nothing without shares. The sheet payload carries no settled or unsettled data: the
settled ring and the Unsettled status show to the owner only (`isMyCharacter`,
read from `useCharacterAuras`); everyone else sees the halo and the words. Mounted by
`SpellbookTab` (its reflections card carries the "Settle your aura" button, #5124) and by the Gift stage's resonance
step in character creation until #5231, when that step began drawing its aura with `AuraSwirl`
(below) and `ResonanceWeights.tsx` was removed; `AuraHalo` stays on the character sheet.

### `components/AffinityExplanation.tsx` (#5293)

Wraps the sheet's `AuraHalo` (`SpellbookTab`) in a hover card that names each affinity the
aura holds, with the description staff wrote on the Affinity row (`useAffinities` from
`@/character-creation/queries`, `GET /api/magic/affinities/`). The trigger is an unstyled
button around the halo, named by the halo's own words, so it opens on hover or keyboard
focus. An affinity with a blank description is left out; with none left the halo is drawn
bare, with no trigger. A test that mocks `@/character-creation/queries` wholesale and
renders `SpellbookTab` must give it `useAffinities`.

### `auraSwirl.ts`, `components/AuraSwirl.tsx` (#5231)

An aura drawn as one swirling mass in which each colour covers its share and the colours do not
blend, ported from the approved creation demo. `auraSwirl.ts` holds the pure drawing: `hexToOklch`,
`lift`, `ramp`, `noise`, `cloud`, `swirlThreshold` (the quantile that gives each colour its share),
`drawMass` and `massFrame`. `AuraSwirl` takes `primaryHex`, `secondaryHex` (null draws one colour),
`secondShare` (0 to 1) and `className`; a colour the server sent that is not `#RRGGBB` draws neutral
grey (`#8C8C8C`, the colour a resonance starts with), the swirl keeps its phase across redraws, and
it animates only while the page is visible and draws one still frame under reduced motion. Only the
Gift stage of character creation mounts it (`StrengthStep`); the sheet keeps `AuraHalo`.

### `components/CastResonancePicker.tsx` (#5231)

The resonances a cast may be worked in, one row each, on the scene cast panel (`ActionPanel`, from
`CastableTechnique.resonance_options`) and the combat cast declaration (`YourTurn`, from the
descriptor's `cast_resonance_options`). A row shows the resonance's colour and name, "your usual" on
the default, the kindled word and its reason, "Stronger here than <the usual one>." on the single option
the server marked `stronger`, and "Adds corruption." where `adds_corruption` is set. Nothing is drawn
with fewer than two options. Picking the default sends nothing (a worn alternate self's resonance is
its own default entry and is not on the Gift's thread, so the server would refuse its id); picking
any other sends `preferred_resonance_id`. It is separate from `TechniqueFormPicker`, which keeps choosing
forms: picking a variant form moves the resonance picker to that form's resonance, a pick made after
wins, and the base form leaves it alone. `PayerOptions` shows a "Stronger" tag beside the payer the
server marks `stronger` in the pull preview.

### `components/KindledResonancesPanel.tsx` (#5124, #5177)

"Your resonances" (demo Screen 1): each resonance she holds with its affinity, "Kindled,
<strength word>" or "Not kindled" (dimmed), and the reasons in player words; no numbers. Reads
`useKindledResonances(characterSheetId)` (`GET /api/magic/kindled-resonances/`, refetched every
30 s), whose data is a `KindledReading` `{ results: KindledResonance[], impulses: Impulse[] }`
(`YourTurn` reads `data?.results`). Under the resonances, "Impulses" lists what the corruption the
character carries stirs: an `Impulse` is `{ resonance_id, resonance_name, label ("Intrusive Thoughts:
Ruin" / "Compulsion: Ruin"), present, is_compulsion, text, reasons }`. The row shows the `label`, the
`text` when the server sent words, the `reasons`, and "Present" while something the resonance cares
about is here. Three looks, told apart by `data-state`: `stirring` (violet, an Intrusive Thought),
`compulsion` (red, bold, a Compulsion not in effect) and `compulsion-active` (a heavy red border and
fill, a Compulsion that is costing rolls now). Mounted in the scene tools (`SceneDetailPage`), the game
page and the combat rail beside Dig deep (`YourTurn`); renders nothing for a character with no
resonance and no impulse.

### `components/ReflectingOnRow.tsx` (#5124, #5177)

The optional "Reflecting on" row of a pose and of a journal entry (demo Screen 5): each
unreflected kindled deed (newest first), then the unsettling resonance, then the Mire the writer carries
for a Sinner (a `burden` option, "The Mire you carry for Ysmay"), as pills; picking a pressed pill again
clears it. The choices follow the kind of the picked option and come from one place, `choicesFor(option)`
in `reflection.ts`, so the pose composer and the journal editor cannot drift: Embrace and Disown for a
deed or the unsettling resonance (and while nothing is picked), Absolve, Condemn and Succumb for a
burden. `pickOption` drops a choice the new pick does not take. A target without a choice, or a choice
without a target, shows `reflectionIncompleteLine(draft)` ("Choose Absolve, Condemn or Succumb, or clear
them.") and holds the send (`isReflectionIncomplete`); a note says a new reflection replaces a waiting one
when `replaces_waiting` is set. Reads `useReflectionOptions(characterSheetId)`
(`GET /api/magic/reflectables/`, rows `{ kind ('deed' | 'resonance' | 'burden'), id, label,
replaces_waiting }`; a burden's `id` is the Sineater side's tether pk) and renders nothing when there is
nothing to reflect on. State is a `ReflectionDraft` (`reflection.ts`, `NO_REFLECTION` while idle);
`reflectionFields(draft)` gives the `reflect_*` fields a request carries: `reflect_choice` plus exactly
one of `reflect_grant_id` (deed), `reflect_resonance_id` or `reflect_tether_id` (burden). The pose body
(`scenes/queries.ts`) and the journal request (`journals/api.ts`) extend `ReflectionFields` rather than
repeat it. Mounted by `CommandInput` (pose mode, not Commands or companion; a scene pose sends the fields
to `submit-pose`, an out-of-scene one dispatches the registry `pose` action) and by `JournalEntryFields`
(the desk and the composer dialog). A succumbing is a deed in the list, labelled by where it happened.
`AuraReflections` lists deeds and burdens with no reflection waiting under "Not yet reflected on".

### `components/ReachRow.tsx`, `reach.ts` (#5308, #5327)

The optional "Reaching for" row of a pose and of a journal entry: in the `CommandInput` footer (pose
mode) and in `JournalEntryFields` (the desk and the composer dialog). The "Reaching for" pill opens a
select of every resonance from `useResonanceCatalog()` (`GET /api/magic/resonances/`, in her aura or not; rows carry `affinity_name` and `description`), and
the chosen resonance's own `description` shows under it as help text. Once a resonance is chosen,
"Pointing at" lists her recent acts (`useRecordedActs(characterSheetId)`, `GET
/api/magic/recorded-acts/?character_sheet=<id>`, rows `{ id, label, created_at, suggestions[] }`,
newest first, only acts not yet marked) as radios: the act's label, its age (`formatRelativeTime`) and
"Suggested: <Resonance>. <reason>." (the suggestion for the chosen resonance, else the strongest) or
"No resonance suggested.". On a pose the last choice is "Nothing: another player has to endorse it",
chosen to begin with: a resonance alone is a reach, which an endorsement of the pose pays. Pointing at an
act makes the writing a mark that pays when it is posted. A journal entry passes `actRequired`: the
legend reads "Pointing at (required)", there is no "Nothing" choice, and `isReachActMissing(draft)`
(`isReachUnfinished` on the journal's fields value) holds Post entry until an act is chosen, because no
one can endorse a journal entry. In an ephemeral scene (`SceneDetail.is_ephemeral`, read by
`CommandInput` from the scene query) the act list is replaced by "This scene is ephemeral and stores nothing, so a mark here pays nothing. Mark the act later, in a pose in another scene or from a journal entry." and no acts are read.

State is a `ReachDraft` (`{ on, resonanceId, actId }`, `NO_REACH` while idle); `reachFields(draft)` gives
`reach_resonance_id`, plus `reach_act_id` when an act is chosen, and nothing while the row is off or
unchosen. `chooseAct` points the draft at an act (null for nothing). The pose body (`scenes/queries.ts`)
and the journal request (`journals/api.ts`) extend `ReachFields`. A scene pose sends the fields to
`submit-pose`; a pose outside a scene goes through the socket `pose` action. The REST pose response
carries `mark_line` and `mark_recorded`; the action result carries `data.mark_recorded` (and the line in
`data.mark_line`, else the last line of the message); the journal's 201 carries `mark_line`. A mark that
paid is a private feed note on the writer's own feed (toast on a journal); one that paid nothing
(`mark_recorded` false) is an error toast with the reason and what to do next, and the pose still posted.
`useRefreshRecordedActs(characterSheetId)` re-reads the list once a pose or entry is sent. The row clears
when the pose lands. An `Interaction` carries `reached_resonance`; `EndorsementControl` then shows one
"Endorse their X" button and sends no resonance. A live frame goes out before the reach is written and
lacks the field; the ids-only `interaction_changed` frame refetches the row. The entry-flourish dialog
lists the whole catalog, the resonances the character holds first.

**Local types standing in for generated ones** (swap for `components['schemas'][...]` after
`just gen-api-types`): `RecordedAct` and `RecordedActSuggestion` in `types.ts`; `ActMark` and
`PendingPick` in `scenes/types.ts`; `SceneDetail.is_ephemeral`. Claiming is gone (#5327): no claim row,
no `claiming.ts`, no "N waiting" line on `KindledResonancesPanel` (the "waiting for your anima ritual"
line stays).

### `components/SineatingRow.tsx` (#5177)

The optional "Sineating" row of a pose, beside "Reflecting on" in the `CommandInput` footer (pose mode
in an active scene: it needs `sceneId` and `personaId`, and reads `useSineatingOptions`, polled). One pill
per option: "Ask Corvin to take on your sins" (`role: 'entreat'`, the Sinner's plea) or "Take on Ysmay's
sins" (`role: 'perform'`, a plea waiting for the writer to answer), each with the tether's resonance.
A plea waiting for the writer badges the row "Plea waiting" and its pill has a Decline button
(`useDeclineSineating`, the line comes back as a toast). Picking an option shows Units pills 1 to
`max_units`, preselected at `max_units`. The draft is a `SineatingDraft` (`sineating.ts`, `NO_SINEATING`
while idle); `sineatingFields(draft)` gives the three fields the pose body carries: `sineating_role`,
`sineating_partner_id` (the other character's sheet id), `sineating_units`. A pose carries a Sineating or
a reflection, never both: `CommandInput` clears one when the other is picked. The pose response carries
`sineating_line` (lines joined by a newline) and `sineating_recorded`; each line is shown to the writer
alone as a system note in the feed, or as an error toast when not recorded. A refusal before posting is
400 `{detail}`: the pose is not posted, the toast shows `detail` and the typed pose and the pick stay. A
pick whose option leaves the polled list (answered, declined) is dropped. The old inbox, request dialog
and the request and respond routes are gone; `GET /api/magic/soul-tether/sineating/pending/` still
exists and has no web caller. Tests: `components/SineatingRow.test.tsx`, and the "Sineating" block of
`game/components/CommandInput.test.tsx`.

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

**One rule for a click, `axisSelection.ts` (#5193).** `nextAxisSelection(axisTags,
selectedTagIds, clickedTagId, multi)` returns an axis's picks after a click, and both
mounts call it (`GlimpseFlow` here, `GlimpseAxes` in character creation): a click on a
picked tag lets it go, an axis that takes one answer swaps, an axis that takes several
adds, and a tag whose `stands_alone` is true (staff tick it in admin; Fugue in The
Reflection is the first) replaces every other pick of its axis, while picking another
tag lets it go. The server refuses a stand-alone tag beside another
(`set_glimpse_tags`), so never write a second copy of this rule in a component.

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

9 unit tests (mocks `../queries`, no msw). Covers: bindings grouped by resonance; empty-bindings message; unbind fires
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

### The rite of settling and the open chance to atone (#4733, #5123, #5124)

A deed in the main affinity in a live scene opens the character's one chance to atone, which stays open
until the rite spends it. The character writes reflections (the "Reflecting on" row) and one rite of
settling carries them all out. Nothing settles with a click: the Accept and Atone sections, the in-scene
gate and its strip are gone.

**Wire contract** (generated types, re-exported in `types.ts`):

- `getSettlingRite(characterSheetId)` - GET `/api/magic/settling-rite/?character_sheet=<id>` ->
  `SettlingRiteReading` `{ reflections[], offerings[], rite_ready, not_ready_message, check_name }`.
  A reflection is `{ id, choice ('EMBRACE' | 'DISOWN' | 'ABSOLVE' | 'CONDEMN' | 'SUCCUMB'), kind ('deed' |
'resonance' | 'burden'), title ("Disown your Domination", "Absolve the Mire you carry for Ysmay"), where ('"The collar" · journal' / 'Pose in The Quarry'), from_line ('from your journal,
"The collar"'), excerpt, effect_line }`; an offering is `{ item_id, name, mode ('material' | 'facet' |
'keepsake'), resonance_name, focus_bonus }`. Owner only (404 for anyone else's character).
- `performSettlingRite({ character_sheet_id, component_ids })` - POST the same URL ->
  `SettlingRiteResult` `{ outcome_name, success_level, focus_bonus, lines[] }`. A refusal is 400 `{detail}`
  (no reflection waiting, no qualifying offering, an item not carried, the rite not set up), thrown by
  `readErrorDetail` so the dialog shows `error.message`.
- `getPendingDriftConversionOffers()` - GET `/api/magic/drift-correction/pending/` ->
  `PaginatedDriftConversionOfferList`; one offer per character `{ id, scene_id, character_id, caps[] }`, a
  cap `{ target_resonance {id, name, affinity}, cap_remaining }`.

**Hooks:** `useSettlingRite(characterSheetId, enabled?)`, `usePerformSettlingRite()` (invalidates the
reading, the pending chance, `reflectionOptionsAll`, `characterResonanceList`, the auras and
`['character-sheets']`), `usePendingDriftConversionOffers(enabled?)` (read, not polled).

**Components:** `AuraReflections` (the sheet's aura card, owner only: "Your reflections" as
`<where> · <title>`, one "Settle your aura" button shown only while a reflection waits, "Not yet reflected
on" with the unreflected deeds and burdens and `atoneChanceLine`'s "A chance to atone is open: up to 3 toward Fury.";
renders nothing with nothing to list) and `SettleAuraDialog` (Screen 6: "Settling your aura", each
reflection's title, quoted excerpt with its `from_line` and effect line, an "Offering" pill per carried
item that counts (`offeringLabel`: "Iron collar · a keepsake of Fury"; a lone one is the choice), the roll
line ("Roll: Composure, +2 from your worn focus. ..." with the bonus only when above 0), the server's
refusal in an alert, "Not now" and "Perform the rite"; after it runs, the outcome and one line per
reflection with a Close button; `not_ready_message` replaces the offering when staff have not set the
rite up). Props `{ characterSheetId, open, onOpenChange }`: it reads and performs for that one
character. The feed offers the same dialog: `CommandInput`'s toast for a recorded reflection carries a
"Settle your aura" action, and a reflection that posts but is not recorded shows an error toast
(`reflection_recorded` false, on the REST pose and on the pose action's result `data`). Words live in
`riteText.ts`. Tests that mock `@/magic/queries` wholesale must add `useSettlingRite`,
`useReflectionOptions`, `usePendingDriftConversionOffers` and `usePerformSettlingRite`
(`SpellbookTab.test.tsx` does).

## Data Flow

- **GET soul-tether detail:** `useSoulTetherDetail(relationshipId)` → `SoulTetherDetail`
  — shows Hollow state, corruption stage, lifetime helped, and `mire`: `[{ sinner_sheet_id,
sinner_name, rows: [{ resonance_name, amount, label }], total }]`, the Mire the viewer carries for
  that Sinner. The backend fills it only when the viewer plays the Sineater side (a Sinner gets `[]`), and
  answers 404 to anyone who plays neither side of the bond. `SoulTetherStatusPanel` draws each entry under
  the Hollow bar as "The Mire you carry for Ysmay" with its total, then one line per row.
- **Sineating:** the Sinner attaches a plea to a pose (`SineatingRow`, role `entreat`) → the Sineater's
  `useSineatingOptions` poll lists it (role `perform`) → the Sineater attaches the ritual to a pose, or
  declines (`useDeclineSineating`). Nothing is sent outside a pose.
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
  - `SineatingOptionSerializer` → `SineatingOption`
  - `SineatingDeclineSerializer` → `SineatingDeclineRequest`
  - `RescueOutcomeSerializer` → `RescueOutcome`
  - `StageAdvanceBonusResultSerializer` → `StageAdvanceBonusResult`
  - `PendingStageAdvanceOfferSerializer` → `PendingStageAdvanceOffer`
- **Consumers (Phase 3 Tasks 3.2–3.7):** SoulTetherPanel, StageAdvanceInbox, RescueDialog,
  DissolveDialog; the Sineating row of the pose composer (#5177)

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

**`units_committed=0` is a decline.**
`useRespondToStageAdvance` accepts 0 as a valid input — it signals decline (not an error). The
returned result will have `declined: true`. A Sineating plea is declined through
`useDeclineSineating`, not with zero units.

**`CharacterResonance[]` (not paginated).**
The `GET /api/magic/character-resonances/` response is a bare array, not a paginated object.
`useCharacterResonances().data` is `CharacterResonance[]`, not `PaginatedList`.

**Path param is `relationship_id`, not a soul-tether id.**
`useSoulTetherDetail(relationshipId)` takes a `CharacterRelationship` PK. Either the Sinner's
or the Sineater's directional row PK is accepted by the backend.
