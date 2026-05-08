# Thread Spending UI Design

**Date:** 2026-05-08
**Status:** Approved (autonomous-mode design conversation)
**Related:**
- `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` — Thread + currency pivot (the source-of-truth for what these models do)
- `docs/superpowers/specs/2026-05-07-anima-ritual-ui-design.md` — most recent Ritual surface; established `RitualPerformView`-as-dispatch and per-anchor field renderers
- `src/world/magic/services/threads.py` — `weave_thread`, `cross_thread_xp_lock`, `accept_thread_weaving_unlock`, imbue prospect helpers
- `src/world/magic/services/resonance.py` — `spend_resonance_for_imbuing`, `spend_resonance_for_pull`, `preview_resonance_pull`
- `src/world/magic/views.py` — `ThreadViewSet`, `RitualPerformView`, `ThreadPullPreviewView`, `ThreadWeavingTeachingOfferViewSet`
- `frontend/src/magic/components/ThreadList.tsx` — existing read-only list to absorb
- `frontend/src/rituals/components/RitualPerformDialog.tsx` — pattern reference for forms-from-input-schema dispatch

---

## Goal

Make the Thread system playable in the React frontend. Resonance currency already flows in via Spec C surfaces (endorsements, residence trickle); the spending side is gone-dark. Players need to:

1. **See** their threads, balances, and prospects (what's ready to imbue, what's blocked, what's near an XP-lock boundary).
2. **Imbue** — spend resonance to advance a thread's level.
3. **Pay XP** at locked level boundaries (20, 30, 40...).
4. **Weave** new threads on anchors they're eligible for.
5. **Acquire** new ThreadWeavingUnlocks (accept teaching offers).
6. **Pull** threads to apply effects to an action (ephemeral RP first; combat-ready dialog component).
7. **Manage** threads — rename, soft-retire.

This is the first full management surface for a major Spec A model family. It sets the pattern for similar later work (covenant-role Thread management UI, facet-Thread management UI when those land in player flows).

## Background

### What exists today

**Models (all in `world.magic.models.threads`):**

- `Thread` (discriminator + typed-FK; owner, resonance, target_kind, target_*, name, description, level, developed_points, hollow_current, retired_at)
- `ThreadLevelUnlock` — per-thread XP-locked-boundary receipt
- `ThreadPullCost` — per-tier tuning (resonance_cost, anima_per_thread)
- `ThreadXPLockedLevel` — global level-boundary price list
- `ThreadPullEffect` — authored tier-0..3 effect templates (FLAT_BONUS, INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT, NARRATIVE_ONLY, CORRUPTION_RESISTANCE)
- `ThreadWeavingUnlock` — authored "you can weave threads on X" unlocks
- `CharacterThreadWeavingUnlock` — per-character purchase record
- `ThreadWeavingTeachingOffer` — teacher-side offer (FK RosterTenure + Unlock)

**Services:**

- `weave_thread(character_sheet, target_kind, target, resonance, *, name, description) -> Thread` — eligibility + create
- `update_thread_narrative(thread, *, name, description) -> Thread` — rename/redescribe
- `spend_resonance_for_imbuing(character_sheet, thread, amount) -> ThreadImbueResult` — per-tier imbue with `blocked_by` enum (NONE, INSUFFICIENT_BUCKET, XP_LOCK, PATH_CAP, ANCHOR_CAP)
- `cross_thread_xp_lock(character_sheet, thread, boundary_level) -> ThreadLevelUnlock` — pay XP at a boundary
- `compute_path_cap(character_sheet)`, `compute_anchor_cap(thread)`, `compute_effective_cap(thread)`
- `imbue_ready_threads(character_sheet) -> list[Thread]`
- `near_xp_lock_threads(character_sheet, within=100) -> list[ThreadXPLockProspect]`
- `threads_blocked_by_cap(character_sheet) -> list[Thread]`
- `compute_thread_weaving_xp_cost(unlock, learner) -> int`
- `accept_thread_weaving_unlock(learner, offer) -> CharacterThreadWeavingUnlock`
- `preview_resonance_pull(character_sheet, resonance, tier, threads, *, combat_encounter=None) -> PullPreviewResult`
- `spend_resonance_for_pull(character_sheet, resonance, tier, threads, action_context) -> ResonancePullResult`

**API:**

- `GET/POST/PATCH/DELETE /api/magic/threads/` — `ThreadViewSet`. DELETE is soft-retire.
- `GET /api/magic/character-resonances/` — `CharacterResonanceViewSet`. Returns full balance/lifetime/flavor per resonance the character has.
- `POST /api/magic/rituals/perform/` — `RitualPerformView`. Imbuing is a SERVICE-dispatched Ritual (`Rite of Imbuing`, `service_function_path = "world.magic.services.spend_resonance_for_imbuing"`); `thread_id` is resolved server-side from kwargs into a Thread instance before dispatch.
- `POST /api/magic/thread-pull-preview/` — read-only preview, accepts `thread_ids[]`, `tier`, optional `action_context` (with `combat_encounter_id`).
- `GET /api/magic/teaching-offers/` — `ThreadWeavingTeachingOfferViewSet` (read-only).

**Frontend:**

- `frontend/src/magic/components/ThreadList.tsx` — minimal read-only list (5 fields displayed). Currently the only Thread surface.
- `frontend/src/magic/queries.ts` — has `useThreads()`, `useCharacterResonances()`.
- `frontend/src/magic/api.ts` — has `getThreads()`, `getCharacterResonances()`.
- `frontend/src/rituals/` module — established Ritual perform pattern, including a generic `RitualPerformDialog` that renders a form from `Ritual.input_schema`. Has `IntField`, `TextField`, `SelectField`, `ResonancePickerField`, `ScenePickerField`, `RelationshipCapstonePickerField`, `CharacterSearchField`, `UnknownFieldFallback`.

### What's missing

- **No commit endpoint for `spend_resonance_for_pull`.** Only the preview is exposed.
- **No accept endpoint for `accept_thread_weaving_unlock`.** Service exists; no view.
- **No endpoint for `cross_thread_xp_lock`.** Service exists; no view.
- **No frontend management surface beyond the read-only list.** No detail view, no imbue UI, no weave wizard, no pull dialog, no teaching-offer browse.
- **No frontend route for threads.** The user has to navigate via `/rituals` to perform Imbuing today, but the current generic ritual form has no `ThreadPickerField`, so even that path doesn't actually work yet.

## Scope

**In scope:**

1. `/threads` Thread Hub page — currency balances, thread list with state, filters, "Weave New" entry.
2. `/threads/:id` Thread Detail page — narrative, stats, imbue panel, XP-lock boundary panel, pull effect preview (per tier), pull commit (ephemeral RP), rename, retire.
3. Weave New Thread wizard — modal flow from the hub.
4. `/threads/teaching` Weaving Teaching Offers page — browse + accept teacher offers.
5. **Backend additions** to plug API gaps:
   - `POST /api/magic/threads/{id}/cross-xp-lock/` — `ThreadCrossXPLockView`.
   - `POST /api/magic/teaching-offers/{id}/accept/` — extend `ThreadWeavingTeachingOfferViewSet` with an `accept` action.
   - `POST /api/magic/thread-pull-commit/` — `ThreadPullCommitView` (covers both ephemeral and combat modes via optional encounter context).
   - `Ritual.client_hosted` boolean flag, exclude such rituals from the generic `/rituals` list.
6. ThreadPullDialog component — a reusable component, ephemeral-mode triggered from the hub/detail. Its API accepts an optional encounter/participant tuple so the future combat panel can mount it unchanged.

**Out of scope (explicit deferrals):**

- **Combat panel UI.** No `frontend/src/combat/` exists today. Mounting `ThreadPullDialog` in a combat panel is a future spec — this work designs the dialog to accept combat context but does not ship a combat-side host.
- **Teacher-side offer creation UI.** Teachers create `ThreadWeavingTeachingOffer` rows via service/admin paths today; a player-facing teacher-side authoring UI is a separate concern (mirrors codex teaching offers, which also lacks a frontend authoring UI).
- **Per-pull anchor-in-action involvement editor.** Ephemeral pulls require `involved_traits/techniques/objects` tuples for the anchor-in-action gate. v1 ephemeral pulls only allow threads of `RELATIONSHIP_TRACK`, `RELATIONSHIP_CAPSTONE`, `FACET`, and `COVENANT_ROLE` kinds (the always-in-action set per `_ALWAYS_IN_ACTION_KINDS` in `services/resonance.py`); TRAIT/TECHNIQUE/ROOM threads can only pull from a combat context where the action substrate provides the involvement tuples. (When the combat panel ships, it'll have the action declaration data to pre-populate these.) The dialog must clearly disable / explain TRAIT/TECHNIQUE/ROOM threads in ephemeral mode.
- **Rituals-page Imbuing path.** Adding a `ThreadPickerField` to the generic ritual form to make imbuing work via `/rituals` is unnecessary churn — the dedicated thread-detail hosting is the correct UX. Imbuing rituals are simply hidden from `/rituals` (via the new `client_hosted` flag).
- **Pull-effect aggregator across rounds.** No rolling history of past pull commits. The current-action preview is enough.
- **Bulk operations.** No multi-select retire, no batch imbue. One thread at a time.

## Design Decisions

### 1. New top-level route `/threads`

Threads are a sufficiently large management surface (multiple sub-pages, multi-step wizards, cross-references with rituals/combat) that they warrant their own route family rather than a section of `/rituals`.

```
/threads                  → ThreadHubPage
/threads/:id              → ThreadDetailPage
/threads/teaching         → WeavingTeachingOffersPage
```

Wired in `frontend/src/App.tsx` as protected routes (require authenticated character). Sidebar/menu link on the Magic submenu, alongside `/rituals`.

### 2. Frontend module placement: extend `frontend/src/magic/`

All new components, pages, hooks, and types live in the existing `frontend/src/magic/` module rather than creating a sibling `frontend/src/threads/` module. Rationale:

- `ThreadList` and the magic queries already live in `magic/`.
- Threads are conceptually a magic system — their currency is `CharacterResonance`, their effects are `ThreadPullEffect` keyed by `Resonance`.
- Splitting would require duplicating `ResonancePickerField` or cross-importing it.

Internal organization adds a `magic/components/threads/` subdirectory and a `magic/pages/` subdirectory:

```
frontend/src/magic/
├── api.ts                                      # extended
├── queries.ts                                  # extended
├── types.ts                                    # extended
├── components/
│   ├── ThreadList.tsx                          # rewritten as ThreadCard-based
│   ├── HollowBar.tsx                           # unchanged
│   ├── ...soul-tether components               # unchanged
│   └── threads/                                # NEW
│       ├── ThreadCard.tsx
│       ├── ThreadStateBadge.tsx
│       ├── ResonanceBalanceCard.tsx
│       ├── ImbuePanel.tsx
│       ├── XPLockBoundaryPanel.tsx
│       ├── PullEffectPreview.tsx
│       ├── ThreadPullDialog.tsx
│       ├── ThreadRenameDialog.tsx
│       ├── ThreadRetireDialog.tsx
│       ├── WeaveThreadWizard.tsx
│       ├── AnchorPickerStep.tsx                # wizard substep
│       ├── ResonancePickerStep.tsx             # wizard substep
│       ├── NarrativeStep.tsx                   # wizard substep
│       ├── TeachingOfferCard.tsx
│       └── AcceptOfferDialog.tsx
└── pages/                                      # NEW
    ├── ThreadHubPage.tsx
    ├── ThreadDetailPage.tsx
    └── WeavingTeachingOffersPage.tsx
```

### 3. Thread Hub layout

`ThreadHubPage` is two stacked sections:

```
┌─────────────────────────────────────────────────────────────┐
│ Header: "Your Threads"            [Weave New]  [Browse Teachers] │
├─────────────────────────────────────────────────────────────┤
│ Resonance Balances                                          │
│  ┌─────┐ ┌─────┐ ┌─────┐ ...   (one card per claimed res)   │
│  │ Res │ │ Res │ │ Res │                                    │
│  │ bal │ │ bal │ │ bal │                                    │
│  │ lifetime │ │ lifetime │                                  │
│  └─────┘ └─────┘ └─────┘                                    │
├─────────────────────────────────────────────────────────────┤
│ Threads (grouped by anchor kind)                            │
│  ▾ Trait (3)                                                │
│   ┌─ ThreadCard ──────────────────────────────────────────┐ │
│   │ Name, badge(target_kind), level/cap, dev_points,      │ │
│   │ resonance, state(ready/blocked/near-boundary)         │ │
│   │ →click opens ThreadDetailPage                         │ │
│   └───────────────────────────────────────────────────────┘ │
│  ▾ Technique (2)                                            │
│  ▾ Relationship Track (1)                                   │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

Group headers are collapsible. Empty kinds are hidden. Threads with `state=ready_to_imbue` get a small green dot; `state=near_xp_lock` orange; `state=blocked_by_cap` grey; otherwise neutral.

State derivation is client-side from the data available:
- `ready_to_imbue` ↔ thread appears in the `imbue_ready_threads` payload (new endpoint, see §10).
- `near_xp_lock` ↔ thread appears in the `near_xp_lock_threads` payload.
- `blocked_by_cap` ↔ thread appears in the `threads_blocked_by_cap` payload.

We expose these via a single new aggregate endpoint (§10), not three round-trips.

### 4. Thread Detail page

`ThreadDetailPage` (`/threads/:id`) is a vertical layout of cards:

```
┌─────────────────────────────────────────────────────────────┐
│ Breadcrumb: Threads / {name or "(unnamed)"}                 │
│ Title: name editable inline → ThreadRenameDialog            │
│ Subtitle: target_kind badge + anchor display name           │
│ Description block (editable)                                │
├─────────────────────────────────────────────────────────────┤
│ Stats card                                                  │
│  Level: 12 / 20 (effective cap)                             │
│  Path cap: 20  Anchor cap: 25  Binding: PATH                │
│  Developed points: 350 / 600 to next level                  │
│  Resonance: {affinity-tinted name} | Balance: 142           │
├─────────────────────────────────────────────────────────────┤
│ Imbue panel (only if not retired and not at cap)            │
│  Amount: [stepper 1..balance]                               │
│  [Preview] → expand to show levels gained, blocked_by       │
│  [Confirm Imbue]                                            │
│                                                             │
│  Or: blocked-by callouts                                    │
│  - blocked_by=XP_LOCK → render XPLockBoundaryPanel inline   │
│  - blocked_by=PATH_CAP → "Advance your Path to raise this"  │
│  - blocked_by=ANCHOR_CAP → kind-specific guidance           │
├─────────────────────────────────────────────────────────────┤
│ XP Lock Boundary panel (only if level%10==0 boundary blocks)│
│  "Crossing level 20 requires 5 XP."                         │
│  Available XP: 18.   [Pay XP to Cross]                      │
├─────────────────────────────────────────────────────────────┤
│ Pull Effect Preview                                         │
│  Tier selector: [1 / 2 / 3]                                 │
│  Cost: 6 resonance + 0 anima (1 thread, +N more would add)  │
│  Resolved effects:                                          │
│    - tier 0 passive (always-on): VITAL_BONUS +12 max_health │
│    - tier 1: INTENSITY_BUMP +20                             │
│    - tier 2: NARRATIVE_ONLY "..."                           │
│    - tier 3: CAPABILITY_GRANT [Capability name]             │
│  [Pull Now (RP)] (disabled in ephemeral mode if anchor not  │
│      always-in-action; tooltip explains why)                │
├─────────────────────────────────────────────────────────────┤
│ Footer                                                      │
│  [Retire Thread]  (red-tinted, opens ThreadRetireDialog)    │
└─────────────────────────────────────────────────────────────┘
```

The pull preview lives on the detail page (single-thread context). The multi-thread pull dialog (`ThreadPullDialog`, §6) is its own surface, opened from the hub or future combat panel.

### 5. Weave New Thread wizard

Triggered from the hub's `[Weave New]` button. Multi-step modal:

**Step 1 — Pick anchor kind.** Show one button per `TargetKind` value, *only* the kinds for which the character has either:

- A `CharacterThreadWeavingUnlock` row (for trait/technique/room/relationship-track/relationship-capstone/facet) — `weave_thread` will validate this.
- Active or past covenant role membership (for `COVENANT_ROLE` — `weave_thread` validates this via `has_ever_held`).

Disabled kinds show a tooltip: "Acquire a Thread Weaving Unlock for [trait/technique/...] first." Link to `/threads/teaching`.

To drive this, the wizard reads a new `eligibility` payload from the hub-data endpoint (§10) that lists each kind and a flag for whether the character has the prerequisite unlock(s) for *any* anchor of that kind.

**Step 2 — Pick anchor.** Conditional on kind:

- `TRAIT` → list traits the character has (from `CharacterTraitValue.value > 0`); display as searchable select; show only traits matched by the character's `unlock_trait` rows.
- `TECHNIQUE` → list techniques the character knows (via `CharacterTechnique`); show only those whose gift is in the unlock's `unlock_gift` set.
- `ROOM` → list rooms that have at least one Property in the character's unlock's `unlock_room_property` set. **No room-search-by-property endpoint exists today** — this work adds `GET /api/magic/rooms-by-property/?property_id=<int>[&property_id=<int>...]` returning rooms (`ObjectDB`) bearing any of the specified properties. View: `RoomsByPropertyView(APIView)`. The frontend resolves the unlock's `unlock_room_property` set client-side from the unlock data, then issues a single query with all property IDs.
- `RELATIONSHIP_TRACK` → list `RelationshipTrackProgress` for the character whose `track` is in the unlock's `unlock_track` set.
- `RELATIONSHIP_CAPSTONE` → list `RelationshipCapstone` rows for the character on tracks the character has unlocks for.
- `FACET` → list facets that match any of the character's worn-item facets (or, more permissively, all facets the player can browse).
- `COVENANT_ROLE` → list the character's ever-held `CovenantRole` rows.

Each picker uses an inline `<Select>` or `<Combobox>`; rooms and traits use search.

**Step 3 — Pick resonance.** Searchable select over the character's `CharacterResonance` rows (any claimed resonance is eligible — the spec doesn't constrain weaving to balance > 0). Show resonance affinity tint and current balance.

**Step 4 — Narrative.** Optional `name` (CharField max 120) and `description` (TextField). Both default empty; the spec allows empty. Help text encourages naming for personal narrative reference.

**Step 5 — Confirm.** Display a summary card with all four selections; `[Weave]` button posts to `POST /api/magic/threads/`. On success, navigate to `/threads/{id}` (the detail page for the new thread).

The wizard is implemented as a single component with internal step state; it does NOT use react-router subroutes (modal state is ephemeral).

### 6. Thread Pull Dialog

`ThreadPullDialog` is the multi-thread pull commit surface. Two modes via props:

```ts
interface ThreadPullDialogProps {
  characterSheetId: number;
  open: boolean;
  onClose: () => void;
  // Combat mode: provided by combat panel when it ships
  combat?: { encounterId: number; participantId: number; involvedTraitIds: number[];
             involvedTechniqueIds: number[]; involvedObjectIds: number[]; };
  // Ephemeral default (when combat omitted)
}
```

In ephemeral mode (no `combat` prop), the dialog filters the character's threads to the always-in-action kinds (`RELATIONSHIP_TRACK`, `RELATIONSHIP_CAPSTONE`, `FACET`, `COVENANT_ROLE`). Other kinds show with a disabled-eligibility chip — "requires combat context" — so the player understands why they're greyed.

In combat mode, all kinds are eligible; the dialog uses `combat.involved*` tuples to mark TRAIT/TECHNIQUE/ROOM threads as eligible only when their anchor is in the involved set.

**Dialog layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Pull Threads                                                │
│ ─────────────────────────────                               │
│ Resonance: [select — only resonances where character has ≥1 │
│             pulldown-eligible thread, with balance > 0]     │
│ Tier: [○ 1 ○ 2 ○ 3]                                         │
│                                                             │
│ Threads (filtered to selected resonance + eligibility):     │
│  ☐ {ThreadCard with checkbox} ...                           │
│                                                             │
│ Cost: 6 resonance + 4 anima (3 threads selected, tier 2)    │
│ Affordable: ✓                                               │
│                                                             │
│ Resolved Effects:                                           │
│  - Per-thread × per-tier breakdown (from preview)           │
│  - Inactive (greyed) effects flagged with reason            │
│  - Capped intensity warning if applicable                   │
│                                                             │
│ [Cancel]  [Commit Pull]                                     │
└─────────────────────────────────────────────────────────────┘
```

Live preview: every change to thread selection / tier / resonance debounces a `POST /api/magic/thread-pull-preview/` so the cost + resolved effects panel stays current.

Commit posts to the new `POST /api/magic/thread-pull-commit/` endpoint (§10).

### 7. Weaving Teaching Offers page

`WeavingTeachingOffersPage` (`/threads/teaching`) browses available teaching offers. Layout:

```
┌─────────────────────────────────────────────────────────────┐
│ Header: "Thread Weaving Teaching Offers"   [Filter by kind] │
├─────────────────────────────────────────────────────────────┤
│ TeachingOfferCard rows:                                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Teacher: {tenure display name}                        │  │
│  │ Unlock: "Weave threads on Trait: Persuasion"          │  │
│  │ Pitch: {teacher's authored pitch}                     │  │
│  │ Cost: 8 XP (in-Path) | 24 XP (out-of-Path) ✗ blocked  │  │
│  │ Gold: 250                                             │  │
│  │ [Accept Offer]                                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

XP cost is computed server-side via a new `effective_xp_cost_for_viewer` SerializerMethodField on `ThreadWeavingTeachingOfferSerializer`. The field resolves the learner using the existing `_resolve_actor_sheet`-style alt guard:

- Single active tenure → use that sheet, return `compute_thread_weaving_xp_cost(unlock, learner)`.
- Multiple active tenures **without** an explicit `learner_sheet_id` query param → return `null` (the UI shows a "select character" prompt and re-fetches with the chosen pk).
- No active tenures (e.g., staff browsing without an active character) → return `null`.

Returning `null` (rather than raising) keeps the list endpoint usable for browsing; the accept endpoint enforces the alt guard at write time.

`[Accept Offer]` opens `AcceptOfferDialog` — a confirm with a final cost summary. On confirm, posts to the new `POST /api/magic/teaching-offers/{id}/accept/` (§10). On success, invalidates `useTeachingOffers()` and `useCharacterUnlocks()` query caches.

### 8. Hide Imbuing rituals from `/rituals`; specialized host posts kwargs directly

Imbuing is a SERVICE-dispatched Ritual, but it has a specialized host (Thread Detail page). Listing it on `/rituals` would be misleading — players would click "Perform" and find the form has no `ThreadPickerField` available.

**Approach:** Add `Ritual.client_hosted: BooleanField(default=False)`. Set `True` on the Imbuing factory. The `RitualsListPage` filters out client-hosted rituals.

This is more durable than a service-path string match because future SERVICE rituals (the eventual Pulling-as-ritual, divinations, bindings) can opt into the same behavior with a single flag flip.

**Imbuing dispatch path — does not use `input_schema`.** The existing `ImbuingRitualFactory` does not author an `input_schema`, and this work does not add one. The Thread Detail page's `ImbuePanel` posts to `POST /api/magic/rituals/perform/` directly with hand-built kwargs (`{ ritual_id, character_sheet_id, kwargs: { thread_id, amount } }`); it does not introspect any schema. The schema-driven `RitualPerformDialog` renderer in `frontend/src/rituals/` is bypassed entirely for this path. (`RitualPerformView` already supports this — it accepts kwargs as primitives and resolves `thread_id` → Thread server-side.) When the time comes to surface a generic Imbuing form on `/rituals`, an `input_schema` can be added then; not needed for v1 because `client_hosted=True` keeps it off that page.

### 9. Manage operations: rename, retire

**Rename** is inline-editable on the detail page title; calling `update_thread_narrative` via PATCH on `/api/magic/threads/{id}/` with `name`/`description` body. `ThreadSerializer` already declares both fields without `read_only=True`, so DRF's default `partial_update` flow accepts them; no serializer changes needed.

**Retire** opens `ThreadRetireDialog` — a hard-confirm. "Retired threads stop pulling and never grant passive effects. They remain in your history. This cannot be undone." On confirm, posts `DELETE /api/magic/threads/{id}/`. Existing soft-retire path. After success, navigate back to `/threads`.

### 10. Backend additions

Three new endpoints + one model field:

#### 10.1 `GET /api/magic/thread-hub-summary/`

Single aggregate endpoint to back the Thread Hub. Returns:

```json
{
  "balances": [ {"resonance_id": 7, "balance": 142, "lifetime_earned": 480, "flavor_text": "..."} ],
  "ready_thread_ids": [12, 18, 41],
  "near_xp_lock_thread_ids": [{"thread_id": 12, "boundary_level": 20, "xp_cost": 5, "dev_points_to_boundary": 80}],
  "blocked_thread_ids": [33],
  "weaving_eligibility": {
      "TRAIT": true, "TECHNIQUE": false, "ROOM": false,
      "RELATIONSHIP_TRACK": true, "RELATIONSHIP_CAPSTONE": true,
      "FACET": false, "COVENANT_ROLE": true
  }
}
```

Drives prospect dots, "Weave New" enable state, and the resonance balance row in one round-trip. View: `ThreadHubSummaryView(APIView)` posted at `path("thread-hub-summary/", ...)`. Reuses the existing `imbue_ready_threads`, `near_xp_lock_threads`, `threads_blocked_by_cap` services and a small new `_weaving_eligibility(character_sheet) -> dict[str, bool]` helper.

The `near_xp_lock_thread_ids` payload mirrors the existing `ThreadXPLockProspect` dataclass field-for-field (`thread_id`, `boundary_level`, `xp_cost`, `dev_points_to_boundary`); the service already computes the delta to the next boundary so the view does no arithmetic.

The thread *list itself* is fetched separately via the existing `GET /api/magic/threads/` ViewSet (paginated). The summary endpoint only returns small ID-and-prospect data for state derivation.

#### 10.2 `POST /api/magic/threads/{id}/cross-xp-lock/`

Implemented as a `@action(detail=True, methods=["post"])` named `cross_xp_lock` on `ThreadViewSet` (not a separate APIView). Single implementation path, no ambiguity:

```python
@action(detail=True, methods=["post"])
def cross_xp_lock(self, request, pk=None):
    thread = self.get_object()  # IsThreadOwner enforces ownership
    serializer = CrossXPLockSerializer(data=request.data, context={"request": request, "thread": thread})
    serializer.is_valid(raise_exception=True)
    unlock = serializer.save()
    return Response({"thread_id": thread.pk, "unlocked_level": unlock.unlocked_level, "xp_spent": unlock.xp_spent})
```

The serializer accepts `boundary_level: int`, calls `cross_thread_xp_lock`. Maps `XPInsufficient`, `InvalidImbueAmount`, `AnchorCapExceeded` to HTTP 400 with `user_message`.

#### 10.3 `POST /api/magic/teaching-offers/{id}/accept/`

Custom action on `ThreadWeavingTeachingOfferViewSet`:

```python
@action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
def accept(self, request, pk=None):
    offer = self.get_object()
    serializer = AcceptTeachingOfferSerializer(data=request.data, context={"request": request, "offer": offer})
    serializer.is_valid(raise_exception=True)
    char_unlock = serializer.save()
    return Response({"id": char_unlock.pk, "unlock_id": char_unlock.unlock_id, "xp_spent": char_unlock.xp_spent})
```

The serializer resolves the learner's `CharacterSheet` via the same alt-guard pattern (`_resolve_actor_sheet` similar to `_resolve_endorser_sheet` already in `views.py`). Calls `accept_thread_weaving_unlock(learner, offer)`. Maps `XPInsufficient` to HTTP 400.

#### 10.4 `POST /api/magic/thread-pull-commit/`

`ThreadPullCommitView` parallels `ThreadPullPreviewView`. Body:

```json
{
  "character_sheet_id": 12,
  "resonance_id": 7,
  "tier": 2,
  "thread_ids": [18, 33, 41],
  "action_context": {
    "combat_encounter_id": null,
    "combat_participant_id": null,
    "involved_trait_ids": [],
    "involved_technique_ids": [],
    "involved_object_ids": []
  }
}
```

Builds a `PullActionContext`, calls `spend_resonance_for_pull`, returns the `ResonancePullResult` serialized (resonance_spent, anima_spent, resolved_effects[]).

Maps `ProtagonismLockedError`, `ResonanceInsufficient`, `InvalidImbueAmount`, `NoMatchingWornFacetItemsError` to HTTP 400 with `user_message`.

#### 10.5 `Ritual.client_hosted` boolean field

Migration adds `client_hosted = models.BooleanField(default=False, help_text="When True, the Rituals listing page hides this ritual; it has a specialized host UI.")`. The Imbuing factory sets it to True. `RitualSerializer` exposes it. `RitualsListPage` filters out `client_hosted=true` rituals client-side.

### 11. Permissions

- All thread-related endpoints require `IsAuthenticated`.
- Thread CRUD requires `IsThreadOwner` (existing).
- `cross_xp_lock` and pull-commit are gated to thread owner via the same path.
- `accept` for teaching offers is the requesting user → resolved learner sheet (alt guard).

### 12. Error handling

All four new endpoints (and the extended Ritual perform path for Imbuing) follow the project pattern: typed exceptions raised in services carry `user_message`; views catch and map to HTTP 400 with `{"detail": exc.user_message}`. No raw `str(exc)` leakage.

Each endpoint's exception map:

| Endpoint | Exceptions |
|----------|------------|
| `POST /threads/{id}/cross-xp-lock/` | `XPInsufficient`, `InvalidImbueAmount`, `AnchorCapExceeded` |
| `POST /teaching-offers/{id}/accept/` | `XPInsufficient` |
| `POST /thread-pull-commit/` | `ProtagonismLockedError`, `ResonanceInsufficient`, `InvalidImbueAmount`, **`NoMatchingWornFacetItemsError`** |
| `POST /rituals/perform/` (Imbuing) | `ResonanceInsufficient`, `AnchorCapExceeded`, `InvalidImbueAmount` (already mapped in `RitualPerformView`) |

`NoMatchingWornFacetItemsError` is in the pull-commit map specifically: a FACET thread can pass ephemeral-mode "always-in-action" gating but still fail at commit if the character has no worn item bearing the matching facet. The dialog must distinguish this (player needs to equip something) from generic resonance/anima shortfall, so the error banner displays the typed `user_message` verbatim — no remapping.

Frontend dialogs surface errors inline (a red banner in the dialog body) rather than toasting, so the player doesn't miss them in the middle of a multi-step action.

### 13. Testing

**Backend:**

- `tests/test_thread_hub_summary_view.py` — auth, prospect lists are accurate, eligibility flags match service.
- `tests/test_thread_cross_xp_lock_view.py` — happy path, XPInsufficient, AnchorCapExceeded, InvalidImbueAmount.
- `tests/test_teaching_offer_accept_view.py` — happy path (in-path + out-of-path), XPInsufficient, alt-guard.
- `tests/test_thread_pull_commit_view.py` — ephemeral happy path, combat happy path, ProtagonismLocked, anchor-not-in-action, ResonanceInsufficient, NoMatchingWornFacetItemsError (FACET thread eligible at validation but no matching worn item).
- Existing `test_api.py` extended for the `client_hosted` filter on RitualSerializer.

**Frontend:**

- `__tests__/queries.test.tsx` extended for new hooks.
- `__tests__/ThreadHubPage.test.tsx` — renders balances + grouped thread list, prospect dots wired correctly.
- `__tests__/ThreadDetailPage.test.tsx` — imbue panel behavior across `blocked_by` states, XP-lock panel appearance.
- `__tests__/WeaveThreadWizard.test.tsx` — step transitions, kind eligibility gating, anchor picker variants, validation.
- `__tests__/ThreadPullDialog.test.tsx` — ephemeral filtering, combat-mode all-kinds, preview debounce, commit error handling.
- `__tests__/WeavingTeachingOffersPage.test.tsx` — list, accept dialog, cost display in/out-of-path.
- `__tests__/RitualsListPage.test.tsx` extended — `client_hosted` rituals are excluded.

**E2E:**

- One Playwright smoke test that loads `/threads`, opens the wizard, weaves a `RELATIONSHIP_TRACK` thread, opens its detail page, imbues it, and confirms the balance dropped. Catches build/route/asset issues; doesn't try to verify every UI permutation.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ /threads (ThreadHubPage)                                     │
│  GET /api/magic/character-resonances/   (existing)           │
│  GET /api/magic/threads/                (existing)           │
│  GET /api/magic/thread-hub-summary/     (NEW)                │
│  Renders ResonanceBalanceCard, grouped ThreadCard list.      │
│  Buttons: Weave New (opens WeaveThreadWizard),               │
│          Browse Teachers (→/threads/teaching)                │
└──────────────────────────────────────────────────────────────┘
           │                                              │
           ▼ click ThreadCard                             ▼ click Weave New
┌──────────────────────────────────────────┐  ┌────────────────────────────┐
│ /threads/:id (ThreadDetailPage)          │  │ WeaveThreadWizard (modal)  │
│  GET  /api/magic/threads/{id}/           │  │  Step 1: Anchor Kind       │
│  POST /api/magic/rituals/perform/        │  │     uses summary endpoint  │
│        (Imbuing)                         │  │  Step 2: Pick Anchor       │
│  POST /api/magic/threads/{id}/cross-xp-  │  │     uses anchor-picker eps │
│        lock/  (NEW)                      │  │  Step 3: Pick Resonance    │
│  POST /api/magic/thread-pull-preview/    │  │  Step 4: Narrative         │
│  POST /api/magic/thread-pull-commit/     │  │  Step 5: Confirm           │
│        (NEW, ephemeral)                  │  │     POST /threads/         │
│  PATCH /api/magic/threads/{id}/          │  │     →redirect /threads/:id │
│  DELETE /api/magic/threads/{id}/         │  └────────────────────────────┘
└──────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ /threads/teaching (WeavingTeachingOffersPage)                │
│  GET /api/magic/teaching-offers/   (existing)                │
│  POST /api/magic/teaching-offers/{id}/accept/  (NEW)         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ ThreadPullDialog (component, mountable from hub or future    │
│ combat panel)                                                │
│  POST /api/magic/thread-pull-preview/  (existing, debounced) │
│  POST /api/magic/thread-pull-commit/   (NEW)                 │
│   ephemeral mode → action_context with all-empty involved_*  │
│   combat mode    → action_context with encounter+participant │
│                    + involved_* tuples from caller           │
└──────────────────────────────────────────────────────────────┘
```

## Components Inventory

### Backend

#### New views (`src/world/magic/views.py`)

- `ThreadHubSummaryView` — GET, returns the summary payload.
- `ThreadPullCommitView` — POST, commits pulls.
- `RoomsByPropertyView` — GET, search rooms (ObjectDB) by `RoomProperty` ids; backs the ROOM-anchor wizard step.
- `cross_xp_lock` action on `ThreadViewSet` — pays XP for a level boundary (decided as `@action`, not a separate APIView; see §10.2).
- `accept` action on `ThreadWeavingTeachingOfferViewSet` — accepts an offer.

#### New serializers (`src/world/magic/serializers.py`)

- `ThreadHubSummarySerializer` — output for the summary endpoint. Fields are simple (lists of ints, list of small dicts for near_xp_lock, dict for eligibility); use a plain `serializers.Serializer` with explicit fields rather than overloading a model serializer.
- `CrossXPLockSerializer` — input + service dispatch + output.
- `AcceptTeachingOfferSerializer` — input + service dispatch + output.
- `ThreadPullCommitRequestSerializer` — input shape mirroring the preview serializer plus participant id.
- `ThreadPullCommitResponseSerializer` — wire shape for `ResonancePullResult`.
- Add `effective_xp_cost_for_viewer` SerializerMethodField to `ThreadWeavingTeachingOfferSerializer`.
- Add `client_hosted` field to `RitualSerializer`.

#### New URL routes (`src/world/magic/urls.py`)

```python
path("thread-hub-summary/", ThreadHubSummaryView.as_view(), name="thread-hub-summary"),
path("thread-pull-commit/", ThreadPullCommitView.as_view(), name="thread-pull-commit"),
path("rooms-by-property/", RoomsByPropertyView.as_view(), name="rooms-by-property"),
```

The viewset actions (`cross_xp_lock` on threads, `accept` on teaching-offers) register automatically via the router.

#### Model migration

- `Ritual.client_hosted: BooleanField(default=False)` — adds non-nullable column with a default; safe migration.
- Imbuing factory in `factories.py` sets `client_hosted=True`.

### Frontend

#### `frontend/src/magic/api.ts` — additions

```ts
// Hub summary
export async function getThreadHubSummary(): Promise<ThreadHubSummary> { ... }

// Mutations
export async function imbueThread(body: ImbueRequest): Promise<ImbueResponse> { ... }   // wraps performRitual
export async function crossXPLock(threadId: number, body: CrossXPLockRequest): Promise<CrossXPLockResponse> { ... }
export async function previewPull(body: PullPreviewRequest): Promise<PullPreviewResponse> { ... }
export async function commitPull(body: PullCommitRequest): Promise<PullCommitResponse> { ... }
export async function weaveThread(body: WeaveThreadRequest): Promise<Thread> { ... }
export async function patchThreadNarrative(threadId: number, body: PatchThreadRequest): Promise<Thread> { ... }
export async function retireThread(threadId: number): Promise<void> { ... }
export async function getTeachingOffers(): Promise<PaginatedTeachingOfferList> { ... }
export async function acceptTeachingOffer(offerId: number): Promise<AcceptTeachingOfferResponse> { ... }
```

#### `frontend/src/magic/queries.ts` — additions

```ts
magicKeys.threadHubSummary = () => [...magicKeys.all, 'thread-hub-summary'] as const;
magicKeys.thread = (id: number) => [...magicKeys.all, 'thread', id] as const;
magicKeys.teachingOffers = () => [...magicKeys.all, 'teaching-offers', 'list'] as const;

export function useThreadHubSummary() { ... }
export function useThread(id: number) { ... }
export function useTeachingOffers() { ... }

export function useImbueThread() { ... invalidates threadHubSummary, threads, thread(id), characterResonances }
export function useCrossXPLock() { ... invalidates threadHubSummary, thread(id) }
export function usePreviewPull() { ... no cache; debounced via useQuery with enabled control }
export function useCommitPull() { ... invalidates threadHubSummary, threads, characterResonances }
export function useWeaveThread() { ... invalidates threadHubSummary, threads }
export function usePatchThreadNarrative() { ... invalidates thread(id), threads }
export function useRetireThread() { ... invalidates threadHubSummary, threads }
export function useAcceptTeachingOffer() { ... invalidates teachingOffers; nothing else (CharacterThreadWeavingUnlock not currently surfaced) }
```

#### `frontend/src/magic/types.ts` — additions

Re-exports of new generated request/response types where available; local types where the backend uses non-`ModelSerializer` shapes.

#### Components — see directory listing in §2.

#### Pages

- `ThreadHubPage.tsx`
- `ThreadDetailPage.tsx`
- `WeavingTeachingOffersPage.tsx`

#### Routing (`frontend/src/App.tsx`)

```tsx
<Route path="/threads" element={<ProtectedRoute><ThreadHubPage /></ProtectedRoute>} />
<Route path="/threads/teaching" element={<ProtectedRoute><WeavingTeachingOffersPage /></ProtectedRoute>} />
<Route path="/threads/:id" element={<ProtectedRoute><ThreadDetailPage /></ProtectedRoute>} />
```

Use `React.lazy` for each page (consistent with the existing code-splitting pattern).

#### Sidebar / nav

Add a "Threads" link to the magic submenu of the main navigation, alongside "Rituals". Where exactly the magic submenu lives is implementation-discoverable from the existing nav code (don't fabricate a path here).

## Data Flow

### Imbuing

1. Player on `/threads/:id` enters amount, clicks `[Confirm Imbue]`.
2. `useImbueThread` → `POST /api/magic/rituals/perform/` with `{ ritual_id, character_sheet_id, kwargs: { thread_id, amount } }`.
3. `RitualPerformView` resolves `thread_id` → Thread instance, dispatches `PerformRitualAction` → `spend_resonance_for_imbuing`.
4. Service returns `ThreadImbueResult` (resonance_spent, levels_gained, new_level, blocked_by).
5. Response payload is the result asdict; UI shows toast/inline summary, invalidates queries.

### Crossing XP Lock

1. Player clicks `[Pay XP to Cross]` on `XPLockBoundaryPanel`.
2. `useCrossXPLock` → `POST /api/magic/threads/{id}/cross-xp-lock/` with `{ boundary_level }`.
3. View dispatches `cross_thread_xp_lock`, returns the new `ThreadLevelUnlock`.
4. UI invalidates thread + summary; the imbue panel re-renders without the XP-lock block.

### Weaving

1. Player completes the wizard.
2. `useWeaveThread` → `POST /api/magic/threads/` with `{ character_sheet_id, target_kind, target_id, resonance_id, name, description }`. The existing `ThreadSerializer.create` calls `weave_thread`.
3. New thread returned; UI navigates to `/threads/{id}`.

### Pulling (ephemeral)

1. Player on hub clicks "Pull Threads". `ThreadPullDialog` opens with `combat=undefined`.
2. Dialog filters threads to always-in-action kinds.
3. Selection changes debounce-trigger `previewPull` → server returns cost + resolved effects.
4. Player clicks `[Commit Pull]`. `useCommitPull` → `POST /api/magic/thread-pull-commit/` with empty `action_context`.
5. Server commits (no CombatPull row created since `combat_encounter` is None), returns result.
6. UI invalidates hub summary + character resonances; close dialog with success toast.

### Pulling (combat — future combat panel mounts the same dialog)

1. Combat panel passes `combat={ encounterId, participantId, involved* }` prop.
2. Dialog enables all kinds; involvement gates surface on per-thread eligibility.
3. Same preview/commit flow; commit endpoint persists `CombatPull` + `CombatPullResolvedEffect` rows.

### Accepting a teaching offer

1. Learner on `/threads/teaching` clicks `[Accept Offer]`.
2. `AcceptOfferDialog` confirms cost.
3. `useAcceptTeachingOffer` → `POST /api/magic/teaching-offers/{id}/accept/`.
4. Server creates `CharacterThreadWeavingUnlock`, deducts XP, consumes teacher's banked AP.
5. UI invalidates teaching-offers list + hub summary; offer disappears from the list (the same offer can't be accepted twice — backend/server-side will need uniqueness; the existing `CharacterThreadWeavingUnlock.unique_together(character, unlock)` provides this).

## Migration / Rollout

- Backend migration: single `Ritual.client_hosted` column add. Default False, so all existing rituals continue to surface on `/rituals`. Imbuing factory is updated to set True.
- No data migration needed. Local dev DB is disposable; CI fresh-DB tests cover the new shape.
- No feature flag needed — frontend simply doesn't show the routes/nav until the components ship.

## Out of Scope / Follow-ups

- Combat panel UI (mounts `ThreadPullDialog`) — separate spec.
- Teacher-side: authoring `ThreadWeavingTeachingOffer` — separate spec, will mirror codex teaching offer authoring when that ships.
- TRAIT/TECHNIQUE/ROOM ephemeral pulls — needs an "involvement editor" UI; deferred until concrete RP demand.
- Bulk operations on threads (multi-select retire, batch imbue).
- Pull history / audit display (CombatPull rows from past combat encounters).
- Weaving acquisition without a teacher — currently only via offer-accept; self-acquisition (e.g., from a path grant) is a separate pattern that may need its own surface later.
- Replacing the placeholder `accept_soul_tether` Path grant with intentional cultural grants (carry-over from anima ritual spec) — not blocked by this work.
