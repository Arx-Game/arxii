# Attempts - Narrative Consequence Layer

Wraps the check system with narrative consequences per outcome tier. Attempts translate mechanical check outcomes into specific consequences for roulette display, with rollmod-based character_loss protection.

## Purpose

The attempts app sits between the checks app (Layer 1: mechanical resolution) and callers like flows/scenes (Layer 3: acting on results). Each AttemptTemplate pairs a CheckType with weighted consequences per outcome tier, so the roulette wheel shows "Guard raises alarm" instead of "Failure."

## Key Files

### `models.py`
- **`AttemptCategory`**: Groups attempt templates (Infiltration, Social, Combat, Survival). SharedMemoryModel.
- **`AttemptTemplate`**: Staff-defined attempt pairing a CheckType with narrative consequences. SharedMemoryModel.
- **`AttemptConsequence`**: A single consequence within a template, tied to an outcome tier. Has `character_loss` flag for rollmod-based filtering.

### `services.py`
- **`resolve_attempt(character, attempt_template, target_difficulty, extra_modifiers)`**: Main entry point. Calls `perform_check()`, selects consequence, applies character loss filtering, returns `AttemptResult`.
- **`_select_weighted_consequence()`**: Weighted random selection within a tier.
- **`_apply_character_loss_filtering()`**: Positive rollmod + character_loss + alternatives exist → select non-loss alternative.
- **`_build_roulette_display()`**: Builds cosmetic display payload for frontend.

### `types.py`
- **`AttemptResult`**: Dataclass returned by `resolve_attempt()`. Contains template, check result, selected consequence, and roulette display list.
- **`ConsequenceDisplay`**: Frontend-safe consequence display (label, tier_name, cosmetic weight, is_selected). No rollmod, real weights, or character_loss flags exposed.

## Resolution Pipeline

1. Call `perform_check()` with the template's check_type → outcome tier
2. Gather AttemptConsequences matching the outcome tier
3. Select consequence via weighted random
4. If selected has `character_loss=True` AND character has positive rollmod AND non-loss alternatives exist → swap to worst non-loss alternative
5. Build roulette display with all consequences across all tiers
6. Return AttemptResult

## Rollmod in Attempts

Rollmod (from the checks layer) also affects consequence selection:
- **Positive rollmod:** Characters are protected from `character_loss` consequences when non-loss alternatives exist

## Integration Points

- **Checks app**: Uses `perform_check()` and `get_rollmod()`
- **Traits app**: AttemptConsequence FKs to CheckOutcome for outcome tier
- **Callers**: Flows, scenes, missions call `resolve_attempt()` and act on consequences

## Design Principles

- **SharedMemoryModel** for all lookup tables
- **No consequence persistence** — results are transient, used by flows/scenes
- **Callers own complexity** — the resolver stays simple; callers interpret mechanical_description
- **Roulette is theater** — real selection is server-side, display is cosmetic
- **Absolute imports** throughout
