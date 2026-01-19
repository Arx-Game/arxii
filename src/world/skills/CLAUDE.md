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
