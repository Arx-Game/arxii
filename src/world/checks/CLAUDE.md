# Checks - Check Resolution System

Database-defined check types with weighted trait and aspect composition, resolved through the rank/chart/outcome pipeline.

## Purpose

The checks app defines types of checks (Stealth, Diplomacy, Perception, etc.) and resolves them. Each check type specifies which traits contribute and at what weight, plus which aspects (from the classes system) are relevant. At resolution time, trait points + path-based aspect bonuses + caller-provided modifiers flow through the existing PointConversionRange/CheckRank/ResultChart pipeline.

## Key Files

### `models.py`
- **`CheckCategory`**: Groups check types (Social, Combat, Exploration, Magic). SharedMemoryModel.
- **`CheckType`**: Named check definition with trait weights and aspect weights. SharedMemoryModel.
- **`CheckTypeTrait`**: Links CheckType to Trait with a weight multiplier. SharedMemoryModel.
- **`CheckTypeAspect`**: Links CheckType to Aspect (from classes app) with a weight multiplier. SharedMemoryModel.

### `services.py`
- **`perform_check(character, check_type, target_difficulty, extra_modifiers)`**: Main resolution function. Returns CheckResult.
- **`get_rollmod(character)`**: Public function that sums character and account rollmod values. Used by both checks and attempts apps.

### `consequence_resolution.py`
- **`select_consequence(character, check_type, target_difficulty, consequences)`**: Generic consequence selection. Performs check, selects weighted consequence from pool, applies character loss filtering. Returns `PendingResolution` (not yet applied). Any system can call this.
- **`apply_resolution(pending, context)`**: Apply effects from a selected consequence using `ResolutionContext` for target resolution. Returns list of `AppliedEffect`.

### `types.py`
- **`CheckResult`**: Dataclass returned by perform_check. Contains outcome, chart, ranks, and point breakdowns. No roll numbers exposed.
- **`ResolutionContext`**: Carries typed optional refs to whatever triggered a consequence resolution (challenge_instance, action_context, future fields). Handlers use `context.character` and `context.location`.
- **`PendingResolution`**: Intermediate result holding check_result and selected_consequence. Supports future reroll/negation by separating selection from application.

## Resolution Pipeline

1. Weighted trait points from CheckTypeTrait entries
2. Aspect bonus from PathAspect weights * CheckTypeAspect weights * character level
3. Extra modifiers from caller (goals, magic, combat, conditions)
4. Total points -> CheckRank -> ResultChart -> roll 1-100 -> outcome

## Integration Points

- **Traits app**: Uses PointConversionRange, CheckRank, ResultChart, CheckOutcome
- **Classes app**: Uses Aspect and PathAspect for aspect bonuses
- **Progression app**: Uses CharacterPathHistory for current path lookup
- **Mechanics app**: `resolve_challenge()` uses `apply_resolution()` for effect dispatch
- **Any system**: Can call `select_consequence()` + `apply_resolution()` for standalone consequence resolution (magic mishaps, reactive checks, etc.)
- **Callers**: Goals, magic, combat, conditions compute extra_modifiers before calling perform_check

## Design Principles

- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect)
- **No check persistence** -- results are transient, used by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals/magic/combat compute their own modifiers
- **Absolute imports** throughout
