# Distinctions System

Character advantages and disadvantages that mechanically modify stats, rolls, and abilities.
Part of CG Stage 6 (Traits).

**Source:** `src/world/distinctions/`
**API Base:** `/api/distinctions/`
**Implementation Plan:** `docs/plans/2026-01-21-distinctions-system-implementation.md`

---

## Enums (types.py)

```python
from world.distinctions.types import (
    DistinctionOrigin,     # CHARACTER_CREATION, GAMEPLAY (vestigial), GM_AWARD,
                            # ACHIEVEMENT_AUTO_GRANT, CONSEQUENCE_POOL, ENDORSEMENT_THRESHOLD
    OtherStatus,           # PENDING_REVIEW, APPROVED, MAPPED
)

# Typed data structures
from world.distinctions.types import (
    ValidatedDistinction,    # Dataclass for validated add operations
    DraftDistinctionEntry,   # TypedDict for draft_data storage
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `DistinctionCategory` | Categories like Physical, Mental, Social | `name`, `slug`, `description`, `display_order` |
| `DistinctionTag` | Searchable tags | `name`, `slug` |
| `Distinction` | The advantage/disadvantage definition | `name`, `category`, `cost_per_rank`, `max_rank`, `is_variant_parent`, `allow_other`, `secret_by_default`, `default_secret_level` |
| `DistinctionEffect` | Mechanical effects | `distinction`, `target` (FK `mechanics.ModifierTarget`), `value_per_rank`, `scaling_values`, `amplifies_sources_by`, `grants_immunity_to_negative`, `description` |
| `DistinctionPrerequisite` | Requirements (JSON rules) | `distinction`, `rule_json`, `description` |

**Mutual exclusion is not a separate model.** `Distinction.mutually_exclusive_with` is a
symmetrical self-referential `ManyToManyField` — adding `a.mutually_exclusive_with.add(b)`
automatically makes the pair conflict in both directions. There is no
`DistinctionMutualExclusion` model/table.

**There is no `effect_type` enum/column.** `DistinctionEffect` targets a single
`mechanics.ModifierTarget` row, and the effect's *kind* is derived on read from
`target.category.name` — not stored as a separate discriminator. The consumer loop
(`create_distinction_modifiers` / `update_distinction_rank`, `world/mechanics/services.py`)
branches on `target.category.name`:
- `category.name == "resonance"` (`RESONANCE_CATEGORY_NAME`) — skipped by the ordinary
  `ModifierSource`/`CharacterModifier` loop entirely; see "Distinction → Resonance (#1834)"
  below for how this axis is actually granted.
- `category.name == "power"` (`POWER_CATEGORY_NAME`), optionally gated by
  `target.target_resonance` — still writes a normal `CharacterModifier` row (this is the
  **potency** axis; see below).
- Everything else (stat, affinity, goal, …) — writes a normal `CharacterModifier` row as
  always, via `ModifierSource(distinction_effect=effect, character_distinction=...)`.

### Character Data (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterDistinction` | Character's acquired distinctions | `character` (FK → `character_sheets.CharacterSheet`), `distinction`, `rank`, `origin`, `is_temporary`, `notes`, `secret` (→ `secrets.Secret`) |
| `CharacterDistinctionOther` | Freeform "Other" entries | `character` (FK → `character_sheets.CharacterSheet`), `parent_distinction`, `freeform_text`, `status`, `staff_mapped_distinction` |

Both `character` FKs point at **`CharacterSheet`**, not `ObjectDB` (#2608 — the first
re-point in the ObjectDB FK audit). `CharacterSheet.pk ==
ObjectDB.pk` (primary-key O2O), so the change was a pure `AlterField`. Read
`character_distinction.character` and get the sheet directly — no `.sheet_data` hop.

---

## Post-CG acquisition — the `grant_distinction` seam (#2037)

Character creation grants distinctions through `CharacterDraft.draft_data` and
`_create_distinction_modifiers_bulk` (`world.character_creation.services`) — the CG-only path.
Every **in-play** (post-CG) acquisition or rank-up, from any source, goes through exactly one
function: `world.distinctions.services.grant_distinction(character, distinction, *, origin,
rank=None, source_description="")`. It is the single writer of `CharacterDistinction` outside
CG finalization and Django admin — no in-play caller re-implements the create/rank-up branching.

**Semantics:**

- `rank=None` **advances one step**: 1 for a brand-new grant; `current.rank + 1` (clamped to
  `distinction.max_rank`, a no-op returning the row unchanged if already at max) for an existing
  holder.
- An explicit `rank` **sets/raises only — never lowers**: a no-op if `rank <= current.rank`.
  Monotonic, matching the "rank-down never claws back" ethos `reconcile_distinction_resonance_grants`
  already established.
- **`origin` is first-acquisition provenance, not latest-touch** — it is stamped once, at
  creation, and is **never rewritten by a rank-up**. A GM re-award/rank-up of a distinction
  originally earned via `ENDORSEMENT_THRESHOLD` keeps that origin; the `origin` kwarg on a
  rank-up call is accepted but has no effect on an existing row. Deliberate (#2037 review
  fold-in) — a future toucher must not "fix" this into latest-touch without realizing it's
  ratified.
- Internally: mutual/variant exclusion check → branch on existing `CharacterDistinction` → create
  (`world.mechanics.services.create_distinction_modifiers`) or bump-and-recalculate
  (`update_distinction_rank`) → narrate via `send_narrative_message` (ABILITY category) → return
  the row. The modifier/resonance-seed cascade (see "Distinctions grant/shape Resonance" below)
  fires automatically either way, since both branches reuse the same CG-time modifier services.
- **XP path via SheetUpdateRequest (#2628).** Player-initiated requests to add or
  remove distinctions go through a `SheetUpdateRequest` model — the player
  submits with justification, the GM at their table approves or denies, and XP
  is auto-debited on approval. The sign-based cost model: adding a beneficial
  distinction (positive `cost_per_rank`) costs XP; adding a detrimental one
  (negative `cost_per_rank`) is free; removing is the inverse. The GM-direct
  path (`gm_award_distinction`) creates an auto-approved request — same XP model,
  no free bypass, ensuring consistency. Automated sources (achievement,
  consequence pool, endorsement threshold) continue to call `grant_distinction`
  directly with no XP charge — those are system-driven rewards, not purchases.
  CG-time distinctions remain point-costed (`Distinction.calculate_total_cost`); that
  budget economy does not extend past character creation.

### Exclusion checks

`_check_exclusions` (private to `services.py`) is a service-layer port of
`DraftDistinctionViewSet._check_mutual_exclusions`/`_check_variant_exclusions` — the same
`mutually_exclusive_with` (symmetrical M2M) and variant-sibling rules the CG draft view enforces,
run against a character's **currently-held** distinctions instead of a draft. It raises
`DistinctionExclusionError` (`world.distinctions.exceptions`, carries a `user_message`) instead
of a DRF `ValidationError`, since `grant_distinction` has non-HTTP callers (GM action, telnet,
achievement engine, consequence-effect handler, resonance-threshold check).

**In-play exclusion behavior differs from CG:** at CG time an exclusion conflict blocks the
draft's Traits stage outright. In play, every calling source catches
`DistinctionExclusionError` at its own call site and **skips just that grant** — logging it and
continuing — rather than failing the surrounding operation (an achievement award, a
consequence-pool resolution, an endorsement's resonance grant). This mirrors
`_apply_capture`'s `AlreadyCapturedError` skip pattern in `world/checks/consequence_resolution.py`.
The one exception is the GM action/telnet path, which surfaces the conflict as a failed action
(`exc.user_message`) since a GM issuing the award is present to see and correct it.

### The five ratified sources

| `DistinctionOrigin` | Caller | Where |
|---|---|---|
| `GM_AWARD` | `GMAwardDistinctionAction` (`registry_key="gm_award_distinction"`, JUNIOR-tier `MinimumGMLevelPrerequisite`, staff bypass) — now goes through the `SheetUpdateRequest` framework (#2628): creates an auto-approved request and processes it (XP debited on the sign-based model). Supports add (default) and remove (`/remove` switch). Telnet face `CmdGrantDistinction` (`grant_distinction <character>=<distinction slug>[,rank]` / `grant_distinction/remove <character>=<slug>`) in `src/commands/grant_distinction.py` | `src/actions/definitions/distinctions.py` |
| `UNLOCK_PURCHASE` | `SubmitSheetUpdateRequestAction` (player-initiated, `registry_key="submit_sheet_update"`) → GM approves via `ReviewSheetUpdateRequestAction` (`registry_key="review_sheet_update"`, JUNIOR-tier). `SheetUpdateRequest` model tracks PENDING → APPROVED/DENIED. XP auto-debited on approval (#2628). Telnet face `CmdSheetRequest` (`sheetrequest <add|remove|cancel|approve|deny> ...`) in `src/commands/sheet_request.py` | `src/world/distinctions/services.py` (`create_sheet_update_request` / `approve_sheet_update_request`); `src/actions/definitions/distinctions.py` |
| `ACHIEVEMENT_AUTO_GRANT` | `RewardType.DISTINCTION` on `achievements.RewardDefinition` (`distinction` FK, nullable, mirrors `modifier_target`) dispatched by `apply_achievement_rewards` → `_grant_distinction` | `src/world/achievements/services.py`. `AchievementReward.reward_value` parses as an explicit rank when a valid int, else `rank=None` (advance one step — **not** a no-op, unlike `_grant_bonus`'s parse-or-skip for BONUS rewards) |
| `CONSEQUENCE_POOL` | `EffectType.GRANT_DISTINCTION` on `checks.ConsequenceEffect` (`distinction` FK, CASCADE, mirrors `property`; `distinction_rank` nullable, mirrors `property_value`, null = advance one step) dispatched by the `_grant_distinction` handler | `src/world/mechanics/effect_handlers.py`, registered in the `EffectType` → handler dispatch table |
| `ENDORSEMENT_THRESHOLD` | `check_distinction_rank_thresholds(character_sheet, resonance)`, called from `grant_resonance` only for `ACCELERATED_GAIN_SOURCES` (sustained in-character endorsement play) | `src/world/magic/services/distinction_resonance.py` — see "Reverse direction — resonance thresholds rank up a held distinction (#2037)" below for the full mechanic (ranks up held distinctions only, never mints a new grant, multi-level catch-up) |

All five sources are lazy-imported callers of the single seam — none reimplements exclusion
checking, the create/rank-up branch, or the narrative message.

---

## Distinctions grant/shape Resonance (#1834)

A distinction can affect a character's `magic.Resonance` standing along **two independent
axes**. Both are authored per-distinction; neither is automatic.

### Standing / currency axis — `DistinctionResonanceGrant`

`DistinctionResonanceGrant` (`world/magic/models/grants.py` — lives in `world.magic`, not
`world.distinctions`, per ADR-0010: the general primitive `magic.Resonance` must not import
back into a dependent app) is a sidecar join authoring two rank-scaled currency knobs for a
`(distinction, resonance)` pair:

| Field | Purpose |
|-------|---------|
| `distinction` | FK → `distinctions.Distinction` |
| `resonance` | FK → `magic.Resonance` |
| `flat_amount_per_rank` | Flat resonance seeded per rank held in the distinction |
| `earn_rate_bonus_per_rank` | Percent bonus to the character's *earn rate* for this resonance, per rank |

Two consumer services in `world/magic/services/distinction_resonance.py`:

- **`reconcile_distinction_resonance_grants(character_distinction)`** — called at grant time
  by `create_distinction_modifiers` and at rank-change time by `update_distinction_rank`
  (`world/mechanics/services.py`). For every `DistinctionResonanceGrant` authored on the
  distinction: `get_or_create`s a `CharacterResonance` row for that resonance (establishing
  the character in it even before any seed is owed), then tops off a rank-scaled flat seed
  (`flat_amount_per_rank * rank`) via `grant_resonance(..., source=GainSource.DISTINCTION,
  source_character_distinction=character_distinction)`. Ledger-idempotent: sums this
  distinction's prior `DISTINCTION`-source grants for the resonance and only grants the
  shortfall. A second reconcile at the same rank grants 0; a rank-down never claws back
  (`CharacterResonance.lifetime_earned` is monotonic).
- **`distinction_earn_rate_for(character_sheet, resonance)`** — sums
  `earn_rate_bonus_per_rank * rank` across all of a character's distinctions that grant a
  bonus for `resonance`. Read by `grant_resonance` (`world/magic/services/resonance.py`) to
  scale up `amount` **before** writing, but only when `source` is one of
  `ACCELERATED_GAIN_SOURCES` (ADR-0041 — perception/presence-driven sources a character
  actively performs to be seen). Authored/system sources — including the `DISTINCTION` seed
  itself, to avoid a circular self-accelerating grant — are in `NON_ACCELERATED_GAIN_SOURCES`
  and are never scaled. Every `GainSource` member is asserted to land in exactly one of the
  two sets (a total-classification test in `world/magic/tests/`).

`GainSource.DISTINCTION` (`world/magic/constants.py`) is the ledger discriminator for the
seed grants above; `ResonanceGrant.source_character_distinction` is its typed source FK.

Wired at both distinction-acquisition sites: gameplay grant/rank-up
(`create_distinction_modifiers` / `update_distinction_rank`) and character creation
(`_create_distinction_modifiers_bulk` in `world/character_creation/services.py`, followed by
`recompute_aura` after `CharacterAura` is created during `finalize_magic_data`).

### Reverse direction — resonance thresholds rank up a held distinction (#2037)

`DistinctionResonanceRankThreshold` (`world/magic/models/grants.py`, beside
`DistinctionResonanceGrant`, same ADR-0010 placement) authors the opposite direction:
`(distinction, resonance, rank)`-unique rows saying "reaching `lifetime_earned_threshold`
lifetime-earned in this resonance unlocks this rank of this distinction."

Consumer: `check_distinction_rank_thresholds(character_sheet, resonance)`
(`world/magic/services/distinction_resonance.py`), called from `grant_resonance` **only when
`source` is in `ACCELERATED_GAIN_SOURCES`** — the "sustained endorsements" identity-
reinforcing-play cluster. Semantics:

- **Ranks up held distinctions only** — never mints a new `CharacterDistinction`; only rows
  whose threshold matches exactly `current_rank + 1` are candidates. That keying is also the
  re-fire guard: once a threshold fires, `current_rank + 1` moves past it, so repeated
  over-threshold grants are no-ops.
- **Multi-level catch-up loops to the final state** — one grant that crosses several
  thresholds ranks all the way up in that call (deterministic final state per grant), rather
  than one rank per grant.
- Rank-ups go through `grant_distinction(..., origin=DistinctionOrigin.ENDORSEMENT_THRESHOLD)`
  (`world/distinctions/services.py`), so the modifier/resonance-seed cascade fires normally;
  a `DistinctionExclusionError` is caught, logged, and skipped.
- **Never fires for `DISTINCTION`-source grants** (that source is not in
  `ACCELERATED_GAIN_SOURCES`), preventing a feedback loop where a distinction's own resonance
  seed re-triggers its own rank-up. The whole check is one query when no thresholds match;
  a crash in it is caught in `grant_resonance` (`logger.exception`) so the resonance grant
  itself always stands — mirrors the `PROJECT_CONTRIBUTION` bonus-isolation precedent in
  `world/projects/services.py`.

### Potency axis — POWER-category `DistinctionEffect`

A distinction expresses **potency** for a resonance (as opposed to standing/currency above)
using the ordinary authoring surface — a `DistinctionEffect` whose `target` is a
POWER-category `ModifierTarget`, optionally gated by `target.target_resonance`. This writes a
normal `CharacterModifier` row (unaffected by the resonance-category skip described in
"Enums" above). Two consumers read it: a technique cast's FLAT power stage
(`_derive_power` in `world/magic/services/techniques.py`), and a standalone thread pull via
`power_flat_bonus_for_resonance` (`world/mechanics/services.py`) folded in by
`_fold_distinction_pull_bonus` (`world/magic/services/resonance.py`). See
`docs/systems/mechanics.md` and `src/world/magic/CLAUDE.md` "Distinction Potency (POWER
axis)" for the full wiring — **note the pull path only folds this one modifier; it does not
include condition-sourced POWER contributions that a cast's FLAT stage also sums.**

The dead resonance-category `CharacterModifier` write that predated this axis split (the
distinction wrote a modifier nothing read) was removed from both grant paths as part of
#1834; the `resonance` `ModifierCategory` itself stays live for non-distinction sources
(facet/mantle/motif-coherence passive bonuses via `equipment_walk_total`).

---

## Economic axis — `DistinctionPurseDrain` (#2613)

A distinction can empty its holder's purse every week. **"Somehow Always Broke"** is the
first: a large negative (`cost_per_rank=-50`) that a player takes so their perpetually-broke
concept cannot be undone by another player's generosity — a consent mechanic (like the
antagonism register #2170), not an economic balance knob.

`DistinctionPurseDrain` (`world/currency/models.py` — lives in `world.currency`, not
`world.distinctions`, per ADR-0010: the sidecar points at the primitive) is a per-distinction
config: `drain_percent` (1–100) and `floor_coppers`. Somehow Always Broke is one row at
`100% / floor 0`; siblings (a 50% Spendthrift, a 10% tithe) are data rows, no new code.

The drain runs as **two anchored weekly cron tasks** ordered by `CronPhase` (ADR-0150):
`currency.purse_drain_snapshot` (`SNAPSHOT` band) records each holder's opening purse balance
*before* income lands; `currency.purse_drains` (`DRAIN` band, after building upkeep) empties
the purse down to `opening_balance − outflows`, where outflows is any coin that left since the
snapshot. Net effect: the holder keeps exactly that week's fresh income and nothing carried
over. `PurseDrainWeek` persists the per-holder baseline between the two bands and is the audit
trail. Every drain is an audited `currency.services.transfer` sink, never a silent write.
Services: `snapshot_purse_drains` / `run_purse_drains` (`world/currency/services.py`).

Deliberately untouched: physical minted coin (`CurrencyInstrumentDetails`, an `ItemInstance`
possession), org treasuries, and coin held by anyone else — the laundering routes are the
concept being played, not defects. See the #2613 issue spec.

Seeded (idempotent `get_or_create`) by `ensure_somehow_always_broke_distinction`
(`world/seeds/character_creation.py`, in the `character_creation` cluster): the `Distinction`
(Personality category, `-50`) and its `DistinctionPurseDrain` row (`100% / floor 0`).

---

## Profile Visibility — relocated into Secrets (#1109 → #1334)

A sensitive distinction is no longer flagged public/private; it is **relocated into a Secret**
(the privacy primitive of the mystery loop — see [secrets.md](secrets.md)):

- **Kind default** — `Distinction.secret_by_default` + `default_secret_level`. Taking a
  criminal / scandalous kind auto-mints a `Secret` at finalize, so it never lands on the public
  list. (Which kinds are secret is a content/author pass.)
- **Per-grant state** — `CharacterDistinction.secret` (`OneToOneField(secrets.Secret, SET_NULL)`).
  **The FK's presence *is* the secret-state** — `CharacterDistinction.is_secret` reads it; there
  is no separate boolean. A player self-gating an otherwise-public distinction mints a
  player-flavor secret on that grant.

Minting/clearing go through `world.distinctions.services.mint_distinction_secret` /
`clear_distinction_secret` (the single authority). The profile serializer filters on
`is_secret`: a non-owner (not staff, not the playing account) receives only **non-secret**
distinctions; the owner and staff see all, and the `DistinctionEntry` payload carries `is_secret`
so the owner's gate UI can show which are relocated. A relocated distinction surfaces for a
*learner* on the **secret tab** (via the ordinary `SecretKnowledge` loop), not back on this list.
The old `DistinctionVisibility` enum / `default_visibility` / `visibility_override` /
`effective_visibility` / `is_publicly_visible` are removed.

`DistinctionEntry` also carries `is_from_glimpse` (#2427) — `True` when
`CharacterDistinction.from_glimpse` points at the character's `CharacterAura` (the
distinction was born from the guided Glimpse flow). The own-character sheet's
Glimpse editor (`GlimpseEditorDialog`, `frontend/src/magic/components/glimpse/`)
reads this flag to seed which distinction chips show as already linked, and links
new ones via `character_distinction_id` — this `DistinctionEntry.id` (the
CharacterDistinction pk), not a catalog `Distinction` id.

---

## Key Methods

### Distinction

```python
# Calculate total cost at a specific rank
distinction.calculate_total_cost(rank=2)  # Returns cost_per_rank * rank

# Get all effect descriptions
distinction.effects.all()

# Check if has variants
if distinction.is_variant_parent:
    variants = distinction.variants.filter(is_active=True)
```

### Mutual exclusion (`Distinction.mutually_exclusive_with`)

```python
# Get all distinctions that conflict with a given distinction
excluded = distinction.mutually_exclusive_with.all()
# Symmetrical M2M — a.mutually_exclusive_with.add(b) makes each exclude the other.
```

### CharacterDistinction

```python
# Calculate total cost for character's rank
char_distinction.calculate_total_cost()  # Uses self.rank

# Get all distinctions for a character
CharacterDistinction.objects.filter(character=character)

# Get by origin
CharacterDistinction.objects.filter(
    character=character,
    origin=DistinctionOrigin.CHARACTER_CREATION
)
```

---

## API Endpoints

### Categories
- `GET /api/distinctions/categories/` - List all categories

### Distinctions
- `GET /api/distinctions/distinctions/` - List active distinctions
- `GET /api/distinctions/distinctions/{id}/` - Get distinction details

**Query Parameters:**
- `category` - Filter by category slug
- `search` - Search name, description, tags, effects
- `exclude_variants` - Hide variant children (show only parents)
- `draft_id` - Add lock status based on draft's distinctions

### Draft Distinctions
- `GET /api/distinctions/drafts/{draft_id}/distinctions/` - List draft's distinctions
- `POST /api/distinctions/drafts/{draft_id}/distinctions/` - Add distinction
- `DELETE /api/distinctions/drafts/{draft_id}/distinctions/{pk}/` - Remove distinction
- `POST /api/distinctions/drafts/{draft_id}/distinctions/swap/` - Swap mutually exclusive

---

## CG Integration

During character creation, distinctions are stored in `CharacterDraft.draft_data["distinctions"]` as a list:

```python
draft.draft_data["distinctions"] = [
    {
        "distinction_id": 1,
        "distinction_name": "Strong",
        "distinction_slug": "strong",
        "category_slug": "physical",
        "rank": 2,
        "cost": 20,
        "notes": "",
    },
    # ...
]
```

### Stage Completion

The Traits stage is complete when:
1. `draft.draft_data["traits_complete"]` is `True` (set by frontend when user makes any selection)
2. CG points remaining >= 0 (not over budget)

```python
# In CharacterDraft._is_traits_complete()
return (
    self.draft_data.get("traits_complete", False)
    and self.calculate_cg_points_remaining() >= 0
)
```

---

## Frontend Hooks

```typescript
import {
    useDistinctionCategories,
    useDistinctions,
    useDraftDistinctions,
    useAddDistinction,
    useRemoveDistinction,
} from '@/hooks/useDistinctions';

// Categories for tabs
const { data: categories } = useDistinctionCategories();

// Distinctions with filtering and lock status
const { data: distinctions } = useDistinctions({
    category: selectedCategory,
    search: searchQuery,
    draftId: draft.id,
});

// Draft's current distinctions
const { data: draftDistinctions } = useDraftDistinctions(draft.id);

// Mutations
const addDistinction = useAddDistinction(draft.id);
const removeDistinction = useRemoveDistinction(draft.id);

addDistinction.mutate({ distinction_id: 1, rank: 2 });
removeDistinction.mutate(distinctionId);
```

---

## Admin

All models are registered in Django admin with appropriate filters, search, and inline editing:

- `DistinctionAdmin` - Full editing with effects and prerequisites inline
- `CharacterDistinctionAdmin` - With `list_select_related` for performance
- `CharacterDistinctionOtherAdmin` - Bulk approve action for freeform entries
