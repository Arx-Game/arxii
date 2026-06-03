# Soul Tether UI Design

**Date:** 2026-05-05
**Status:** Approved (design conversation)
**Backend spec it complements:** `docs/architecture/soul-tether.md`

---

## Goal

Surface the Soul Tether mechanic (backend-only as of commit `50570e8d`) in the React frontend so two PCs can actually form, use, and interact with a tether bond through the browser. Establish the generic ritual UI infrastructure as the first real consumer of the existing `Ritual` / `RitualPerformView` backend, so subsequent rituals (covenant formation, individualized Anima rituals, etc.) need only their `Ritual` row + `input_schema` to become playable.

## Background

Soul Tether shipped May 2026 as backend-only:
- Models: `Sineating`, `SoulTetherRescue`, `Thread.hollow_current`, `CharacterResonance.lifetime_helped`
- Services: `accept_soul_tether`, `dissolve_soul_tether`, `request_sineating`, `resolve_sineating`, `perform_soul_tether_rescue`, plus reactive subscribers `soul_tether_redirect_handler` and `soul_tether_stage_advance_prompt`
- API endpoints: `POST /api/magic/soul-tether/{accept,dissolve,sineat/request,sineat/respond,rescue}/`, `GET /api/magic/soul-tether/{id}/detail/`
- 207 tests, 14 end-to-end integration tests passing

**No frontend consumer exists.** Only character creation has any magic-system UI.

The generic ritual stack also already exists: `Ritual` model with dual-dispatch (`SERVICE | FLOW`) at `src/world/magic/models/rituals.py:48`, `RitualPerformView` at `src/world/magic/views.py:660`. `accept_soul_tether` is wired as a SERVICE Ritual.

## Design Decisions

### 1. Path A — generic shells before Soul Tether-specific UI
Build the generic ritual UI shell, generic Thread display, and generic relationship panel first. Plug Soul Tether in as the first consumer. This sets up the next ritual (covenant formation, Anima ritual, etc.) to require only its `Ritual` row + input schema, no new UI work. Rejected Path B (Soul-Tether-specific UI now, refactor later) because the user has explicitly flagged the parallel-systems anti-pattern in project memory and the roadmap already lists ritual UI, thread UI, and relationship UI as separate gaps.

### 2. Tether formation IS the ritual
The "form a tether" UI surface is the *ritual perform* surface, not a standalone invitation dialog. The `accept_soul_tether` Ritual already handles target selection, validation, gates, and atomic creation of the capstone Thread + ConditionInstance + triggers. The frontend submits to `POST /api/magic/rituals/perform/` with the appropriate kwargs.

### 3. Dissolve is tertiary
A minimal "dissolve" action somewhere is fine (the backend endpoint exists). Do not invest in confirmations, audit display, recovery flows, or rich UX for dissolve.

### 4. Relationship-first presentation
Soul Tether is a relationship in user-mental-model terms. Surface tether status via the relationship panel on the character sheet. Magic-side surfaces (Hollow bar, Sineating inbox, rescue prompts) live separately under magic but the *bond itself* is presented as a relationship.

The current `frontend/src/components/character/RelationshipsSection.tsx` is a stub rendering a plain `string[]`. Replace it with a real panel that includes Soul Tether bonds (and is structured to accept future relationship types).

### 5. Backend gap is small (one field + one viewset)
- Add `Ritual.input_schema` JSONField — declares what kwargs the perform endpoint should collect from the player (UI-rendering metadata).
- Add `RitualViewSet` (read-only list/detail) — frontend needs a way to discover available rituals.
- Wire `accept_soul_tether`'s `input_schema` (sineater_sheet, scene, resonance, capstone).

NOT extending `FlowDefinition` (input_schema would be wrong layer — SERVICE rituals need it too, FlowDefinition stays generic). NOT adding owner FKs anywhere (per-character flows handled via FK inversion: data row points to flow, not the other way).

### 6. Input schema shape
Simple object describing form fields. Not full JSON Schema (overkill).

```json
{
  "fields": [
    {
      "name": "sineater_sheet_id",
      "label": "Sineater (the other PC)",
      "type": "character_search",
      "required": true,
      "help": "The character who will share this bond with you"
    },
    {
      "name": "scene_id",
      "label": "Scene",
      "type": "scene_picker",
      "required": true,
      "scope": "active_for_caller"
    },
    {
      "name": "resonance_id",
      "label": "Resonance",
      "type": "resonance_picker",
      "required": true,
      "scope": "owned_by_caller"
    },
    {
      "name": "capstone_id",
      "label": "Relationship Capstone",
      "type": "relationship_capstone_picker",
      "required": true,
      "scope": "with_target_character"
    }
  ]
}
```

Field types covered in v1:
- `character_search` — debounced search via `searchPersonas`
- `scene_picker` — dropdown of caller's active scenes
- `resonance_picker` — dropdown of caller's owned `CharacterResonance`
- `relationship_capstone_picker` — dropdown of caller's relationship capstones (filterable by target character)
- `int`, `text`, `select` — primitives for future rituals

Unknown field types render as a plain text input with a warning ("unsupported field type — frontend may need an update"). This keeps new schemas authorable in admin without frontend deploys, while flagging when a deploy is needed.

### 7. Frontend surfaces (per-component reference)

| Surface | Clone from | Notes |
|---|---|---|
| Generic ritual perform dialog | `frontend/src/stories/components/AcceptOfferDialog.tsx` | Shell with field rendering driven by input_schema |
| Generic ritual list | `frontend/src/tables/components/TableCard.tsx` (card grid) | Cards show name, description, narrative_prose, perform CTA |
| Hollow bar | `frontend/src/fatigue/components/FatigueDisplay.tsx` | Single zoned `<Progress>` bar with current/max readout |
| Sineating inbox + accept | `frontend/src/scenes/components/ConsentPrompt.tsx` | Polled banner; swap endpoint to `/sineat/respond/` |
| Sineating request dialog | `frontend/src/stories/components/AcceptOfferDialog.tsx` | Sinner picks units + resonance + scene |
| Rescue ritual prompt | `frontend/src/scenes/components/SoulfrayWarning.tsx` + ConsentPrompt polling | Reactive opt-in for stage-advance bonus |
| Tether status panel | `frontend/src/progression/components/VotesPanel.tsx` | Card with rows: bonded character, Hollow bar, lifetime_helped |
| Thread display panel | `frontend/src/progression/components/VotesPanel.tsx` | Read-only thread list; filterable by target_kind |
| Relationship section (stub replacement) | `frontend/src/components/character/RelationshipsSection.tsx` | Compose: existing free-text + tether status panel |

### 8. Out of scope for this spec
- Anima ritual UI — same shell will work, but wiring `perform_anima_ritual` as a Ritual row and exposing it is its own task
- Covenant formation ritual — same, future work
- Imbuing rite UI — already a SERVICE Ritual, frontend exposure is future work
- Thread weaving UI (acquiring new ThreadWeavingUnlocks) — separate from Thread *display*
- Resonance imbuing UI (spending resonance to advance Thread level) — adjacent system, separate work
- Soul Tether dissolve UX beyond a minimal action — explicit per design decision
- Per-resonance Strain tracking on Sineater — backend phase 6 deferred, no UI yet
- `SoulTetherConfig` admin tuning surface — backend phase 14 deferred

## Acceptance Criteria

A player can:
1. Navigate to a "Rituals" page (or section) and see `accept_soul_tether` listed as an available ritual
2. Click "Perform" and fill in the four fields (sineater, scene, resonance, capstone) using sensible pickers
3. Submit and see the bond formed (or see typed errors if a gate fails)
4. View their Hollow on a tether status panel within the relationship section of their character sheet
5. As a Sineater: see pending Sineating requests in an inbox component and accept/decline
6. As a Sineater: see a stage-advance prompt during a Sinner's corruption progression and opt in to spend Strain + resonance
7. Author a new Ritual row with a different `input_schema` in admin, and see the perform UI render the new fields without a frontend deploy (only unknown field types fall back to plain text input)

A developer can:
1. Run all magic + frontend tests with `arx test world.magic` and `pnpm test` cleanly
2. Run frontend e2e smoke test (`pnpm test:e2e`) cleanly
3. See no regressions in existing 1000+ magic tests
