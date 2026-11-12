# Skills System

Character skills and specializations with development tracking. `Skill` is a proxy of `Trait`
(a typed view of skill-type traits, no table); see `docs/systems/traits.md`, "A skill is a
Trait" (ADR-5008).

**Source:** `src/world/skills/`
**API Base:** `/api/skills/`

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Skill` | Proxy of `Trait` showing only skill-type traits (#5008) | `name`, `category`, `description`, `tooltip`, `display_order`, `is_active` (all `Trait` fields) |
| `Specialization` | Specific application under a parent skill | `name`, `parent_skill` (FK Skill), `description`, `tooltip`, `display_order`, `is_active` |
| `SkillPointBudget` | CG point budget configuration (single-row model) | `path_points` (50), `free_points` (60), `points_per_tier` (10), `specialization_unlock_threshold` (30), `max_skill_value` (30), `max_specialization_value` (30) |
| `PathSkillSuggestion` | Suggested skill allocation for a path (template) | `character_path` (FK Path), `skill` (FK Skill), `suggested_value`, `display_order` |

### Character Data (SharedMemoryModel - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterSpecializationValue` | Character's specialization value (no rust) | `character` (FK ObjectDB), `specialization` (FK Specialization), `value`, `development_points` |
| `TrainingAllocation` | Weekly training plan entry for a skill/specialization | `character` (FK ObjectDB), `skill` (FK Skill, XOR), `specialization` (FK Specialization, XOR), `mentor` (FK Persona, optional), `ap_amount` |

---

## Value Scale

- **Internal:** 10, 20, 30, ... (stored value, increments of 10)
- **Display:** 1.0, 2.0, 3.0, ... (shown to players, computed as `value / 10`)
- **CG max:** 30 (configurable via `SkillPointBudget.max_skill_value`)

---

## Key Concepts

### Development and rust: one ledger (#5010)

A skill's progress and its rust live in one place, the skill trait's
`progression.DevelopmentPoints` row (`total_earned`, `rust_debt`). Every source of
development writes it through `DevelopmentPoints.award_points`: use (checks with effort),
GM awards, weekly training and Academy courses (both through `train_skill`). So training
and use share one cost curve, `cumulative_dp_for_level`, where level N to N+1 costs
`(N - 9) x 100`.

- **The ledger counts from the current rating.** For a skill trait `award_points` first
  raises `total_earned` to what the current rating cost, and every writer that sets a
  rating directly (character creation and staff edit through `set_skill_values`, the XP
  breakthrough, the NPC copy, a staff character's preset) aligns the ledger to it through
  `progression.services.skill_development.align_development_floors`. A skill made at 30 needs
  2,100 points to reach 31. A rating set lower brings the ledger down with it, so use does not
  walk it straight back up.
- **Rust** is debt on the same row: incoming points pay it off before they count toward a
  level. It only affects parent skills; specializations are immune.
- **One weekly rust pass**, run by the weekly rollover
  (`progression.services.skill_development._apply_weekly_rust`). A skill used in the week
  that ended (a `WeeklySkillUsage` row) or trained in it (a `TRAINING`
  `DevelopmentTransaction` stamped with that `game_week`) is exempt; every other ledger row
  above the base level takes `path level + 5`, and outstanding debt never exceeds the
  current level's cost. Only characters in active play rust (an active, non-dormant roster
  entry); NPCs and dormant characters do not. Languages never rust.
- Specializations keep their own counter, `CharacterSpecializationValue.development_points`.

### The rating is `CharacterTraitValue` (#5010)

A character's rating in a skill is the skill's own `traits.CharacterTraitValue`, one
row that the sheet shows and every check reads. `skill_rating(sheet, skill)` (through the character's trait handler)
(`world/skills/services.py`) reads it. Writers record a `traits.CharacterTraitChange`:

| Writer | Source stamped |
|--------|----------------|
| Character creation and staff edit (`set_skill_values` -> `set_skill_trait`) | the caller's (`CHARACTER_CREATION`, `STAFF_EDIT`) |
| XP breakthrough (`purchase_skill_breakthrough` -> `set_skill_trait`) | `XP_BREAKTHROUGH` |
| Level-up from use, training or a GM award (`DevelopmentPoints.award_points`) | `DEVELOPMENT_LEVEL_UP` |

`set_skill_trait` also aligns the skill's `DevelopmentPoints` ledger to the rating it writes.
An NPC copy and a preset write the trait rows in bulk and align the ledger themselves.
Journeys: `integration_tests/test_trained_skills_journeys.py`.

### A card's bonus on a skill (#4820, slice 1 of #4813)

A distinction effect reaches a skill the way it reaches a stat: through a stat-category
`mechanics.ModifierTarget` whose `target_trait` is the skill's trait. `TraitHandler.get_trait_value`
folds that target's contributions for `TraitType.SKILL` as for `STAT` (the stat lane, #4726), in
the skill's own units (`+10 sailing` is +10 shown), and `TraitHandler.get_trait_modifier(trait)`
is the bonus alone. **The stored rating is never modified**: the trait row stays the trained
value, so a bonus never raises the cost of the next rank, and the
sheet's `SkillEntry` carries `value` (stored plus `modifier`, the number a roll uses) beside
`modifier`, with `at_boundary` read from the stored rating.

The target is made by `mechanics.services.ensure_skill_target(trait)`: both admin paths that save a
skill call it (`SkillAdmin.save_model` through `ensure_skill_target_or_warn`, and
`TraitAdmin.save_model` for a skill-type trait), and the Distinction Builder's paste calls it at create time when an
effect names a skill with no target yet (the preview row says so), so a new skill takes a bonus
the first time a card names it. A same-named target in another category (the `stealth` roll
modifier that predates the Stealth skill) is left alone: staff retarget it by hand. The sheet
prices skills through `trait_modifiers_for_sheet`, which picks a skill when a card, a
condition or worn equipment (a crafted piece or the equipment walk) bonuses it, so a bonus
from gear alone shows on the sheet as it rolls.
Journeys: `integration_tests/test_skill_bonus_journeys.py`.

### XP Boundaries (19, 29, 39, 49) — plateau, not a stop (#2115)

A skill value ending in 9 (`_is_at_xp_boundary`, `services.py`) is a **breakthrough
plateau** for every source of development, use and GM awards as well as training (owner
ruling on #5010): `DevelopmentPoints.award_points` parks a skill trait there. Incoming
points keep paying off rust (a boundary-parked skill can still "blow the rust off"), but
any surplus beyond the rust payoff **dissipates**: it is deliberately ephemeral, never
banked. A training dissipation is reported: `train_skill` returns a plateau message
("`<skill>` is at threshold `<N>.0` — training maintains, does not advance until the
breakthrough is unlocked.") which `process_weekly_training` folds into the
`DevelopmentTransaction.description` audit row. The same rule applies when a level-up's
overflow lands exactly on a boundary — the overflow dissipates with the same message
rather than banking or silently zeroing.

The gate clears via `purchase_skill_breakthrough(character, skill)` — an XP spend against
an authored `progression.TraitRatingUnlock` (`trait=skill,
target_rating=skill_value.value + 1`), mirroring `spend_xp_on_unlock`'s XP-debit pattern.
The purchase does not itself grant a level (ADR-0053: XP buys the unlock that gates, never
the grant) — it raises the rating to the target, and `set_skill_trait` raises the
`DevelopmentPoints` ledger to it, so development resumes from zero toward the next level
(no retroactive credit for points that dissipated while gated). `skills_at_boundary(character)` is the selector
that surfaces every gated skill (with its authored XP cost, or `authored=False` when staff
hasn't authored a breakthrough for that boundary yet) — feeds the `training` listing's
plateau annotation, the `progression unlocks` listing's `[skill]` section, and the
character-sheet `SkillEntry.at_boundary` flag. Reachable via
`progression unlock skill=<id>` (telnet) or the `PurchaseUnlockAction`
`unlock_type="skill_breakthrough"` branch (web/telnet convergence point) — see
`docs/systems/progression.md`'s Unlock Shop section. A default breakthrough catalog (flat
placeholder costs at each skill's 20/30/40/50 boundaries) is seeded by
`world.seeds.game_content.skills.seed_skill_breakthrough_catalog()` (the `"skills"`
cluster), so no skill is a landmine with no purchasable unlock out of the box.

### Band skill cap (#4585)

Skills are capped by the character's level band exactly as stats are. Staff author
`MaturationStatCap.skill_cap` (admin label "Band caps") per `PathStage` band, beside
`stat_cap`, in shown units: a cap of 3 is a skill shown at 3.0, stored 30. Blank, or no
row for the band, means no cap; the seeds author none. `skill_cap_for(sheet)`
(`world.progression.services.maturation`) reads it through the same band lookup as
`stat_cap_for`; `stored_skill_cap(sheet)` (`world.skills.services`) converts it to the
stored ceiling at the comparison (ADR-0193). The cap binds a skill and its
specializations at every post-creation raise:

| Raise path | At the cap |
|------------|------------|
| Training and Academy (`train_skill`, through `DevelopmentPoints.award_points`) | Stops at the cap; surplus dissipates as at an XP boundary, with a message naming the cap folded into the `DevelopmentTransaction.description` |
| `points_to_next_boundary` | Counts up to the cap when it comes before the next boundary; a skill at its cap takes only its rust |
| Specialization training (`_apply_development_to_specialization`) | Same stop and message |
| XP breakthrough (`purchase_skill_breakthrough`) | Refused, with the cap message, when the target rating is above the cap; no XP is spent |
| Use, GM awards (`DevelopmentPoints.award_points`, SKILL traits only) | Stops at the cap; surplus `total_earned` dissipates. `award_development_points` appends the cap message to the transaction's description. Stats and other traits are untouched |
| Staff edit (`set_skill_values`, `enforce_caps=True`) | `SheetWriteError` above the cap. Character creation passes `enforce_caps=False` and keeps `SkillPointBudget.max_skill_value` |

A skill already above its cap (made that way, or a band row lowered later) is not
lowered; it just cannot rise. Journeys: `integration_tests/test_skill_band_cap_journeys.py`.

### CG Point Budget
- Path points (default 50): Suggested by path template, freely redistributable
- Free points (default 60): Player's choice
- Total: 110 points (default)
- Cost: 10 per tier (flat rate)
- Specialization unlock: Parent skill must reach 30 (configurable)
- **Magic skills are not bought with these points (#4457, ADR-4457-A).** A skill in the MAGIC
  trait category (`magic_category_skills()`), or a specialization of one, is refused by the skills
  stage (`CharacterDraft.validate_path_skills`, called by `get_skill_allocation_errors`, naming each, message
  `MAGIC_SKILL_POINTS_REFUSAL`). They start at the values the player spent their magical training points on
  (`CharacterDraft.magic_training_pool`, from the Tradition schooling stance and other distinctions), or untrained; see `docs/systems/magic.md`,
  "Tradition training and Academy skill courses".

---

## Key Methods

### Skill (a proxy of Trait)

```python
from world.skills.models import Skill

skill = Skill.objects.get(pk=1)  # only skill-type traits; skill.pk is the trait's pk
skill.name, skill.category, skill.tooltip  # Trait's own fields
Skill.objects.create(name="Sailing", category=...)  # save() sets trait_type=SKILL
```

`Skill` shares `Trait`'s identity map, so a row read through `Skill` can be the cached
`Trait` instance. Put skill behaviour on `Trait` (`cached_specializations` is there), not on
the proxy.

### Specialization

```python
from world.skills.models import Specialization

spec = Specialization.objects.get(pk=1)
spec.parent_name  # -> self.parent_skill.name
```

### Skill ratings / CharacterSpecializationValue

```python
from world.skills.models import CharacterSpecializationValue
from world.skills.services import skill_rating

skill_rating(sheet, skill)  # the skill trait's value via character.traits, 0 if unrated
spec = CharacterSpecializationValue.objects.get(character=sheet, specialization=spec)
```

### SkillPointBudget (single-row configuration)

```python
from world.skills.models import SkillPointBudget

# Get or create the active budget (atomic, uses pk=1)
budget = SkillPointBudget.get_active_budget()

budget.total_points  # path_points + free_points (default 110)
budget.path_points   # 50
budget.free_points   # 60
budget.points_per_tier  # 10
budget.specialization_unlock_threshold  # 30
```

---

## API Endpoints

### Skills
- `GET /api/skills/skills/` - List all active skills (light serializer, no specializations)
- `GET /api/skills/skills/{id}/` - Get single skill with nested specializations
- `GET /api/skills/skills/with_specializations/` - All skills with specializations in one request (for CG)

**Query Parameters:**
- `is_active` - Filter by active status (defaults to active only)

### Specializations
- `GET /api/skills/specializations/` - List all active specializations
- `GET /api/skills/specializations/{id}/` - Get single specialization

**Query Parameters:**
- `parent_skill` - Filter by parent skill ID
- `is_active` - Filter by active status (defaults to active only)

### Path Skill Suggestions
- `GET /api/skills/path-skill-suggestions/` - List path skill suggestions

**Query Parameters:**
- `character_path` - Filter by path ID

### Skill Budget
- `GET /api/skills/skill-budget/` - Get the active skill point budget (returns single object, not array)

---

## Admin

All models registered with appropriate admin interfaces:

- `SkillAdmin` (on the proxy, #5008) - where a skill is authored: name, category, description,
  tooltip, order, active and credits, with an inline `Specialization` editor; the trait type is
  not shown (always Skill). Save makes its modifier target. The Builders panel's "New skill" and
  "All skills" links open it. On the Trait page, a skill that has specializations cannot be
  retyped away from Skill.
- `SpecializationAdmin` - List/filter by `parent_skill` and active status, search by name and parent skill
- `CharacterSpecializationValueAdmin` - Shows `value`, `display_value`, `development_points`; filter by parent skill
- `SkillPointBudgetAdmin` - Single-row model; `has_add_permission` returns False if row exists, `has_delete_permission` always False

---

## Training Allocations

Persistent weekly training plans map Action Points to development-point gains for a single
skill or specialization. All mutations run through `ManageTrainingAction`
(`actions/definitions/progression.py`, registry key `manage_training`) and are reached by both
the web API and the telnet `training` command.

### Models

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TrainingAllocation` | One weekly plan entry | `character`, `skill` (XOR), `specialization` (XOR), `mentor` (optional Persona), `ap_amount` |

Constraints enforce exactly one of `skill`/`specialization`, `ap_amount >= 1`, and uniqueness
per `(character, skill)` and `(character, specialization)`.

### Service Functions (`world/skills/services.py`)

| Function | Purpose |
|----------|---------|
| `create_training_allocation(character, ap_amount, *, skill, specialization, mentor)` | Creates an allocation, validating the weekly AP budget |
| `update_training_allocation(allocation, *, ap_amount, mentor)` | Updates an existing allocation |
| `remove_training_allocation(allocation)` | Deletes an allocation |
| `calculate_training_development(allocation)` | Computes development points from the training formula |
| `process_weekly_training()` | Processes all allocations, awards dev points, consumes AP |
| `train_skill(sheet, skill, dev_points, *, description, stop_at_boundary=False) -> SkillTrainingResult` | The one writer for development from training (#4457): a skill the character has no rating in starts at `DP_BASE_LEVEL` (10); the points go into the skill trait's `DevelopmentPoints` ledger through `award_points` (#5010), and one `DevelopmentTransaction` records the points applied, stamped with the current `game_week`. The skill branch of `process_weekly_training()` and Academy skill courses both call it. With `stop_at_boundary=True` the points are clamped to `points_to_next_boundary`, so nothing dissipates; the caller keeps the excess. `SkillTrainingResult` (`world/skills/types.py`) carries `old_value`, `new_value`, `points_applied`, `plateau_message` |
| `points_to_next_boundary(tracker: DevelopmentPoints) -> int or None` | Development the skill can take before it parks at the next XP boundary (19, 29, 39, 49) or the band's skill cap, whichever comes first (#4585), read from its ledger (#5010): unpaid rust, then each level's cost up to the stop, less progress banked toward it. A skill already at a boundary or its cap can take only its rust; `None` above 49 with no cap (#4457) |
| `stored_skill_cap(sheet) -> int or None` / `skill_cap_message(name, stored_cap) -> str` | The band's skill cap as a stored value (`skill_cap_for(sheet) * 10`, `None` for no cap), and the message every raise path shows when development stops at it (#4585) |
| `next_xp_boundary(value) -> int or None` | The first XP boundary at or above `value`; where `award_points` parks a skill (#5010) |
| `skill_rating(sheet, skill) -> int` / `set_skill_trait(sheet, skill, value, source)` | Read a skill's rating, and set it directly (stamped, ledger aligned); the rating is the skill trait's `CharacterTraitValue` (#5010) |
| `run_weekly_skill_cron()` | Weekly training only (rust is the rollover's one pass, #5010); registered as `skills.weekly_training` in `world/game_clock/tasks.py` |

### Training Formula

```
base_gain     = 5 × AP × path_level
mentor_bonus  = (AP + teaching) × (mentor_skill / student_skill) × (relationship_tier + 1)
dev_points    = base_gain + mentor_bonus
```

### API Endpoints

- `GET /api/skills/training-allocations/` — List the played character's allocations plus remaining weekly AP budget
  - Response: `{ allocations: [...], remaining_weekly_budget: <int> }`
- `POST /api/skills/training-allocations/` — Create an allocation; body `{ skill_id | specialization_id, ap_amount, mentor_persona_id? }`
- `PATCH /api/skills/training-allocations/{id}/` — Update `ap_amount` and/or `mentor_persona_id`
- `DELETE /api/skills/training-allocations/{id}/` — Remove the allocation

All writes dispatch through `ManageTrainingAction` (`registry_key="manage_training"`) so the
web and telnet paths share the same validation and mutation logic.

### Telnet Command

Defined in `commands/progression.py`:

```
training                           — list allocations and weekly AP budget
training add skill=<id> ap=<n> [mentor=<id>]
training add spec=<id> ap=<n> [mentor=<id>]
training update id=<id> [ap=<n>] [mentor=<id>]
training remove id=<id>
```

`spec` is an alias for `specialization`. Omitting `mentor` on update leaves it unchanged;
`mentor=` (empty) clears the mentor.

### Cron

`run_weekly_skill_cron()` is registered in `world/game_clock/tasks.py` as the weekly task
`skills.weekly_training` (`interval=7 days`, anchored Sunday midnight EST / Monday 05:00 UTC,
same cadence as `weekly_rollover`). It processes every character's allocations, awards
`DevelopmentTransaction` rows with `source=TRAINING`, `reason=SYSTEM_AWARD` and the current
`game_week`. It applies no rust: the weekly rollover's skill development pass does, once,
and that game week stamp exempts a trained skill from it (#5010).

---

## Integration Points

- **Trait System**: `Skill` is a proxy of `Trait` (trait_type=SKILL), giving skills unified check resolution
- **Classes/Paths app**: `PathSkillSuggestion` links to `classes.Path` for CG skill templates
- **Character Creation**: Stage 5 uses skills for allocation with point budgets
- **Character Sheets**: Display skills, with `at_boundary` for a skill parked at an XP boundary
- **Checks app**: Skill values feed into check resolution via the Trait system. A roll can also
  add a skill it does not list on its check type, through `extra_traits` (#4450, ADR-4450); the skill
  scores, develops once per roll, and counts for thread matching like a check type's own skill.
- **Magic** (#4450): `MagicActivitySkill`, `TechniqueStyle.skill` (the casting style's skill,
  #5002) and `Technique.skill` point at `Skill` (PROTECT for the activity table, SET_NULL for the others), so
  staff choose which skills magical rolls add. A skill in the MAGIC trait category is not offered as
  a character's Anima Check skill (the cast would count it twice). See `docs/systems/magic.md`,
  "Magical skills".
- **NPC services** (#4457): an Academy skill course (`SKILL_COURSE` offer) develops a skill through
  `train_skill(..., stop_at_boundary=True)`, so development that would run past an XP boundary stays
  in the course rather than dissipating as weekly training's does. See `docs/systems/magic.md`,
  "Tradition training and Academy skill courses".
- **Action Points**: Training allocations consume weekly AP from `ActionPointPool`
- **Progression**: `process_weekly_training()` writes `DevelopmentTransaction` records (source `TRAINING`, reason `SYSTEM_AWARD`)
