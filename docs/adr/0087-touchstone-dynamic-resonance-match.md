# ADR-0087: Touchstone dynamic resonance-match via in-place RitualComponentRequirement extension

## Status

Accepted

## Context

Ritual of Sanctification (#707) needs a component requirement that matches
"any item tagged with the performer's own claimed Resonance, at or above a
tier floor" — not a fixed, authored `ItemTemplate`. The existing
`RitualComponentRequirement` (`world/magic/models/rituals.py`) only supported
exact `item_template` FK matching (a fixed archetype + optional
`min_quality_tier`).

Two designs were considered:

1. **Extend `RitualComponentRequirement` in-place** — add a second, mutually
   exclusive mode alongside `item_template`.
2. **A parallel `TouchstoneRequirement` model**, checked by a second code path
   alongside the existing template-mode check.

## Decision

Extend `RitualComponentRequirement` in-place: `item_template` becomes
nullable, and a new nullable `min_touchstone_tier` FK (to a new
`ResonanceTier` lookup model, `world/magic/models/affinity.py`) adds a second
mode. A `CheckConstraint` (`ritualcomponentrequirement_exactly_one_mode`)
enforces exactly one of the two is set per row — mirroring the existing
`Ritual.execution_kind` shape-per-kind constraint pattern already used in
this codebase.

Touchstone-mode resolution is dynamic, not authored: the row only stores a
tier floor (`min_touchstone_tier`); the *resonance* to match is resolved at
performance time from the performer's own `CharacterResonance` rows (or, when
the dispatching action supplies a specific `resonance_context`, against that
one Resonance only — see "Consequence discovered during implementation" below).

## Rejected alternative

A parallel `TouchstoneRequirement` model, checked by a second code path
alongside the existing template-mode check. Rejected because it doubles the
"things a Ritual can require" surface for a case the in-place extension
handles with two nullable fields and one shared resolution helper
(`resolve_and_consume_ritual_components`), and because
`CraftingMaterialRequirement` (crafting's sibling model, `world/items/crafting/models.py`)
never needs touchstone-mode at all — a crafter attaching a facet to someone
else's garment isn't a personal-resonance act, so FACET_ATTACH content stays
exact-template matching (#707 spec, decision 7) — a parallel model would be
an unused shape on that side.

## Consequence discovered during implementation

Ritual of Sanctification's two `Ritual` rows (Personal + Covenant) are
`client_hosted=True` and dispatch via a bespoke `SanctumInstallAction`
(`actions/definitions/sanctum.py`), **not** the generic `PerformRitualAction`
seam (`actions/definitions/ritual.py`) every other Ritual uses. Verified by
reading both files: `PerformRitualAction._validate_components` is the only
call site inside the generic seam, and `SanctumInstallAction.execute()` never
calls it or `PerformRitualAction` at all.

The component validate/consume logic was therefore extracted into a
standalone service function, `resolve_and_consume_ritual_components(*, ritual,
components, performer_sheet, resonance_context=None)`
(`world/magic/services/ritual_components.py`), callable from **both** seams —
`PerformRitualAction._validate_components` and `SanctumInstallAction.execute()`
— rather than being buried inside `PerformRitualAction` alone. The optional
`resonance_context` parameter lets `SanctumInstallAction` pass the *specific*
founding Resonance the founder is consecrating this Sanctum to, so a
touchstone attuned to a different (also-claimed) Resonance does not
incorrectly satisfy Sanctification's requirement; `PerformRitualAction` omits
it, falling back to "any Resonance the performer has claimed."

## Consequences

- Every existing `RitualComponentRequirement` row (all template-mode) is
  unaffected — the `CheckConstraint` only requires exactly one mode be set,
  and template-mode rows already had `min_touchstone_tier` implicitly null.
- A future Ritual/CraftingRecipe author can add a touchstone-mode requirement
  with no new model, migration shape, or service function — only a new
  `RitualComponentRequirement` row.
- `resolve_and_consume_ritual_components` is now the single seam any future
  bespoke (non-`PerformRitualAction`) Ritual dispatch must call to honor
  component requirements, rather than each bespoke action reinventing
  validate/consume logic.
