# Skills System - Character Abilities and Specializations

Skills (a proxy of Trait, #5008) and specializations for character abilities.

## Key Files

### `models.py`
- **`Skill`**: proxy of `Trait` for skill-type traits (Melee Combat, Persuasion, etc.); no
  table (#5008). See `docs/systems/traits.md`, "A skill is a Trait"
- **`Specialization`**: Specific application under a parent skill (Swords, Seduction)
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
- A character's rating in a skill is the skill's own `CharacterTraitValue` (#5010): one
  row the sheet shows and checks read. Read it with `skill_rating(sheet, skill)` (through the character's trait handler); set it
  directly with `set_skill_trait`
- Stored and shown: 10, 20, 30... (one scale, ADR-5091; never divided for display)
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

- **Trait System**: a skill is a Trait (the `Skill` proxy), so checks read it like any trait
- **Character Creation**: Stage 5 uses skills for allocation
- **Character Sheets**: Display skills with development progress
- **Progression**: XP and development point advancement (separate system)

## Training System

### Models
- **`TrainingAllocation`**: Persistent weekly training plan entry. FK to character, skill/specialization (XOR), optional mentor guise, AP amount, and `mentor_accepted_at` (empty while a named mentor has not agreed). Characters can have multiple allocations.

### Service Functions (`services.py`)

**CRUD:**
- `create_training_allocation(character, ap_amount, *, skill, specialization, mentor)` — creates allocation, validates the weekly AP budget. **That budget is shared with ties (#3957):** the check sums this character's training allocations AND their standing `RelationshipAllocation` rows (`world.relationships.services.standing_tie_ap`) against `ActionPointConfig.get_weekly_regen()`, because both are paid from the one `ActionPointPool` at the weekly turn. The tie door enforces the same total from its side (`set_allocation`, via `standing_weekly_ap`).
- `update_training_allocation(allocation, *, ap_amount, mentor)` — updates allocation, against that same shared budget (its own row excluded)
- **Both ask the Tradition rule first (#5326, ADR-5326).** No Magic-category skill is learned by self-study: `_training_refusal` builds a one-character `TeachingContext` and asks `world.magic.services.tradition_teaching.training_asking_refusal`, and a refusal raises `ValueError` with the line the player reads (`ManageTrainingAction` turns it into the message, so telnet and web share it). A Magic skill (or a specialization of one, judged on its parent) needs a mentor unless `world.mechanics.levers.self_teaching_granted(sheet)` is true, and the mentor is never her own character or another character her player plays. **Naming a mentor only asks her, and asking reads nothing about her** (no Tradition, no rating), so the student learns nothing about the named character. An update re-checks on every call, judging the allocation as it would stand, so clearing the mentor on a Magic skill is refused. A skill outside the Magic category is never refused for want of a mentor. Do not add a second reading of "who may teach"; call `training_verdict` for an agreed mentor
- **The mentor must agree (#5326, ADR-5326).** `world/skills/mentoring.py` owns it. `mentor_accepted_at` is empty until she agrees and a mentor who has not agreed counts as no mentor everywhere: `mentor_has_agreed` / `mentor_is_waiting` are the two readers (`calculate_training_development` pays the mentor bonus only for an agreed mentor; `training_verdict(..., mentor_agreed=)` and `_weekly_teaching_context` read the same). Naming a mentor saves the row waiting and sends her character one line (`ask_mentor`); a different mentor clears the agreement and asks again, and only the action points changing keeps it. She answers as an account: `accept_mentoring` (checks the mentor's own facts with `mentor_acceptance_refusal` and refuses to her with the one that fails), `decline_mentoring`, `stop_mentoring`, and `mentoring_for_account(account)` is the list (requests and students, each row naming the persona asked). Who may answer is ONE function, `answerable_allocation_ids(account, allocations)`: the account that plays the mentor's character now, else the creator of its roster entry, staff always, the student's player never. Never write a second one; the services, the telnet list and the REST scoping all call it. `AnswerMentoringAction` (`answer_mentoring`) is the action telnet and REST dispatch; REST passes the requester as the server-supplied `account` and returns 404 for an id she may not answer for
- `mentor_needed_line(teaching, allocation)` returns the teacher line when the weekly run would skip a row for want of a mentor, else None: no mentor (her own persona counts as none), a Magic skill (a specialization is judged on its parent) and no self-teaching lever. It calls `_weekly_refusal`, the weekly run's own verdict, so the training card's `mentor_needed_line` field can never disagree with the week. Build `teaching` once for the page with `training_teaching_context(allocations)` and pass it to `TrainingAllocationSerializer` as `context["teaching_context"]`; never build a context per row
- `remove_training_allocation(allocation)` — deletes allocation

**Calculation:**
- `calculate_training_development(allocation)` — computes dev points from training formula

**Cron Processing:**
- `process_weekly_training()` processes all allocations, awards dev points, consumes AP. It builds one `TeachingContext` for the whole run (`_weekly_teaching_context`, which reads the self-teaching lever only for characters with a Magic allocation that has no mentor or a waiting one), asks `training_verdict` again per allocation, and skips a refused one (`_skip_refused_allocation`): no development, no AP spent, the row stays, and one `SYSTEM` narrative line goes to the character
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
- A step from value N to N+1 costs `dp_cost_for_step(N)` dev points: one geometric curve held
  in the `DevelopmentCostConfig` row (`world/progression/services/dev_cost.py`, #5093), a tenth of
  the band N // 10, the same for skills, specializations and threads
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
- **Band skill cap (#4585):** `MaturationStatCap.skill_cap` (stored units, #5091; blank = no cap) caps every
  skill and specialization by the character's level band, like `stat_cap`. `stored_skill_cap(sheet)`
  returns it (`skill_cap_for(sheet)`). `train_skill`, `points_to_next_boundary`,
  `_apply_development_to_specialization`, `purchase_skill_breakthrough`,
  `DevelopmentPoints.award_points` (SKILL traits only) and staff edit's `set_skill_values` all stop
  there; development at the cap dissipates as at an XP boundary, with `skill_cap_message` naming
  the cap. Any new skill raise path must check it too.

### Rust System
- Idle skills accumulate `character_level + 5` rust debt per week; outstanding debt never
  exceeds the current level's cost (`apply_skill_rust`)
- Only characters on an active, non-dormant roster rust; NPCs and dormant characters do not
- Dev points pay off rust before counting toward advancement
- Training or use in a week prevents rust for that week

### Integration Points
- **Action Points**: AP consumed at weekly cron from `ActionPointPool`
- **Progression**: Creates `DevelopmentTransaction` audit records with `DevelopmentSource.TRAINING` source and `ProgressionReason.SYSTEM_AWARD` reason. Uses the skill (Skill is a proxy of Trait), or a specialization's parent skill, as the transaction trait.
- **Relationships**: `get_relationship_tier()` stub in `world.relationships.helpers` (TODO: implement)
- **Guise**: Mentor FK points to character_sheets.Guise
