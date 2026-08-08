# Achievements App

Cross-cutting meta-engagement layer. Characters earn achievements for milestones
across every game system. Hidden by default, designed to surprise and delight.

## Models

### StatDefinition (SharedMemoryModel)
Lookup table for trackable stats. Normalizes stat keys so they stay in sync
between StatTracker and AchievementStatRequirement.
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

### AchievementStatRequirement
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
- `discovered_by_tenure` (required FK -> `roster.RosterTenure`, `on_delete=PROTECT`): the
  tenure (character piloted by a player) that first discovered this achievement. Discoveries
  are partly-OOC accolades players accumulate via their characters, and the tenure is the
  (player-as-this-character) join object — a sheet with no player tenure is structurally
  incapable of claiming a first-ever slot (#3055). `grant_achievement` resolves this from
  the FIRST eligible sheet in the (already `can_earn_achievements`-filtered) list passed
  in — the triggering sheet for party grants; co-earners still get `CharacterAchievement`
  rows via the shared `discovery`, but only one Discovery row is ever created per achievement.
- `shared_with_tenures` (M2M -> `roster.RosterTenure`): the OTHER simultaneous
  co-discoverers of that first-ever grant (a party or covenant finding it together). A
  player's full discovery record is the union of their tenures' `discoveries` (primary)
  and `shared_discoveries` (shared credit); display may denote the latter as "shared"
  (#3055 ruling). Later earners of the same achievement get neither — they were not
  part of the first-discovery moment.

**Display rule (#3063, ruled 2026-08-07):** shared iff `shared_with_tenures` is
non-empty; the primary `discovered_by_tenure` FK is pure bookkeeping in the group case
(it has to point somewhere) and must never be read as a display privilege — every
participant of a group discovery displays symmetrically as "shared". Implemented as
`DiscoverySerializer.shared` (`serializers.py`).

**Group grants must be ONE `grant_achievement` call, never a per-sheet loop.** Calling
`grant_achievement(achievement, [sheet])` (or the `execute_ceremony_beat` wrapper around
it) once per participant lets the first iteration's call create the sole `Discovery` row
before the rest ever run — every later participant earns a `CharacterAchievement` but
never lands in `shared_with_tenures`, so a party discovery looks solo to everyone but the
first sheet. Pass the whole eligible group to a single `grant_achievement(achievement,
sheets)` call instead (`world/combat/combo_discovery.py::fire_combo_discovery` is the
reference implementation — see its module docstring for why it bypasses
`execute_ceremony_beat`'s per-sheet shape). Two other group-earning moments — combat
encounter completion (`world/combat/services.py`) and relationship reciprocation
(`world/relationships/services.py`) — currently reach `grant_achievement` only through the
single-sheet `StatHandler.increment` → `_check_achievements` indirection and are NOT yet
batched; fixing them needs a batch stat-check seam, tracked as a follow-up, not fixed here.

### CharacterAchievement
Records when a character earned an achievement.
- Required `earned_by_tenure` FK -> `roster.RosterTenure` (`on_delete=PROTECT`, #3055):
  stamped from the earning sheet's current tenure inside `grant_achievement` (the same
  `can_earn_achievements` gate already guarantees one exists). Every co-earner of a party
  grant gets their own individually durable (player, character) pairing, not just the
  primary Discovery slot's discoverer — the acquisition-provenance ledger's achievement leg.
- `is_discoverer()` — no `discovery` FK exists on this model (removed #3055: tenure records
  are the single discovery-credit mechanism, replacing a redundant parallel FK whose credit
  died with the character and couldn't distinguish primary/shared). Derives discoverer status
  by comparing `earned_by_tenure` against the achievement's `Discovery.discovered_by_tenure`
  (primary) and `shared_with_tenures` (shared). Callers iterating many rows should
  `select_related("achievement__discovery")` and prefetch
  `achievement__discovery__shared_with_tenures` (see `CharacterAchievementViewSet.get_queryset`)
  to avoid N+1.
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
- `world.codex.CodexEntry` — a piece of lore can be marked discoverable (first character ever to
  learn it); see the CG-catalog exclusion note under `announce_access_change` below (#2899)

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
- **Never branches on source** — covenant, form shapeshift, and CG gift/technique grant are all identical.
- `source` is an `AccessChangeSource` TextChoices value (drives the lead-in text label).
- **Two eligibility gates run before the per-item loop, both source-agnostic:** (1) the receiving
  character must have a current, non-staff `RosterTenure`, which is now the shared
  `can_earn_achievements` predicate in `achievements/services.py`, enforced globally inside
  `grant_achievement` itself, not a local check here. `announce_access_change` additionally skips
  its own ceremony for an ineligible sheet before the per-item loop, so the plain gained/lost
  message above still sends even when the ceremony is skipped; (2) content reachable through a CG
  catalog table never fires the ceremony regardless of route (`_cg_catalog_exclusions`, covering
  `CodexEntry` via Beginnings/Tradition/Path/Distinction/Species/Resonance grants, and `Technique`
  via `PathGiftGrant`/`TraditionGiftGrant`). See #2899.
- Every `grant_achievement` caller (the stat-threshold path, worship favor, `execute_ceremony_beat`
  for crossing/combo/signature ceremony beats, and aura thresholds) now inherits the eligibility
  invariant at the chokepoint, not just the six `announce_access_change` callers listed below.
  `execute_ceremony_beat`'s `is_first` derives from `grant_achievement`'s returned
  `AchievementGrantResult.created_discovery` (non-None only when this call minted the
  achievement's Discovery row), so an ineligible sheet can never trigger the gamewide
  first-ever announcement (#3024, ADR-0202). The
  CG-catalog exclusion gate (2) above remains `announce_access_change`-local by design, since it is
  about content reachability, not earner eligibility.

Current callers:
- `world/forms/services.py` — assume / revert alternate self
- `world/covenants/services.py` — `_announce_capability_diff` (engage / disengage covenant role)
- `world/character_creation/services.py` — CG gift/technique grant (`AccessChangeSource.CHARACTER_CREATION`)
- `world/magic/services/technique_acquisition.py::learn_technique` — a character learns a
  technique post-CG (`AccessChangeSource.TECHNIQUE_GRANT`)
- `world/magic/services/path_magic.py::grant_path_magic` — advancing into a new Path
  (`AccessChangeSource.PATH_ADVANCEMENT`)
- `world/codex/services.py::grant_codex_entry` — every route that lands a character on KNOWN
  (CG grant, clue-research payoff, the crossing ceremony) on `newly_known`
  (`AccessChangeSource.CODEX_LEARNING`, #2899). `CodexTeachingOffer.accept` only opens the
  UNCOVERED row — a taught entry fires the ceremony once something else (e.g. research)
  completes it through this same function.

### `announce_achievement(earners, *, is_first, first_body, personal_body, category)`

Sends one `NarrativeMessage`:
- `is_first=True` → **gamewide** to all active player sheets via `active_player_character_sheets()`,
  using `first_body` (which must NOT name the discoverer).
- `is_first=False` → **personal** to the `earners` list, using `personal_body`.

`world/covenants/discovery.py` is now a backwards-compatible re-export shim around
`world.magic.crossing.ceremony.execute_crossing_ceremonies` (ADR-0094); it has no `_notify`
function. `announce_achievement`'s direct callers are `announce_access_change` (in its per-item
loop above) and `execute_ceremony_beat` (`world/magic/crossing/ceremony.py`).

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
- **Only eligible earners (current, non-staff tenure, `can_earn_achievements`) can earn
  achievements**, enforced inside `grant_achievement`, never per-caller
