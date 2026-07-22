# Progression System

XP, kudos, development points, character-level XP, path history, and unlock system for character advancement.

**Source:** `src/world/progression/`
**API Base:** `/api/progression/`

---

## Enums (types.py)

```python
from world.progression.types import (
    UnlockType,          # LEVEL, SKILL_RATING, STAT_RATING, ABILITY, OTHER
    DevelopmentSource,   # SCENE, TRAINING, PRACTICE, TEACHING, QUEST, EXPLORATION, CRAFTING, COMBAT, SOCIAL, OTHER
    ProgressionReason,   # XP_PURCHASE, CG_CONVERSION, SCENE_AWARD, GM_AWARD, SYSTEM_AWARD, REFUND,
                         # CORRECTION, KUDOS_CLAIM, FIRST_IMPRESSION, VOTE_REWARD, MEMORABLE_POSE,
                         # RANDOM_SCENE, GM_STORY_REWARD (#2123 — GM Story Reward, see gm-system.md), OTHER
)

# Typed data structures
from world.progression.types import (
    AwardResult,   # Dataclass: points_data (KudosPointsData), transaction (KudosTransaction)
    ClaimResult,   # Dataclass: points_data (KudosPointsData), transaction (KudosTransaction), reward_amount (int)
)
```

---

## Models

### Account-Level Rewards (XP)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ExperiencePointsData` | Account XP balance (one per account) | `account` (PK, OneToOne AccountDB), `total_earned`, `total_spent` |
| `XPTransaction` | Audit trail for all account XP changes | `account`, `amount`, `reason` (ProgressionReason), `description`, `character`, `gm`, `transaction_date` |

### Character-Level XP

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterXP` | Per-character XP balance, partitioned by transferability | `character`, `total_earned`, `total_spent`, `transferable` |
| `CharacterXPTransaction` | Audit trail for character-level XP changes | `character`, `amount`, `reason` (ProgressionReason), `description`, `transferable`, `transaction_date` |

### Development Points (Auto-Applied Trait Growth)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DevelopmentPoints` | Per-character, per-trait development tracker | `character`, `trait`, `total_earned` |
| `DevelopmentTransaction` | Audit trail for all development point awards | `character`, `trait`, `source` (DevelopmentSource), `amount`, `reason`, `description`, `scene`, `gm`, `transaction_date` |

### Kudos ("Good Sport" Currency)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `KudosSourceCategory` | Staff-configurable award categories (SharedMemoryModel) | `name`, `display_name`, `description`, `default_amount`, `is_active`, `staff_only` |
| `KudosClaimCategory` | Staff-configurable claim/conversion types (SharedMemoryModel) | `name`, `display_name`, `description`, `kudos_cost`, `reward_amount`, `is_active` |
| `KudosPointsData` | Account kudos balance (one per account) | `account` (PK, OneToOne AccountDB), `total_earned`, `total_claimed` |
| `KudosTransaction` | Audit trail for all kudos awards and claims | `account`, `amount`, `source_category`, `claim_category`, `description`, `awarded_by`, `character`, `transaction_date` |

### XP Cost System (SharedMemoryModel - cached)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `XPCostChart` | Reusable cost curves for classes/traits | `name`, `description`, `is_active` |
| `XPCostEntry` | Individual level/cost entries within a chart | `chart`, `level`, `xp_cost` |
| `ClassXPCost` | Links classes to cost charts with optional modifier | `character_class`, `cost_chart`, `cost_modifier` (percentage, 100 = normal) |
| `TraitXPCost` | Links traits to cost charts with optional modifier | `trait`, `cost_chart`, `cost_modifier` (percentage) |

### Unlock Types

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ClassLevelUnlock` | Unlocking a new level in a character class | `character_class`, `target_level` |
| `TraitRatingUnlock` | Unlocking a major trait rating threshold. Wired for skill XP boundaries via `purchase_skill_breakthrough` (`world.skills.services`, #2115) — `trait` resolves to `Skill.trait`, `target_rating` to the skill's next rating (20/30/40/50) | `trait`, `target_rating` (divisible by 10) |
| `CharacterUnlock` | Records what class levels a character has unlocked | `character`, `character_class`, `target_level`, `unlocked_date`, `xp_spent` |

### Requirements (Abstract Hierarchy)

All requirements inherit from `AbstractClassLevelRequirement` which provides `description`, `is_active`, and FK to `ClassLevelUnlock`. Each implements `is_met_by_character(character)` returning `(bool, str)`.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `TraitRequirement` | Minimum trait value required | `trait`, `minimum_value` |
| `LevelRequirement` | Minimum character level in any class | `minimum_level` |
| `ClassLevelRequirement` | Minimum level in a specific class | `character_class`, `minimum_level` |
| `MultiClassRequirement` | Multiple classes at specific levels (via `MultiClassLevel` through model) | `required_classes`, `description_override` |
| `TierRequirement` | Character has reached a specific tier | `minimum_tier` (1 for levels 1-5, 2 for 6-10) |
| `AchievementRequirement` | Character has been granted a specific Achievement | `achievement` (FK `achievements.Achievement`) |
| `RelationshipRequirement` | Character's own relationship-track tier count (#2116) | `required_track_kind` (nullable FK `relationships.RelationshipTrack`, null = any track), `minimum_tier`, `minimum_count` (default 1) |
| `ItemRequirement` | Possesses a physical touchstone/trophy item (#1859) | `item_template` XOR `min_touchstone_tier` (FK `magic.ResonanceTier`), `quantity`, `min_quality_tier` — possession-only, not consumed |
| `LegendRequirement` | Minimum total legend value | `minimum_legend` |
| `MajorGiftTechniqueRequirement` | Knows >= N techniques of the character's MAJOR gift (#2440 ruling 4) — a COUNT gate, not completeness; minor-gift techniques never count. Seeded onto the level-2 `ClassLevelUnlock` via `world.progression.seeds.seed_major_gift_technique_level_requirement` | `minimum_techniques` (default 3) |
| `CodexKnowledgeRequirement` | Gates Path selection (and class-level unlocks / thread crossings) behind codex knowledge. A character must have learned the specified `CodexEntry` (at `KNOWN` status in `CharacterCodexKnowledge`) before they can select that Path at a crossing. Fail-open: a Path with no `CodexKnowledgeRequirement` authored → gate passes. Composes with the existing `check_requirements_for_path` → `cross_into_path` gate — zero new gate wiring. Any discovery route that lands a KNOWN codex entry (CG grants, teaching offers, clue resolution, research projects) satisfies the gate (#2603) | `codex_entry` (FK `codex.CodexEntry`) |

### Class-Level Advancement Receipts (#1352)

`AbstractClassLevelAdvancement` is an **abstract** Django model that provides the
shared shape for a single class-level advance, whether within-tier (Ritual of the
Durance) or a tier crossing (Audere Majora). Both concrete models inherit it.

| Field | Purpose |
|-------|---------|
| `scene` FK → `scenes.Scene` | Scene in which the advance occurred (nullable, SET_NULL) |
| `declaration_interaction` FK → `scenes.Interaction` | Declaration pose; soft FK (`db_constraint=False` — partitioned table) |
| `level_before` PositiveSmallIntegerField | Class level immediately before the advance |
| `level_after` PositiveSmallIntegerField | Class level granted by the advance |
| `created_at` DateTimeField (auto) | Timestamp |

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ClassLevelAdvancement` | Receipt for one within-tier advance via the Ritual of the Durance. Survives character death. | inherits `AbstractClassLevelAdvancement` + `character_sheet` FK, `character_class` FK, `officiant` FK (nullable CharacterSheet — the trainer), `ritual` FK (nullable — the `Ritual` row that fired the session), `witnesses` M2M → `scenes.Persona` (`related_name="witnessed_advancements"`) |
| `DuranceTrainingSite` | A room registered as a Durance training site, bound to a trainer-of-record (officiant). Enables site-convened sessions without a live higher-level PC. (#1700) | `room_profile` FK → `RoomProfile` (PROTECT), `officiant` FK → `CharacterSheet` (PROTECT), `training_path` FK → `Path` (SET_NULL, nullable — display hint only), `is_active` Bool; unique `(room_profile, officiant)` |

`AudereMajoraCrossing` (in `world/magic`) inherits `AbstractClassLevelAdvancement` for
the same shape on tier crossings. The two share the `apply_class_level_advance` spine
in `world.progression.services.advancement`.

---

### Path History

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterPathHistory` | Tracks which path a character selected at each stage milestone | `character`, `path`, `selected_at` |

### Path Intent

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `PathIntent` | Player's declared preferred next path — one per character sheet | `character_sheet` (OneToOne FK → `CharacterSheet`), `intended_path` (FK → `Path`) |

### Progression Exceptions (`exceptions.py` — #1352 / #1700)

All carry a `user_message` attribute for safe API responses (no `str(exc)` in views).

| Exception | Raised when |
|-----------|-------------|
| `ClassLevelAdvancementError` | Base class for all advancement failures |
| `TierBoundaryRequiresCrossing` | The step would cross a tier boundary; must use Audere Majora instead |
| `AdvancementRequirementsNotMet` | Authored `ClassLevelUnlock` requirements not met; `.failed: list[str]` carries the failed requirement descriptions |
| `AdvancementUnlockNotPurchasedError` | The `CharacterUnlock` XP purchase for this class/target_level is missing (#2116) — an additional gate stacked alongside `AdvancementRequirementsNotMet`, never a substitute |
| `OfficiantIneligibleError` | Officiant level ≤ target level or wrong Path lineage |
| `NoDuranceSiteError` | `convene_durance_at_site` — no active `DuranceTrainingSite` with an eligible trainer in the room |
| `PathAlreadySelectedError` | `select_initial_path` — the character already has a `CharacterPathHistory` row; this is a one-time recovery, not a general path-change tool (#2121) |

---

## Key Methods

### ExperiencePointsData / CharacterXP

```python
from world.progression.models import ExperiencePointsData, CharacterXP

# Account-level XP
xp_data = ExperiencePointsData.objects.get(account=account)
xp_data.current_available  # Property: total_earned - total_spent
xp_data.can_spend(100)     # Check if enough XP
xp_data.spend_xp(100)      # Spend XP (returns bool)
xp_data.award_xp(50)       # Award XP

# Character-level XP (partitioned by transferable flag)
char_xp = CharacterXP.objects.get(character=character, transferable=True)
char_xp.current_available  # Property: total_earned - total_spent
char_xp.spend_xp(50)       # Returns bool
char_xp.award_xp(25)       # Awards XP
```

### DevelopmentPoints

```python
from world.progression.models import DevelopmentPoints

dev = DevelopmentPoints.objects.get(character=character, trait=trait)
# Awards points AND automatically applies them to CharacterTraitValue
# Caps at major thresholds (multiples of 10) if unlock not present
dev.award_points(5)
```

### KudosClaimCategory

```python
from world.progression.models import KudosClaimCategory

claim_cat = KudosClaimCategory.objects.get(name="xp")
claim_cat.calculate_reward(kudos_amount=20)       # How much reward for 20 kudos
claim_cat.calculate_kudos_needed(reward_amount=5)  # How many kudos for 5 reward units
```

### XP Cost Lookups

```python
from world.progression.models import XPCostChart, ClassXPCost, TraitXPCost

chart = XPCostChart.objects.get(name="Standard")
chart.get_cost_for_level(3)  # Base XP cost for level 3

class_cost = ClassXPCost.objects.get(character_class=my_class)
class_cost.get_cost_for_level(3)  # Modified cost (applies cost_modifier percentage)

trait_cost = TraitXPCost.objects.get(trait=my_trait)
trait_cost.get_cost_for_rating(20)  # Modified cost for rating threshold
```

### Unlock / Requirement Checking

```python
from world.progression.models import ClassLevelUnlock

unlock = ClassLevelUnlock.objects.get(character_class=my_class, target_level=5)
xp_cost = unlock.get_xp_cost_for_character(character)
```

---

## Service Functions

### Awards (`services.awards`)

```python
from world.progression.services import award_xp, award_development_points, get_or_create_xp_tracker
from world.progression.types import DevelopmentSource, ProgressionReason

# Award account-level XP (atomic, creates transaction)
transaction = award_xp(account, 50, reason=ProgressionReason.GM_AWARD, description="Quest reward", gm=gm_account)

# Award development points (auto-applies rate modifiers from distinctions)
transaction = award_development_points(
    character=character,
    trait=trait,
    source=DevelopmentSource.COMBAT,
    amount=5,
    scene=scene,
    reason="Combat training",
    description="Earned during sparring scene",
    gm=gm_account,
)

# Get or create XP tracker
xp_tracker = get_or_create_xp_tracker(account)
```

**GM Story Reward (#2123):** the sole GM-side XP source in the game — `world.gm.services.award_gm_story_reward`
calls this same `award_xp` with `reason=ProgressionReason.GM_STORY_REWARD` (`gm=None` — it is a
system-issued award, not a manual GM correction). See [gm-system.md](../roadmap/gm-system.md) and
the GM entry in `INDEX.md` for the full players-served formula, weekly cap, and the three
convergence points (a GM-marked beat, a resolved episode, a completed story) plus the positive
story-feedback path.

### Spends (`services.spends`)

```python
from world.progression.services import spend_xp_on_unlock, check_requirements_for_unlock, get_available_unlocks_for_character

# Spend XP on an unlock (checks requirements, spends XP, creates records)
success, message, unlock = spend_xp_on_unlock(character, unlock_target, gm=None)

# Check requirements only
all_met, failed_messages = check_requirements_for_unlock(character, unlock_target)

# Get categorized unlocks for a character
result = get_available_unlocks_for_character(character)
# Returns: {"available": [...], "locked": [...], "already_unlocked": [...]}
```

### Path Requirements (#2538)

`AbstractUnlockRequirement` supports a third polymorphic target FK — `path` —
alongside `class_level_unlock` and `thread_crossing_threshold` (ADR-0090 pattern).
`TraitRequirement` and `CodexKnowledgeRequirement` rows authored against a `Path`
gate both hybrid path entry and cross-path technique learning.

```python
from world.progression.services.spends import check_requirements_for_path

# Check if a character meets a path's TraitRequirements
all_met, failed_messages = check_requirements_for_path(character, path)
# Returns: (True, []) when no requirements authored (fail-open)
```

**Hybrid path entry:** `cross_into_path` calls `check_requirements_for_path`
before switching, raising `PathRequirementsNotMet` when unmet. The semi-crossing
catches this for a non-breaking level-only advance; Audere Majora lets it propagate.

**Cross-path technique learning:** `can_learn_technique` checks
`check_requirements_for_path` against each path in
`technique.style.allowed_paths` when the character's current path is not in the
list. Derive-on-read (ADR-0014) — reuses the same requirement rows.

**Eligible-paths selectors:** `eligible_advanced_paths_for` and
`eligible_paths_for_threshold` filter out paths whose requirements are unmet.

### CG Conversion (`services.cg_conversion`)

```python
from world.progression.services import award_cg_conversion_xp

# Award locked (non-transferable) XP for unspent CG points
award_cg_conversion_xp(character, remaining_cg_points=10, conversion_rate=2)
# Creates CharacterXP with transferable=False and CharacterXPTransaction
```

### Kudos (`services.kudos`)

```python
from world.progression.services import award_kudos, claim_kudos, InsufficientKudosError

# Award kudos (atomic: updates balance + creates transaction)
result = award_kudos(
    account=account,
    amount=5,
    source_category=source_cat,
    description="Great roleplay during scene",
    awarded_by=gm_account,
    character=character,  # optional: associate with specific character
)
# Returns AwardResult(points_data, transaction)
#
# Post-commit side effect (#2161): every award — regardless of caller (vote
# settlement, GM award, writeup kudos, social-engagement roll, …) — schedules
# `notify_kudos_received(account, amount=..., source_category=..., description=...)`
# via `transaction.on_commit`, pushing a `kudos_received` WS frame to the recipient's
# connected sessions so the toast surfaces in real time. `KudosTransactionSerializer`
# never exposes `awarded_by` to the recipient (ADR-0033 structural guard) — the push
# payload mirrors that: no awarder identity, only amount/source_category/description.

# Claim kudos for conversion (atomic: updates balance + creates transaction)
result = claim_kudos(
    account=account,
    amount=10,
    claim_category=claim_cat,
    description="Converting to XP",
)
# Returns ClaimResult(points_data, transaction, reward_amount)
# Raises InsufficientKudosError if not enough kudos
```

### Class-Level Advancement (`services.advancement` — #1352)

```python
from world.progression.services.advancement import (
    primary_class_level,
    apply_class_level_advance,
    assert_can_officiate,
    advance_class_level_via_session,
)

# Resolve the primary CharacterClassLevel for a character (is_primary=True, or highest level).
# Returns None when the character has no CharacterClassLevel rows.
cl = primary_class_level(character)  # -> CharacterClassLevel | None

# Write level_after to the primary CharacterClassLevel and invalidate the sheet cache.
# Pure level-write — no receipt creation, no scene side-effects.
# Shared by cross_threshold (Audere Majora) and the Durance action.
apply_class_level_advance(sheet, level_after=target_level)

# Guard: raise OfficiantIneligibleError if the officiant may not induct this advance.
# Gates: (1) officiant.current_level > target_level; (2) same Path lineage.
assert_can_officiate(
    officiant_sheet=officiant,
    inductee_sheet=inductee,
    target_level=target_level,
)

# Advance each ACCEPTED inductee one class level via the Ritual of the Durance.
# Called by fire_session inside the session's transaction.
# Raises ClassLevelAdvancementError subclasses on failure (rolls back the transaction).
# Returns list of created ClassLevelAdvancement receipts.
receipts = advance_class_level_via_session(session=locked_ritual_session)
```

**Per-inductee order inside `advance_class_level_via_session`:**
1. Resolve primary class level → `target_level = level + 1`.
2. Refuse a tier boundary (`TierBoundaryRequiresCrossing`) if an `AudereMajoraThreshold` row exists at `level_before`.
3. Officiant guard (`assert_can_officiate`).
4. Resolve authored `ClassLevelUnlock`; check requirements (`AdvancementRequirementsNotMet` when absent or unmet).
4b. **Multi-gate rule (#2116):** require the purchased XP unlock (a `CharacterUnlock` receipt
    for this exact class/target_level, bought via `progression unlock class=<id>`) —
    `AdvancementUnlockNotPurchasedError` (names the unlock + its XP cost) when missing. This is
    an *additional*, independently-required gate stacked alongside step 4's requirements, never
    a substitute — see ADR "XP unlocks, never grants — major acquisitions stack gates."
5. Post the testament oration (+ cited deeds) as a POSE in the active scene.
6. Apply the level write and create the `ClassLevelAdvancement` receipt.
7. Record scene witnesses (`_record_witnesses`) into `receipt.witnesses` via `scene_witness_personas`,
   excluding inductee + officiant.

`convene_durance_at_site` pre-checks the same two gates (requirements + purchase) up front so a
doomed session is never drafted. `durance status` (telnet) surfaces both: the requirements-met
line and an "XP unlock: purchased / not purchased (cost N)" line.

### Site-Convened Sessions (#1700)

```python
from world.progression.services.advancement import convene_durance_at_site
from world.progression.exceptions import NoDuranceSiteError

# One-shot: draft a Durance session with the room's trainer-of-record as initiator.
# Does NOT fire — the inductee's `ritual join` auto-fires (DuranceAdapter.should_auto_fire).
# Raises NoDuranceSiteError if no active DuranceTrainingSite with eligible trainer is here.
session = convene_durance_at_site(inductee_sheet=sheet, room=room)
```

### Launch Bootstrap + Late-Selection Recovery (#2121)

`seed_canonical_rituals()` (`world/seeds/game_content/magic.py`, the `"magic"` cluster) now
also creates `RitualOfTheDuranceFactory()` — previously the Ritual of the Durance row itself
existed only in test factories, so a fresh DB's `ritual draft "Ritual of the Durance"` failed
by name even with a live officiant present.

`seed_durance_officiants()` (`world/progression/seeds.py`, the `"progression"` cluster, after
`"character_creation"` and `"magic"`) seeds one NPC officiant `CharacterSheet` per
CG-selectable PROSPECT `Path` — built via `create_character_with_sheet` (the same non-CG path
NPCAsset promotion uses), given a level comfortably above the first Durance target (2) via
`set_primary_class_level`, and a matching `CharacterPathHistory` — each bound as
trainer-of-record via a `DuranceTrainingSite` at the canonical fallback starting room (see
`docs/roadmap/character-creation.md`). Idempotent and staff-edit-preserving: the officiant's
level/path-history are written only at first creation, never re-clobbered on a later seed run.

```python
from world.progression.services.advancement import select_initial_path
from world.progression.exceptions import PathAlreadySelectedError

# Late-selection recovery for a character created via a CG-bypassing path
# (finalize_gm_character GM-quickstart, NPCAsset -> PC promotion) that never
# writes CharacterPathHistory — permanently Durance-blocked otherwise
# (current_path_for_character stays None; assert_can_officiate can never
# establish lineage). Raises PathAlreadySelectedError if a path is already
# on record — one-time only, NOT a general path-change tool (cross_into_path
# is that seam). Deliberately does NOT call grant_path_magic.
select_initial_path(character, path)
```

`SelectPathAction` (key `select_path`, `actions/definitions/progression_rewards.py`) is the
action.run() seam both telnet (`durance selectpath <path name or id>`) and the web converge
on; only the 5 PROSPECT paths are offered.

### Path Selectors (`selectors.py` — #1700)

```python
from world.progression.selectors import eligible_advanced_paths_for, resolve_advanced_path_by_name

# Active child Paths at the character's next level's stage (for the semi-crossing resolver).
# Empty when not at a stage boundary or no current path.
paths = eligible_advanced_paths_for(sheet)  # -> list[Path]

# Case-insensitive name match against eligible_advanced_paths_for(sheet); None if not found.
path = resolve_advanced_path_by_name(sheet, "Path of the Pale")  # -> Path | None
```

---

### Scene Integration (`services.scene_integration`)

```python
from world.progression.services import award_scene_development_points, calculate_automatic_scene_awards

# Calculate automatic awards based on scene content
awards = calculate_automatic_scene_awards(scene, participants)

# Award development points to scene participants
transactions = award_scene_development_points(scene, participants, awards)
```

---

## API Endpoints

### Path Options (transition-generic)

- `GET /api/progression/path-options/` — Returns `{ current_path, options }` (`PathOptionsSerializer`); character resolved via `X-Character-ID` header
  - `current_path` — the character's current `Path` from `CharacterPathHistory`, or `null`
  - `options` — active child paths at the next stage (or all top-level paths if no current path)
  - **Transition-generic:** reused beyond Audere Majora; any feature needing "what can this character pick next?" should use this endpoint
  - **Selectors:** `current_path_for_character(character)` + `next_path_options(character)` in `world.progression.selectors`

### Path Intent

- `GET /api/progression/path-intent/` — Returns `{ intent: { id, intended_path: { id, name, stage, stage_display, description }, declared_at } | null }` (character via `X-Character-ID` header)
- `PUT /api/progression/path-intent/` — Declare intent; body `{ path_id }` (character via `X-Character-ID` header); upserts one `PathIntent` row per character sheet
- `DELETE /api/progression/path-intent/` — Clear declared intent (character via `X-Character-ID` header)

**Crossing pre-selection wire:** `PendingAudereMajoraOfferSerializer.get_intended_path_id` (`src/world/magic/serializers.py:2353`) reads the character's `PathIntent` and returns `intended_path_id` only when it is among the offer's `eligible_paths` — ensuring the Audere Majora dialog pre-selects the declared path.

### Select Path (late-selection recovery, #2121)

- `GET /api/progression/select-path/` — Returns `{ current_path, options }` (`InitialPathOptionsSerializer`) — `current_path` should be `null` for a character that needs this; `options` are the 5 PROSPECT paths (character via `X-Character-ID` header)
- `POST /api/progression/select-path/` — Select a starting path; body `{ path_id }` (PROSPECT-stage only); dispatches `SelectPathAction`; 400 when the character already has a `CharacterPathHistory` row (`PathAlreadySelectedError`) — a one-time recovery, not `PathIntentViewSet`'s general declare/replace

### Unlock Shop

- `GET /api/progression/unlocks/` — List purchasable unlocks for the played character; returns a paginated wrapper (`{ count, next, previous, page_size, num_pages, current_page, results: [...] }`)
  - Items are discriminated by `unlock_type`: `class_level` (authored `ClassLevelUnlock`), `thread_xp_lock` (next `ThreadXPLockedLevel` boundary), or `skill_breakthrough` (a skill parked at an XP boundary, via `world.skills.services.skills_at_boundary`, #2115) — the `skill_id` field is populated for that variant; `requirements_met=False`/`locked_reason="Not yet authored"` when no `TraitRatingUnlock` exists yet for that boundary
  - Query parameter `unlock_type` filters the list to a single variant
  - Requires a played character (set by the Evennia session / test client)
- `POST /api/progression/unlocks/purchase/` — Purchase an unlock with XP; body `{ unlock_type, class_level_unlock_id }`, `{ unlock_type, thread_id, boundary_level }`, or `{ unlock_type: "skill_breakthrough", skill_id }`; dispatches `PurchaseUnlockAction` (`registry_key="purchase_unlock"`) and returns the action result on success

### Account Progression Dashboard
- `GET /api/progression/account/` - Current user's XP balance, kudos balance, recent transactions, and claim options

**Query Parameters:**
- `limit` (int) - Max transactions per type (default: 50, max: 200)
- `offset` (int) - Pagination offset (default: 0)

**Response shape:**
```json
{
    "xp": {"total_earned": 100, "total_spent": 20, "current_available": 80},
    "kudos": {"total_earned": 50, "total_claimed": 10, "current_available": 40},
    "xp_transactions": [...],
    "kudos_transactions": [...],
    "claim_categories": [...]
}
```

### Path Intent (`services.path_intent` — #1348)

```python
from world.progression.services.path_intent import set_path_intent, clear_path_intent

# Declare or replace the character's intended next path (re-declaring overwrites).
intent = set_path_intent(sheet, path)   # -> PathIntent

# Clear the declared intent (idempotent — no error if absent).
clear_path_intent(sheet)
```

These are the single mutation seam shared by the web `PathIntentViewSet` (`PUT` / `DELETE`) and
the telnet `CmdPathIntent` via `SetPathIntentAction` / `ClearPathIntentAction`.

---

## Actions (#1348)

Seven REGISTRY, `target_type=SELF` actions in `actions/definitions/progression_rewards.py`
close the ADR-0001 "web bypasses actions" gap — web views and telnet commands now converge
on the same `action.run()` seam:

| Action key | Class | Wraps |
|---|---|---|
| `claim_kudos` | `ClaimKudosAction` | `claim_kudos_for_xp` |
| `cast_vote` | `CastVoteAction` | `services.voting.cast_vote` |
| `remove_vote` | `RemoveVoteAction` | `services.voting.remove_vote` |
| `claim_random_scene` | `ClaimRandomSceneAction` | `services.random_scene.claim_random_scene` |
| `reroll_random_scene` | `RerollRandomSceneAction` | `services.random_scene.reroll_random_scene_target` |
| `set_path_intent` | `SetPathIntentAction` | `services.path_intent.set_path_intent` |
| `clear_path_intent` | `ClearPathIntentAction` | `services.path_intent.clear_path_intent` |

---

## Telnet Commands

Defined in `commands/progression.py` (training/unlock), `commands/progression_rewards.py`
(#1348, kudos/vote/random-scene/path-intent), and `commands/durance.py` (#1700, Durance
readiness + site-convene); all use namespaced subverb commands to avoid one-word key collisions.

### `training` — Manage weekly skill-training allocations

```
training                           — list allocations and weekly AP budget
training add skill=<id> ap=<n> [mentor=<id>]
training add spec=<id> ap=<n> [mentor=<id>]
training update id=<id> [ap=<n>] [mentor=<id>]
training remove id=<id>
```

Dispatches `ManageTrainingAction` (`registry_key="manage_training"`) through the same
`dispatch_player_action` seam the web API uses.

### `progression` — Browse/purchase XP unlocks

```
progression unlocks              — list class-level, thread XP-lock, and skill-breakthrough
                                    unlocks
progression unlock class=<id>    — purchase a class-level unlock
progression unlock thread=<id> level=<n>
                                 — purchase a thread XP-lock boundary
progression unlock skill=<id>    — purchase a skill's XP-boundary breakthrough (#2115)
```

`progression unlocks` reads the same service functions as `GET /api/progression/unlocks/`.
`progression unlock` dispatches `PurchaseUnlockAction`
(`registry_key="purchase_unlock"`). See `docs/systems/skills.md`'s "XP Boundaries" section
for the skill-breakthrough purchase's mechanics (rust payoff, ephemeral dev points,
`purchase_skill_breakthrough`).

`progression unlocks` also prepends the caller's **XP balance** (`ExperiencePointsData
.current_available`) and last-5 `XPTransaction` rows (#2122) — the only telnet display of
account XP; previously it only leaked into failed-purchase error text. Account lookup mirrors
`CmdKudos._show_balance`'s pattern exactly (`get_account_for_character`, `world.roster
.selectors`), so a stray character with no active tenure reports a zero balance rather than
erroring. Deliberately not duplicated onto `sheet` — one canonical place avoids two surfaces to
keep in sync (see `CmdProgressionUnlock._render_xp_balance` in `commands/progression.py`).

### `kudos` — Claim kudos for XP (#1348)

```
kudos                          — show kudos balance and claim categories
kudos claim <category_id> <n> — claim <n> kudos via category for XP
```

Dispatches `ClaimKudosAction` (`registry_key="claim_kudos"`); mirrors the web
`ClaimKudosView`.

### `vote` — Cast weekly votes on other players' content (#1348)

```
vote                               — list current votes and remaining budget
vote <interaction|participation|journal> <id>   — cast a vote
vote remove <interaction|participation|journal> <id>   — remove a vote
```

Dispatches `CastVoteAction` / `RemoveVoteAction` (`registry_key="cast_vote"` /
`"remove_vote"`); mirrors the web `VoteViewSet`.

### `randomscene` / `rscene` — Weekly random-scene bounties (#1348)

```
randomscene                — list weekly targets
randomscene claim <id>     — claim a target (must share a scene with them)
randomscene reroll <id>    — reroll a target slot (once per week)
```

Dispatches `ClaimRandomSceneAction` / `RerollRandomSceneAction`
(`registry_key="claim_random_scene"` / `"reroll_random_scene"`); mirrors the web
`RandomSceneViewSet`.

### `durance` — Ritual of the Durance readiness hub (#1700)

```
durance [status]                      — show level, unlock gate, eligible paths, intent, site
durance intent <path name or id>      — declare path intent (reuses SetPathIntentAction)
durance intent clear                  — clear path intent (reuses ClearPathIntentAction)
durance convene                       — open a site-convened Durance session at this room
durance selectpath <path name or id>  — one-time recovery: pick a path when you have none on
                                         record at all (SelectPathAction, #2121)
```

`durance convene` calls `convene_durance_at_site` and echoes the session pk. The inductee
then completes the rite via `ritual join <id> testament=<oration> [path=<name>]`. For a
live-officiant ceremony the trainer drafts with `ritual draft`, the inductee joins, and
the initiator fires with `ritual fire <id>`.

### `pathintent` — Declare preferred next path for Audere Majora (#1348)

```
pathintent              — show current path and available next-path options
pathintent <path_id>    — declare your intended next path
pathintent clear        — clear the declared intent
```

Dispatches `SetPathIntentAction` / `ClearPathIntentAction`
(`registry_key="set_path_intent"` / `"clear_path_intent"`); mirrors the web
`PathIntentViewSet` (`PUT` / `DELETE`).

---

## Integration Points

- **Mechanics**: Development rate modifiers from distinctions (e.g., Spoiled reduces physical skill development by 20%) are applied via `get_modifier_total(sheet, modifier_target)` with string-based ModifierTarget lookup (pending target FK).
- **Traits**: `DevelopmentPoints.award_points()` auto-applies to `CharacterTraitValue`.
- **Classes**: `ClassLevelUnlock`, `ClassXPCost`, and requirements reference `CharacterClass` and class levels.
- **Scenes**: Scene completion triggers `award_scene_development_points()` for trait-specific development.
- **Character Creation**: CG-to-XP conversion via `award_cg_conversion_xp()` creates locked (non-transferable) `CharacterXP`.
- **Magic — Ritual of the Durance (#1352):** `advance_class_level_via_session` is
  dispatched by `fire_session` for the "Ritual of the Durance" `Ritual` row (seeded via
  `RitualOfTheDuranceFactory`). The `ClassLevelAdvancement` receipt links back to the
  `Ritual`, the scene, and the officiant. `AudereMajoraCrossing` (magic app) and
  `ClassLevelAdvancement` both inherit `AbstractClassLevelAdvancement` and share the
  `apply_class_level_advance` spine.
- **Magic (Spec A)**: XP sinks for thread progression live in `world.magic.services`:
  - `accept_thread_weaving_unlock(character, unlock)` / `compute_thread_weaving_xp_cost(character, unlock)` — Path-multiplied XP spend that opens a new thread anchor kind via `ThreadWeavingUnlock` → `CharacterThreadWeavingUnlock`
  - `cross_thread_xp_lock(character, thread, target_level)` — XP charged when a thread crosses a `ThreadXPLockedLevel` boundary. This is reachable on the web via the legacy `POST /api/magic/threads/{id}/cross-xp-lock/` action and on both web and telnet through the shared `PurchaseUnlockAction` seam in the Unlock Shop (`/api/progression/unlocks/purchase/` and `progression unlock thread=<id> level=<n>`).
  See `docs/systems/magic.md` for the full thread model lineup.

---

## Admin

All models are registered with appropriate filters, search, and inline editing:

- **Rewards**: `ExperiencePointsDataAdmin`, `XPTransactionAdmin`, `DevelopmentPointsAdmin`, `DevelopmentTransactionAdmin`
- **Kudos**: `KudosSourceCategoryAdmin`, `KudosClaimCategoryAdmin`, `KudosPointsDataAdmin` (with transaction link), `KudosTransactionAdmin`
- **Unlocks**: `XPCostChartAdmin` (with `XPCostEntryInline`), `ClassXPCostAdmin`, `TraitXPCostAdmin`, `ClassLevelUnlockAdmin`, `TraitRatingUnlockAdmin`, `CharacterUnlockAdmin`
- **Requirements**: Individual admin classes for each requirement type, `MultiClassRequirementAdmin` (with `MultiClassLevelInline`)
- **Paths**: `CharacterPathHistoryAdmin` with `list_select_related` for performance
