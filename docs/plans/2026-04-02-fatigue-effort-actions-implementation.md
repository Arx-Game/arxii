# Fatigue, Effort Levels, and Character Actions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 3 new stats (Composure, Stability, Luck), reclassify Perception/Willpower to Meta, simplify CG stat allocation to "budget = sum of starting values, min 1 max 5", build the fatigue system with three independent pools, effort levels, collapse mechanic, IC daily reset, and rest command.

**Architecture:** New stats added to PrimaryStat enum and fixtures. CG simplified to remove internal 10-50 scale — store and display 1-5 directly. CharacterFatigue model tracks three pools. Fatigue integrates with the existing check/modifier system via ModifierTargets. Effort level is a parameter on action execution that scales cost and check modifier.

**Tech Stack:** Django models (SharedMemoryModel), existing modifier system (ModifierTarget/CharacterModifier), cron registry, React frontend (character creation components)

**Key files to consult:**
- Design doc: `docs/plans/2026-04-02-fatigue-effort-actions-design.md`
- Traits: `src/world/traits/constants.py`, `src/world/traits/fixtures/initial_primary_stats.json`
- CG: `src/world/character_creation/constants.py`, `models.py`, `validators.py`, `serializers.py`
- Frontend CG: `frontend/src/character-creation/components/AttributesStage.tsx`
- Modifier system: `src/world/mechanics/models.py` (ModifierTarget, CharacterModifier)
- Cron: `src/world/game_clock/tasks.py`, `task_registry.py`

---

## Phase 1: New Stats + CG Simplification

### Task 1: Add new stats to PrimaryStat enum and fixtures

**Files:**
- Modify: `src/world/traits/constants.py` (PrimaryStat enum + get_stat_metadata)
- Modify: `src/world/traits/fixtures/initial_primary_stats.json` (add 3 new stats)
- Modify: `src/world/character_creation/constants.py` (update budget constants)
- Test: Run existing trait tests to verify no breakage

**Changes:**

Add to PrimaryStat enum:
- `COMPOSURE = "composure", "Composure"`
- `STABILITY = "stability", "Stability"`
- `LUCK = "luck", "Luck"`

Update categories in get_stat_metadata:
- perception: social → meta
- willpower: mental → meta
- composure: social (new)
- stability: mental (new)
- luck: meta (new)

Final layout (12 stats, 4 categories):
- physical: strength, agility, stamina
- social: charm, presence, composure
- mental: intellect, wits, stability
- meta: luck, perception, willpower

Update fixture JSON to add composure, stability, luck entries.

Update constants:
- Remove `STAT_FREE_POINTS`, `STAT_BASE_POINTS`, `STAT_TOTAL_BUDGET`
- Remove `STAT_DISPLAY_DIVISOR`, `STAT_DEFAULT_VALUE`
- Keep `STAT_MIN_VALUE = 1` (was 10)
- Keep `STAT_MAX_VALUE = 5` (was 50)
- Add `STAT_DEFAULT_VALUE = 2`
- Add `STAT_COUNT = 12`

Generate migration for the new Trait records: `uv run arx manage loaddata initial_primary_stats`

**Commit:** `feat(traits): add Composure, Stability, Luck stats; reclassify Perception/Willpower to Meta`

---

### Task 2: Simplify CG stat allocation backend

**Files:**
- Modify: `src/world/character_creation/models.py` (CharacterDraft stat methods)
- Modify: `src/world/character_creation/validators.py` (get_attributes_errors)
- Modify: `src/world/character_creation/serializers.py` (stat serializer fields)
- Modify: `src/world/character_creation/constants.py` (REQUIRED_STATS update)
- Test: `src/world/character_creation/tests/test_models.py` (rewrite stat tests)

**New stat allocation logic:**

`CharacterDraft` methods to replace:

**`calculate_stat_budget()`** (replaces calculate_stats_free_points + get_stats_max_free_points):
```python
def calculate_stat_budget(self) -> int:
    """Total points available = (2 * stat_count) + net bonuses."""
    bonuses = self.get_all_stat_bonuses()
    base = STAT_DEFAULT_VALUE * len(REQUIRED_STATS)  # 2 * 12 = 24
    net_bonus = sum(bonuses.values())
    return base + net_bonus

def calculate_points_remaining(self) -> int:
    """Budget minus currently allocated points."""
    stats = self.draft_data.get("stats", {})
    if not stats:
        return self.calculate_stat_budget() - (STAT_DEFAULT_VALUE * len(REQUIRED_STATS))
    spent = sum(stats.values())
    return self.calculate_stat_budget() - spent
```

**Remove entirely:**
- `get_stats_max_free_points()`
- `calculate_stats_free_points()`
- `enforce_stat_caps()` (no longer needed — bonuses affect budget, not individual caps)

**Simplify `calculate_final_stats()`:**
```python
def calculate_final_stats(self) -> dict[str, int]:
    """Return allocated stats as-is (already in display scale 1-5)."""
    stats = self.draft_data.get("stats", {})
    return {name: stats.get(name, STAT_DEFAULT_VALUE) for name in REQUIRED_STATS}
```

Note: Bonuses are baked into the budget, not applied on top. The allocated values ARE the final values.

**Simplify `get_attributes_errors()`:**
```python
def get_attributes_errors(draft) -> list[str]:
    errors = []
    stats = draft.draft_data.get("stats", {})
    missing = [s for s in REQUIRED_STATS if s not in stats]
    if missing:
        errors.append(f"Missing stats: {', '.join(missing)}")
        return errors
    for stat_name, value in stats.items():
        if not isinstance(value, int):
            errors.append(f"{stat_name} has invalid value")
        elif not (STAT_MIN_VALUE <= value <= STAT_MAX_VALUE):
            errors.append(f"{stat_name} must be between {STAT_MIN_VALUE} and {STAT_MAX_VALUE}")
    remaining = draft.calculate_points_remaining()
    if remaining > 0:
        errors.append(f"{remaining} point(s) remaining")
    elif remaining < 0:
        errors.append(f"{abs(remaining)} point(s) over budget")
    return errors
```

**Update serializer:**
- Replace `stats_free_points` → `stats_points_remaining`
- Replace `stats_max_free_points` → `stats_budget`
- Keep `stat_bonuses`

**Rewrite all 21 stat tests** to use new logic:
- Budget = 24 (12 stats * 2) + net bonuses
- Values stored as 1-5 directly (no *10 conversion)
- Validation: sum == budget, each 1-5

**Commit:** `refactor(cg): simplify stat allocation — budget = 2 * stat_count + bonuses, store 1-5 directly`

---

### Task 3: Update frontend stat allocation

**Files:**
- Modify: `frontend/src/character-creation/components/AttributesStage.tsx`
- Modify: `frontend/src/character-creation/types.ts` (Stats type, if exists)
- Modify: any `getDefaultStats()` helper
- Test: `pnpm typecheck && pnpm lint`

**Changes:**
- Remove all `* 10` and `/ 10` conversions (values are now 1-5 directly)
- Update `STAT_ORDER` to include composure, stability, luck (4x3 grid)
- Replace `freePoints` / `maxFreePoints` with `pointsRemaining` / `budget`
- Update `canIncrease` logic: `allocated < 5 && pointsRemaining > 0`
- Update `canDecrease` logic: `allocated > 1`
- Remove `maxAllocatable` calculation (always 5)
- Update `handleStatChange` to pass value directly (no `* 10`)
- Group stats by category in the UI (physical/social/mental/meta columns)
- Show "X/Y points allocated" instead of "X free points"

**Commit:** `feat(frontend): update stat allocation for 12 stats with simplified budget`

---

## Phase 2: Fatigue System

### Task 4: CharacterFatigue model

**Files:**
- Create: `src/world/fatigue/` app (models, services, constants, admin, etc.)
  OR add to existing app. Given CLAUDE.md preference for focused apps, create as
  part of `world/action_points/` since fatigue is a character resource like AP.
  Actually, fatigue is distinct enough — create `src/world/fatigue/` with its own models.
- Test: `src/world/fatigue/tests/test_models.py`

**Models:**

`FatiguePool` (SharedMemoryModel) — one per character:
- `character` — OneToOne FK to ObjectDB (or CharacterSheet?)
  Per CLAUDE.md rule: avoid ObjectDB. Use CharacterSheet.
- `physical_current` — PositiveIntegerField (default=0, current fatigue)
- `social_current` — PositiveIntegerField (default=0)
- `mental_current` — PositiveIntegerField (default=0)
- `well_rested` — BooleanField (default=False)
- `rested_today` — BooleanField (default=False, reset on IC dawn)
- `dawn_deferred` — BooleanField (default=False, true if in scene at dawn)

Constants in `fatigue/constants.py`:
```python
class FatigueCategory(TextChoices):
    PHYSICAL = "physical"
    SOCIAL = "social"
    MENTAL = "mental"

class FatigueZone(TextChoices):
    FRESH = "fresh"          # 0-40%
    STRAINED = "strained"    # 41-60%
    TIRED = "tired"          # 61-80%
    OVEREXERTED = "overexerted"  # 81-99%
    EXHAUSTED = "exhausted"  # 100%+

class EffortLevel(TextChoices):
    HALFHEARTED = "halfhearted"
    NORMAL = "normal"
    ALL_OUT = "all_out", "All Out"

# Fatigue zone thresholds (percentage of capacity)
ZONE_THRESHOLDS = {
    FatigueZone.FRESH: (0, 40),
    FatigueZone.STRAINED: (41, 60),
    FatigueZone.TIRED: (61, 80),
    FatigueZone.OVEREXERTED: (81, 99),
    FatigueZone.EXHAUSTED: (100, None),  # No upper bound
}

# Check penalties per zone
ZONE_PENALTIES = {
    FatigueZone.FRESH: 0,
    FatigueZone.STRAINED: -1,
    FatigueZone.TIRED: -2,
    FatigueZone.OVEREXERTED: -3,
    FatigueZone.EXHAUSTED: -4,
}

# Effort level modifiers
EFFORT_CHECK_MODIFIER = {
    EffortLevel.HALFHEARTED: -2,
    EffortLevel.NORMAL: 0,
    EffortLevel.ALL_OUT: 2,
}

EFFORT_COST_MULTIPLIER = {
    EffortLevel.HALFHEARTED: 0.3,
    EffortLevel.NORMAL: 1.0,
    EffortLevel.ALL_OUT: 2.0,
}

# Capacity formula
CAPACITY_STAT_MULTIPLIER = 10
CAPACITY_WILLPOWER_MULTIPLIER = 3
WELL_RESTED_MULTIPLIER = 1.5

# Rest command
REST_AP_COST = 10

# Endurance stat mapping
FATIGUE_ENDURANCE_STAT = {
    FatigueCategory.PHYSICAL: "stamina",
    FatigueCategory.SOCIAL: "composure",
    FatigueCategory.MENTAL: "stability",
}
```

**Commit:** `feat(fatigue): add FatiguePool model and fatigue constants`

---

### Task 5: Fatigue service functions

**Files:**
- Create: `src/world/fatigue/services.py`
- Test: `src/world/fatigue/tests/test_services.py`

**Functions:**

`get_fatigue_capacity(character, category)` — Calculate max fatigue for a category.
Uses endurance stat + willpower + well_rested modifier. Integrates with modifier system.

`get_fatigue_zone(character, category)` — Return current zone based on percentage.

`get_fatigue_penalty(character, category)` — Return check penalty for current zone.

`apply_fatigue(character, category, base_cost, effort_level)` — Add fatigue. Returns
the actual cost after effort multiplier and modifiers.

`check_collapse_risk(character, category, effort_level)` — Return whether collapse
check is needed (overexerted/exhausted + normal/all-out effort).

`attempt_collapse_check(character, category)` — Roll endurance stat vs fatigue level.
Return (passed: bool, can_power_through: bool).

`attempt_power_through(character, category)` — Roll willpower (with intensity bonus).
Return (passed: bool, strain_damage: int).

`reset_fatigue(character)` — Reset all three pools to 0. Clear dawn_deferred.

`rest(character)` — Spend AP, set well_rested=True, set rested_today=True.

**Commit:** `feat(fatigue): add fatigue service functions`

---

### Task 6: IC dawn reset cron

**Files:**
- Modify: `src/world/game_clock/tasks.py` (register fatigue reset)
- Create: `src/world/fatigue/tasks.py` (the actual task function)
- Test: `src/world/fatigue/tests/test_tasks.py`

**Logic:**
- Cron fires at IC dawn (check IC time via game clock)
- For each FatiguePool:
  - If character is in an active scene → set dawn_deferred=True, skip
  - Otherwise → reset_fatigue(), apply well_rested bonus if flagged
- For deferred characters: a separate check runs when scenes end (wire into
  on_scene_finished or scene completion flow)

**Commit:** `feat(fatigue): add IC dawn fatigue reset cron`

---

### Task 7: Rest command

**Files:**
- Create appropriate command/handler for "rest"
- Integrate with AP spending
- Test: rest costs AP, sets well_rested, blocks second rest same day

**Commit:** `feat(fatigue): add rest command (10 AP, once per IC day, at home)`

---

## Phase 3: Effort Levels + Action Integration

### Task 8: Effort level integration with check system

**Files:**
- Modify: `src/world/checks/services.py` (perform_check to accept effort_level)
- Modify: relevant ModifierTarget setup
- Test: effort level applies correct bonus/penalty to checks

**Commit:** `feat(checks): integrate effort level modifier into perform_check`

---

### Task 9: Action fatigue cost pipeline

**Files:**
- Modify scene action request flow to include effort level and fatigue cost
- Wire fatigue application into the action execution pipeline
- Test: action costs fatigue from correct pool, effort scales cost

**Commit:** `feat(actions): wire fatigue cost into action execution pipeline`

---

### Task 10: Collapse mechanic

**Files:**
- Create collapse check flow (endurance check → power through prompt → willpower check)
- Integrate with action execution (check collapse risk after fatigue applied)
- Test: collapse triggers at overexerted, power through with willpower

**Commit:** `feat(fatigue): implement two-stage collapse mechanic`

---

### Task 11: Frontend fatigue display + effort selection

**Files:**
- Create fatigue display component (three bars)
- Create effort level selector for actions
- Show effort tags on interactions
- Test: `pnpm typecheck && pnpm lint`

**Commit:** `feat(frontend): fatigue display and effort level selector`

---

### Task 12: Update roadmap and documentation

**Files:**
- Modify: `docs/roadmap/character-progression.md`
- Modify: `docs/roadmap/capabilities-and-challenges.md`
- Modify: `docs/roadmap/ROADMAP.md`

**Commit:** `docs(roadmap): update for fatigue system and new stats`
