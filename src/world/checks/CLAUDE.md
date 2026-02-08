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

### `types.py`
- **`OutcomeSummary`**: Dataclass for a single possible outcome (name, description, success_level, min_roll, max_roll).
- **`CheckResult`**: Dataclass returned by perform_check. Contains outcome, chart, possible outcomes for frontend display. No roll numbers exposed.

## Resolution Pipeline

1. Weighted trait points from CheckTypeTrait entries
2. Aspect bonus from PathAspect weights * CheckTypeAspect weights * character level
3. Extra modifiers from caller (goals, magic, combat, conditions)
4. Total points -> CheckRank -> ResultChart -> roll 1-100 -> outcome

## Integration Points

- **Traits app**: Uses PointConversionRange, CheckRank, ResultChart, CheckOutcome
- **Classes app**: Uses Aspect and PathAspect for aspect bonuses
- **Progression app**: Uses CharacterPathHistory for current path lookup
- **Callers**: Goals, magic, combat, conditions compute extra_modifiers before calling perform_check

## Design Principles

- **SharedMemoryModel** for all lookup tables (CheckCategory, CheckType, CheckTypeTrait, CheckTypeAspect)
- **No check persistence** -- results are transient, used by flows/scenes
- **Callers own complexity** -- the resolver stays simple; goals/magic/combat compute their own modifiers
- **Absolute imports** throughout
