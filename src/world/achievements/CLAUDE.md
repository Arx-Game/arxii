# Achievements App

Cross-cutting meta-engagement layer. Characters earn achievements for milestones
across every game system. Hidden by default, designed to surprise and delight.

## Models

### StatDefinition (SharedMemoryModel)
Lookup table for trackable stats. Normalizes stat keys so they stay in sync
between StatTracker and AchievementRequirement.
- key (unique): dot-separated identifier, e.g., 'relationships.total_established'
- name: player-facing display name
- description: what this stat measures

### StatTracker (SharedMemoryModel)
General-purpose counter for measurable character actions.
- FK to CharacterSheet, FK to StatDefinition, integer value
- UniqueConstraint on character_sheet + stat
- Uses SharedMemoryModel for caching

### Achievement (SharedMemoryModel)
Staff-defined achievement definitions.
- name, slug, description, icon
- hidden (default True), notification_level (Personal/Room/Gamewide)
- prerequisite (self FK for chained achievements)
- is_active flag

### AchievementRequirement
Conditions to earn an achievement. FK to StatDefinition with thresholds.
- Multiple per achievement (all must be met)
- comparison: gte, eq, lte
- `is_met(value)` method encapsulates comparison logic

### RewardDefinition (SharedMemoryModel)
Lookup table for rewards. Normalizes reward identifiers across game systems.
- key (unique): dot-separated identifier, e.g., 'title.champion'
- name: player-facing display name
- reward_type: TextChoices (title, bonus, cosmetic, prestige, **distinction**)
- modifier_target: FK to `mechanics.ModifierTarget` (nullable) — for BONUS rewards, *which* stat
  the bonus modifies (e.g. allure); the amount comes from `AchievementReward.reward_value`
- distinction: FK to `distinctions.Distinction` (nullable, `SET_NULL`, mirrors `modifier_target`)
  — for DISTINCTION rewards (#2037), *which* Distinction to grant/rank-up; the optional explicit
  rank comes from `AchievementReward.reward_value`

### AchievementReward
Links an achievement to a RewardDefinition with optional parameterization.
- FK to Achievement, FK to RewardDefinition
- reward_value: optional extra data — the **amount** for BONUS (e.g. "5") and PRESTIGE (e.g.
  "5000"), or an optional explicit **rank** for DISTINCTION (e.g. "3"; blank/invalid parses as
  "advance one step")

### CharacterTitle (SharedMemoryModel)
The cosmetic/display record of a title a character has earned (FK character_sheet, FK to a TITLE
`RewardDefinition`, `earned_at`; unique per (sheet, reward)). **Mechanical rewards do NOT live
here** — they attach to the *achievement* (see Reward application below); a title is display-only.

### Discovery
First-time-earned record. OneToOne to Achievement.
- Supports simultaneous co-discoverers (party kills, etc.)

### CharacterAchievement
Records when a character earned an achievement.
- FK to Discovery if they were a co-discoverer
- UniqueConstraint on character_sheet + achievement

## Reward application (#1522)

`grant_achievement` applies an achievement's rewards **once per newly-earned sheet** (then fires
the stories reactivity hook). `services.apply_achievement_rewards(sheet, achievement)` dispatches
by `reward_type`:
- **TITLE** → a `CharacterTitle` (idempotent via the unique constraint).
- **BONUS** → a `CharacterModifier` on `reward.modifier_target` (amount = `reward_value`), sourced
  via the shared `mechanics.ModifierSource.achievement_reward` marker (mirrors `residence_comfort`).
- **PRESTIGE** → `societies.renown.award_deed_prestige(persona, amount)` on the primary persona.
- **DISTINCTION** (#2037) → `distinctions.services.grant_distinction(sheet, reward.distinction,
  origin=DistinctionOrigin.ACHIEVEMENT_AUTO_GRANT, rank=...)` — `reward_value` parses as an
  explicit rank when a valid int, else `rank=None` (advance one step; NOT a no-op, unlike
  `_grant_bonus`'s parse-or-skip). A `DistinctionExclusionError` (mutual/variant conflict) is
  caught and logged — the distinction leg is skipped, the rest of the award proceeds unharmed.
- **COSMETIC** → no-op until that system exists.

Cross-app deps (mechanics/societies/distinctions) are **lazy-imported** so `achievements` stays
low-coupled.

Achievement-sourced BONUS modifiers ARE read by `get_modifier_total`: `get_modifier_breakdown`
counts *recognized* non-distinction sources (`achievement_reward`, `residence_comfort`) as flat
addends — orphaned/bare (UNKNOWN) sources still contribute nothing (#909).

## Displaying earned titles (#1522)

Titles are cosmetic and **public** — a character shows them off — so display is ungated.
`CharacterTitleViewSet` (`GET /api/achievements/character-titles/?character_sheet=<id>`,
`CharacterTitleSerializer` → the `CharacterTitle` schema: `title`, `reward_key`, `earned_at`)
lists a character's earned titles, newest first. Faces: the telnet `sheet/titles` section
(`commands.account.sheet_sections._render_titles_section`, registered in `SHEET_SECTIONS`) and the
React **Titles** tab (`frontend/src/achievements/TitlesPanel` on `CharacterSheetPage`). The title's
player-facing name is the linked TITLE `RewardDefinition.name`.

## StatHandler (handlers.py)

Cached stat handler attached to CharacterSheet as `@cached_property`:
```python
character_sheet.stats.get(stat_def)           # Returns int, 0 if not tracked
character_sheet.stats.increment(stat_def, 3)  # Atomic increment, returns new value
```
- Lazily loads all stat values on first access
- Mutations update both DB (atomic F() expression) and local cache
- Automatically checks for newly met achievement requirements after increment

## Integration Pattern

Other apps use the StatHandler via CharacterSheet — no Django signals:
```python
from world.achievements.models import StatDefinition

stat_def = StatDefinition.objects.get(key="relationships.total_established")
character_sheet.stats.increment(stat_def)
```

Service functions `get_stat()` and `increment_stat()` are thin wrappers around
the handler for backward compatibility.

Since StatDefinition is a SharedMemoryModel, `.get()` hits the in-memory cache after first access.

## DiscoverableContent abstract base (#1606)

`DiscoverableContent` (`achievements/models.py`) is a Django abstract base (no table) that adds a
single nullable `discovery_achievement` FK (→ `Achievement`, `on_delete=PROTECT`, `related_name="+"`)
to any content model whose instances can trigger a first-ever Discovery ceremony. Inherited by:
- `world.magic.Technique` — a technique can be marked discoverable (first character ever to gain it)
- `world.covenants.CovenantRole` — a sub-role can be marked discoverable at its thread threshold

`discovery_achievement = None` means the content is not discoverable and `announce_access_change`
skips the Discovery path for it. See **ADR-0061** for the architectural decision (GenericFK and
per-model duplication were both rejected).

## Access-change + discovery surface (`discovery.py`, #1606)

Two public functions in `achievements/discovery.py` form the shared announcement surface:

### `announce_access_change(character_sheet, *, gained, lost, source)`

Called whenever any mechanism changes what techniques/capabilities a character can use:

- Sends one `NarrativeCategory.ABILITY` message listing what was gained/lost.
- For each gained item with a non-null `discovery_achievement`, calls `grant_achievement` and then
  `announce_achievement` (gamewide first-ever body if it's a Discovery, personal otherwise).
- **Never branches on source** — covenant, form shapeshift, and CG cantrip are all identical.
- `source` is an `AccessChangeSource` TextChoices value (drives the lead-in text label).

Current callers:
- `world/forms/services.py` — assume / revert alternate self
- `world/covenants/services.py` — `_announce_capability_diff` (engage / disengage covenant role)
- `world/character_creation/services.py` — CG cantrip grant

### `announce_achievement(earners, *, is_first, first_body, personal_body, category)`

Sends one `NarrativeMessage`:
- `is_first=True` → **gamewide** to all active player sheets via `active_player_character_sheets()`,
  using `first_body` (which must NOT name the discoverer).
- `is_first=False` → **personal** to the `earners` list, using `personal_body`.

Also used directly by `world/covenants/discovery.py::_notify` (sub-role discovery ceremony).

## Key Rules

- Achievements are hidden by default — surprise and delight
- Notification level is per-achievement (personal, room, gamewide)
- Discovery tracks first-to-achieve with co-discoverer support
- StatDefinition normalizes stat keys — no raw strings in FKs
- RewardDefinition normalizes reward keys — no raw strings for rewards
- Service functions accept StatDefinition instances, not string keys
- All achievements are hand-crafted by staff (no auto-generation)
- Character ownership queries use RosterTenure chain, NOT db_account
- **`announce_access_change` is source-agnostic** — never add a source branch inside it;
  place source-specific pre/post logic in the caller instead
