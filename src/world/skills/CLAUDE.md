# Skills System - Character Abilities and Specializations

Parent skills and specializations for character abilities. Skills are linked to the Trait system for unified check resolution.

## Key Files

### `models.py`
- **`Skill`**: Parent skill linked to Trait (Melee Combat, Persuasion, etc.)
- **`Specialization`**: Specific application under a parent skill (Swords, Seduction)
- **`CharacterSkillValue`**: Character's skill value with development/rust tracking
- **`CharacterSpecializationValue`**: Character's specialization value with development tracking
- **`SkillPointBudget`**: CG configuration (single-row model)
- **`PathSkillSuggestion`**: Suggested skills for paths (templates, freely redistributable)

### `admin.py`
- Admin for all models with inline specialization editing
- SkillPointBudget limited to single row

### `factories.py`
- FactoryBoy factories for all models

## Key Concepts

### Skill Values
- Internal: 10, 20, 30... (stored value)
- Display: 1.0, 2.0, 3.0... (value / 10)
- CG max: 30 (configurable via SkillPointBudget)
- Post-CG max: 210+ (based on path level)

### Development Points
- Progress toward next level (e.g., 450/1000)
- Earned through training, scenes, missions
- Resets when level increases

### Rust Points
- Blocks development until cleared
- Only affects parent skills (specializations immune)
- Encourages specialization over jack-of-all-trades

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
- `create_training_allocation(character, ap_amount, *, skill, specialization, mentor)` — creates allocation, validates AP budget
- `update_training_allocation(allocation, *, ap_amount, mentor)` — updates allocation
- `remove_training_allocation(allocation)` — deletes allocation

**Calculation:**
- `calculate_training_development(allocation)` — computes dev points from training formula

**Cron Processing:**
- `process_weekly_training()` — processes all allocations, awards dev points, consumes AP
- `apply_weekly_rust(trained_skills)` — adds rust to untrained skills
- `run_weekly_skill_cron()` — orchestrator: training then rust

### Training Formula
```
base_gain = 5 × AP × path_level
mentor_bonus = (AP + teaching) × (mentor_skill / student_skill) × (relationship_tier + 1)
dev_points = base_gain + mentor_bonus
```

### Development Costs
- Level N to N+1 costs `(N - 9) × 100` dev points
- Overflow carries across levels
- XP boundaries at 19, 29, 39, 49 block advancement until XP purchase
- Specializations have no XP boundaries

### Rust System
- Untrained skills accumulate `character_level + 5` rust per week
- Rust caps at current level's dev cost
- Dev points pay off rust before counting toward advancement
- Training (or any dev source) prevents rust for that week

### Integration Points
- **Action Points**: AP consumed at weekly cron from `ActionPointPool`
- **Progression**: Creates `DevelopmentTransaction` audit records with `DevelopmentSource.TRAINING` source and `ProgressionReason.SYSTEM_AWARD` reason. Uses the skill's linked Trait (or parent skill's Trait for specializations) as the transaction trait.
- **Relationships**: `get_relationship_tier()` stub in `world.relationships.helpers` (TODO: implement)
- **Guise**: Mentor FK points to character_sheets.Guise
