# Skills System - Character Abilities and Specializations

Parent skills and specializations for character abilities. Skills are linked to the Trait system for unified check resolution.

## Key Files

### `models.py`
- **`Skill`**: Parent skill linked to Trait (Melee Combat, Persuasion, etc.)
- **`Specialization`**: Specific application under a parent skill (Swords, Seduction)
- **`CharacterSkillValue`**: The skill rating the sheet shows (progress and rust live in the trait's `DevelopmentPoints`)
- **`CharacterSpecializationValue`**: Character's specialization value with development tracking
- **`SkillPointBudget`**: CG configuration (single-row model)
- **`PathSkillSuggestion`**: Suggested skills for paths (templates, freely redistributable)

### `admin.py`
- Admin for all models with inline specialization editing
- SkillPointBudget limited to single row

### `admin_inlines.py`
- Registration-free pieces both the Skill and Trait admins use (#5006): `SkillOnTraitInline`
  (the Trait page's Skill section, where a skill is authored), its formset, and
  `ensure_skill_target_or_warn`. Neither admin module imports the other's.

### `factories.py`
- FactoryBoy factories for all models

## Key Concepts

### Skill Values
- Internal: 10, 20, 30... (stored value)
- Display: 1.0, 2.0, 3.0... (value / 10)
- CG max: 30 (configurable via SkillPointBudget)
- Post-CG max: the level band's `MaturationStatCap.skill_cap` (#4585); no cap when blank

### Development Points (one ledger, #5010)
- A skill's progress lives in its trait's `progression.DevelopmentPoints` row; every source
  (use, GM awards, training, Academy) goes through `DevelopmentPoints.award_points`
- The ledger counts from the current rating; a direct rating write aligns it
  (`align_development_floors`, called by `set_skill_trait`)
- Specializations keep their own `CharacterSpecializationValue.development_points`

### Rust
- `DevelopmentPoints.rust_debt`, paid off before points count toward a level
- One weekly pass in the rollover (`progression.services.skill_development._apply_weekly_rust`);
  a skill used or trained that week is exempt; languages never rust
- Only affects parent skills (specializations immune)

### CG Point Budget
- Path points (50): Suggested by path, freely redistributable
- Free points (60): Player's choice
- Total: 110 points
- Cost: 10 per tier (flat)

## Integration Points

- **Trait System**: Skills link to Trait model for unified checks
- **Character Creation**: Stage 5 uses skills for allocation
- **Character Sheets**: Display skills with development progress
- **Progression**: XP and development point advancement (separate system)

## Training System

### Models
- **`TrainingAllocation`**: Persistent weekly training plan entry. FK to character, skill/specialization (XOR), optional mentor guise, AP amount. Characters can have multiple allocations.

### Service Functions (`services.py`)

**CRUD:**
- `create_training_allocation(character, ap_amount, *, skill, specialization, mentor)` — creates allocation, validates the weekly AP budget. **That budget is shared with ties (#3957):** the check sums this character's training allocations AND their standing `RelationshipAllocation` rows (`world.relationships.services.standing_tie_ap`) against `ActionPointConfig.get_weekly_regen()`, because both are paid from the one `ActionPointPool` at the weekly turn. The tie door enforces the same total from its side (`set_allocation`, via `standing_weekly_ap`).
- `update_training_allocation(allocation, *, ap_amount, mentor)` — updates allocation, against that same shared budget (its own row excluded)
- `remove_training_allocation(allocation)` — deletes allocation

**Calculation:**
- `calculate_training_development(allocation)` — computes dev points from training formula

**Cron Processing:**
- `process_weekly_training()` — processes all allocations, awards dev points, consumes AP
- `run_weekly_skill_cron()` — weekly training only; rust is the rollover's one pass (#5010)

**Development from training (#4457):**
- `train_skill(sheet, skill, dev_points, *, description, stop_at_boundary=False) -> SkillTrainingResult`
  (`world/skills/types.py`) — the one writer: a new skill starts at `DP_BASE_LEVEL`; the points go
  into the trait's `DevelopmentPoints` through `award_points`; one `DevelopmentTransaction` with the
  current `game_week`. Weekly training's skill branch and Academy courses both call it.
  `stop_at_boundary=True` clamps to `points_to_next_boundary` so nothing dissipates; the caller
  keeps the excess.
- `points_to_next_boundary(tracker: DevelopmentPoints) -> int | None` — rust + level costs up to
  the next boundary or the band's skill cap (whichever is first), less progress banked; only rust
  at a boundary or the cap; `None` above 49 with no cap.
- `next_xp_boundary(value) -> int | None` — the first boundary at or above `value`

**XP-Boundary Breakthrough (#2115):**
- `purchase_skill_breakthrough(character, skill) -> tuple[bool, str]` — spends XP against
  an authored `TraitRatingUnlock` to clear a boundary-parked skill's gate; the new rating raises
  the ledger to it (no retroactive credit)
- `skills_at_boundary(character) -> list[SkillBreakthroughProspect]` — selector listing every
  gated skill (read from `CharacterTraitValue`) with its authored XP cost (or `authored=False`)
- `is_skill_at_xp_boundary(value) -> bool` — public wrapper for boundary-check, used by
  `character_sheets` serialization for the `SkillEntry.at_boundary` flag

### Training Formula
```
base_gain = 5 × AP × path_level
mentor_bonus = (AP + teaching) × (mentor_skill / student_skill) × (relationship_tier + 1)
dev_points = base_gain + mentor_bonus
```

### Development Costs
- Level N to N+1 costs `(N - 9) × 100` dev points
- Overflow carries across levels
- XP boundaries at 19, 29, 39, 49 are a **plateau, not banking** (#2115) for every source,
  use and GM awards as well as training (#5010): a boundary-parked skill still pays off rust
  from incoming dev points, but any surplus beyond that payoff **dissipates**. `train_skill`
  returns a plateau message on dissipation (also folded into the weekly
  `DevelopmentTransaction.description`); `purchase_skill_breakthrough(character, skill)`
  spends XP against an authored `progression.TraitRatingUnlock` to clear the gate, and
  development resumes from zero toward the next level (no retroactive credit for
  dissipated points). `skills_at_boundary(character)` surfaces every gated skill (with its
  authored XP cost, if any) for display. Reachable via `progression unlock skill=<id>`
  (`PurchaseUnlockAction` `unlock_type="skill_breakthrough"`); default breakthroughs are
  seeded by the `"skills"` cluster (`world.seeds.game_content.skills`).
- Specializations have no XP boundaries
- **Band skill cap (#4585):** `MaturationStatCap.skill_cap` (shown units, blank = no cap) caps every
  skill and specialization by the character's level band, like `stat_cap`. `stored_skill_cap(sheet)`
  converts it (`skill_cap_for(sheet) * 10`). `train_skill`, `points_to_next_boundary`,
  `_apply_development_to_specialization`, `purchase_skill_breakthrough`,
  `DevelopmentPoints.award_points` (SKILL traits only) and staff edit's `set_skill_values` all stop
  there; development at the cap dissipates as at an XP boundary, with `skill_cap_message` naming
  the cap. Any new skill raise path must check it too.

### Rust System
- Idle skills accumulate `character_level + 5` rust debt per week, at most the current
  level's cost per week (`apply_skill_rust`)
- Dev points pay off rust before counting toward advancement
- Training or use in a week prevents rust for that week

### Integration Points
- **Action Points**: AP consumed at weekly cron from `ActionPointPool`
- **Progression**: Creates `DevelopmentTransaction` audit records with `DevelopmentSource.TRAINING` source and `ProgressionReason.SYSTEM_AWARD` reason. Uses the skill's linked Trait (or parent skill's Trait for specializations) as the transaction trait.
- **Relationships**: `get_relationship_tier()` stub in `world.relationships.helpers` (TODO: implement)
- **Guise**: Mentor FK points to character_sheets.Guise
