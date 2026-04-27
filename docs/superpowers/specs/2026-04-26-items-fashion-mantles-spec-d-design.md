# Items, Fashion, Mantles, and Resonance Pivot Spec D — Design

**Status:** draft
**Spec lineage:** Resonance Pivot Spec D (continues from Spec A: Threads + Currency, Spec C: Gain Surfaces)
**Date:** 2026-04-26
**Primary apps:** `world.items`, `world.magic`, `world.covenants`, `world.mechanics`

## 1. Summary

This spec is the items-system unblocker. It wires together five tightly-coupled
goals that each individually need items to land first:

1. **Spec D's `ITEM_FACET` and `MANTLE` thread anchor caps** — Spec A explicitly
   defers these to "Spec D" with a `AnchorCapNotImplemented` placeholder. This
   spec replaces ITEM (a placeholder kind) with a richer `FACET` anchor and adds
   `MANTLE` as a separate kind, with cap formulas for both.
2. **Fashion-resonance loop (the headline)** — worn items bearing facets the
   character has invested in (via Threads on those facets) generate daily
   resonance trickle. This is intended as a *strong* mechanical reward,
   reinforcing identity-coherent dress as a major progression axis. The
   `outfit_daily_trickle_per_item_resonance` knob already exists in
   `ResonanceGainConfig` (currently inert) and activates as part of this spec.
3. **Tier-0 passive facet stat bonuses** — facet-bound threads also fire passive
   stat modifiers when the character wears at least one matching item, scaled
   by item quality and attachment quality.
4. **Mantles** — Earthdawn-style ancient artifacts unlocked by per-level
   research (Codex) + mission gates, attuned to a single character via thread
   weaving, providing authored unique bonuses.
5. **Covenant role × gear archetype compatibility** — covenant role bonuses
   are always granted in full (no dampening). Per equipped slot, compatible
   gear contributes `role_bonus + gear_stat` (additive); incompatible gear
   contributes `max(role_bonus, gear_stat)` (highest of the two only). At low
   levels gear stats dominate either way; at higher levels role bonuses
   dominate, and compatible gear adds a small mundane-stat increment on top.

Threading these together, the spec also introduces `COVENANT_ROLE` as a new
Thread anchor kind (with a "must have held the role at least once" weave gate),
folds the existing narrative-only `CharacterFacet` model into Thread-on-Facet,
and establishes the on-demand modifier-walk pattern for equipment-driven stat
contributions (no denormalization).

## 2. Goals and Non-Goals

### 2.1 Goals

- Activate the `outfit_daily_trickle_per_item_resonance` resonance-gain surface
  with a strongly-rewarding regen formula tied to worn facets + Thread investment.
- Replace the unimplemented `ITEM` Thread kind with a `FACET` kind that anchors
  on `world.magic.Facet` directly (item-independent), adds a multi-cap formula
  using `lifetime_earned(resonance)` plus path stage, and wires items as the
  *amplifiers* of facet-thread bonuses rather than the anchor.
- Add `MANTLE` as a separate Thread kind with attunement gated by per-level
  Codex + mission clearance, scaled by max-cleared-level × 10 anchor cap.
- Add `COVENANT_ROLE` as a Thread kind with a "must have ever held this role"
  weave gate; cap by `character.current_level × 10`.
- Define `gear_archetype` on `ItemTemplate` and `GearArchetypeCompatibility`
  rows so the covenant role + gear pipeline can decide per-slot whether to
  add mundane gear stats to role bonuses (compatible) or take the higher of
  the two (incompatible). Role bonuses themselves are never reduced.
- Replace the narrative-only `CharacterFacet` model with Thread-on-Facet
  (single source of truth for "which facet means what to this character").
- Establish the "on-demand modifier walk" pattern: equipment-driven modifier
  contributions are computed by walking `EquippedItem` rows at query time, never
  by writing `CharacterModifier` rows. Distinctions/conditions keep their
  existing eager pattern.
- Land the design as a single spec; implementation in 4 sequenced PRs.

### 2.2 Non-Goals

- **Item ownership / transfer service functions.** `OwnershipEvent` model and
  `CurrencyBalance` already exist; service functions for `give`, `pick_up`,
  `drop`, `steal`, `transfer` are explicitly out of scope. Deferred to a
  follow-up spec.
- **Combat stat blocks** (weapon damage, armor protection numbers, durability).
  These exist in concept (referenced in covenant compatibility math) but the
  concrete `ItemCombatStat` model + integration with `world.combat` is deferred
  to PR3 of this spec's phasing.
- **Crafting recipes / skill-gated craft system.** This spec relies on crafters
  having a path to write `ItemFacet` and `ItemInstance` rows but does not design
  the recipe model. Deferred to a follow-up spec.
- **Full covenant group model.** This spec adds `CharacterCovenantRole` (per-
  character role assignment) but does not design covenant group membership,
  covenant-level progression, or the covenant-creation ritual itself. Those are
  the broader covenant system's concern.
- **Mission system.** Mantle attunement is intended to be gated by both
  research AND mission completion, but only the codex-research half ships
  in this spec. The Mission model doesn't exist yet, and Django requires FK
  targets to exist — so this spec doesn't include a `mission_required`
  field on MantleLevelDefinition at all. The future Mission spec adds the
  FK via migration and updates the clearance service to require both gates.
- **`ROOM` Thread anchor cap.** Spec A also defers this to Spec D, but rooms
  are a distinct enough surface that this spec leaves them as a placeholder.
  A future room-imbuing spec can reuse the patterns established here.
- **Frontend UI** — inventory, equipping, facet attachment, mantle attunement.
  Service-layer + API surfaces only. UI follows after pipeline tests pass per
  the broader project sequencing principle.
- **Motif / aura / stylistic-vibe magical-significance system.** Resonance
  covers thematic affinity, facets cover specific imagery — neither covers
  *style* ("seductive," "beguiling," "menacing," "regal"). The existing
  `Motif`, `MotifResonance`, and `MotifResonanceAssociation` models in
  `world.magic.models.motifs` are scaffolding without a coherent system. A
  dedicated future spec is needed to design how style as a magical-
  significance axis works (per-item style-tag model, MOTIF Thread anchor
  kind, crafter style-adaptation mini-games, style × facet composition,
  public-perception integration). **No model or pipeline changes for Motif
  land in this spec.** See §13.3 for the explicit gap and the design
  sub-questions the future spec needs to answer.

## 3. Architecture Overview

### 3.1 Parts list

```
┌─ world.items ────────────────────────────────────────────────────┐
│   ItemTemplate (existing, +facet_capacity, +gear_archetype)             │
│   ItemInstance (existing — unchanged shape, +ItemFacet relation)        │
│   EquippedItem (existing, unchanged)                                    │
│   ItemFacet (NEW — through model: ItemInstance × Facet)                 │
│   Mantle (NEW — OneToOneField to ItemInstance)                          │
│   MantleLevelDefinition (NEW)                                                  │
│   MantleLevelClearance (NEW)                                            │
└──────────────────────────────────────────────────────────────────┘

┌─ world.magic ────────────────────────────────────────────────────┐
│   Thread (existing, +FACET, +MANTLE, +COVENANT_ROLE kinds and FKs)      │
│   ThreadPullEffect (existing — accepts new target_kinds)                │
│   CharacterFacet (DROPPED — migrated to Thread)                         │
│   Facet (existing, unchanged — referenced by Thread.target_facet)       │
└──────────────────────────────────────────────────────────────────┘

┌─ world.covenants ────────────────────────────────────────────────┐
│   CovenantRole (existing, unchanged)                                    │
│   CharacterCovenantRole (NEW — assignment record with joined_at/left_at)│
│   GearArchetypeCompatibility (NEW)                                      │
└──────────────────────────────────────────────────────────────────┘

┌─ world.mechanics ────────────────────────────────────────────────┐
│   get_modifier_total / get_modifier_breakdown (existing, extended)      │
│     — adds equipment walk for on-demand contributions                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 The five pipelines

1. **Resonance regen pipeline** (daily tick) — walks worn items, matches their
   facets against the wearer's woven Threads, grants resonance scaled by item
   quality × attachment quality × thread level.
2. **Tier-0 passive bonus pipeline** — same walk, contributes stat modifiers
   via `ThreadPullEffect` rows authored at tier 0 for `target_kind=FACET`.
3. **Tier 1+ thread pull pipeline** — existing Spec A `spend_resonance_for_pull`
   with FACET-aware effect resolution that scales by worn-item-facet aggregate.
4. **Mantle attunement pipeline** — Codex research + mission gates → Thread
   weave on Mantle → tier-N pulls firing authored unique effects.
5. **Modifier-walk-on-demand pipeline** — extension to `get_modifier_total`
   that aggregates equipment-driven contributions at query time.

### 3.3 Handler pattern (no service-function queries against CharacterSheet relationships)

**Project rule:** anything FK'd to CharacterSheet goes through a cached
handler installed on the typeclass. Service functions read those handlers;
they never run `.objects.filter(character_sheet=...)` themselves. Handlers
load their data lazily (cached_property) with all needed prefetches in one
batch, expose in-memory helper methods, and are invalidated explicitly when
rows are added or removed.

This spec adds or extends these handlers:

| Handler | Location | New / extended | Purpose |
|---|---|---|---|
| `character.threads` (`CharacterThreadHandler`) | `world.magic` | extended | Add `thread_for_facet(facet)`, `threads_of_kind(kind)` (if not already present), prefetch `target_facet` + `target_mantle` + `target_covenant_role`. |
| `character.equipped_items` (`CharacterEquipmentHandler`) | `world.items` | NEW | Cached list of `EquippedItem` rows with `item_instance` + `item_instance.item_facets` + `item_instance.template` + `item_instance.quality_tier` prefetched. Helper methods: `iter_item_facets() -> Iterable[ItemFacet]` (flat walk of every facet attachment across equipped items), `item_facets_for(facet) -> list[ItemFacet]` (attachments matching a specific Facet). Each `ItemFacet` reaches its item via `item_facet.item_instance`. |
| `character.mantle_clearances` (`CharacterMantleClearanceHandler`) | `world.items` | NEW | Cached list of `MantleLevelClearance` rows. Helper: `max_cleared_level(mantle) -> int`. |
| `character.covenant_roles` (`CharacterCovenantRoleHandler`) | `world.covenants` | NEW | Cached list of `CharacterCovenantRole` rows (active + historical). Helpers: `has_ever_held(role) -> bool`, `currently_held() -> CovenantRole \| None`. |

The existing `sheet.modifiers` handler (set up by Spec A and prior) is reused
for the eager modifier total — no direct `CharacterModifier.objects.filter`
calls in any service function in this spec.

If a handler-cached collection is mutated (e.g., a new `EquippedItem` is
created via `equip_item`), the corresponding handler is invalidated by the
service function: `character.equipped_items.invalidate()`. This is the
standard Spec A pattern — see `CharacterThreadHandler.invalidate()`.

### 3.4 Decision log

| Decision | Choice | Rationale |
|---|---|---|
| Thread anchor on Facet vs ItemFacet | **Facet** (global) | Threads should be precious and identity-shaped; item-coupled threads punish gear cycling. |
| Replace `CharacterFacet` | **Yes** | Thread-on-Facet captures (character, facet, resonance) and supersedes CharacterFacet's role. |
| Drop existing `ITEM` Thread kind | **Yes** | Placeholder, never implemented, no production data. |
| Two-quality-tier facet system | **Yes** | Item quality × attachment quality enables independent crafter-skill scaling. |
| Modifier compute strategy | **On-demand walk** | No denormalization; relies on SharedMemoryModel + content cache. |
| Mantle as separate model | **Yes** | Mantles have authored stories; per-level Codex + Mission gating; not generic items. |
| `COVENANT_ROLE` weave gate | **Must have ever held the role** | Reinforces covenant ritual as the unlock moment. |
| FACET unlock granularity | **Single global unlock** | Per-facet unlocks would be too punishing given facet diversity. |
| FACET anchor cap formula | **min(lifetime_earned/N, path_stage × 20), capped by path_stage × 10** | Couples thread cap to identity-RP investment in the resonance; hard ceiling prevents runaway. |

## 4. Data Model

### 4.1 Extensions to `world.items.ItemTemplate`

```python
class ItemTemplate(SharedMemoryModel):
    # ... existing fields unchanged ...

    facet_capacity = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Number of Facet slots this template can carry. "
            "Plain items = 0 or 1; fine items = 2-3; ceremonial = 4-5."
        ),
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
        default=GearArchetype.OTHER,
        help_text=(
            "Gear category. Drives covenant role × gear compatibility. "
            "Immutable across instances of this template."
        ),
    )

    # No `mantle` FK on ItemTemplate. Mantles are specific items in the
    # world, not categories — the OneToOne lives on Mantle → ItemInstance
    # (see §4.3). "Is this *instance* a mantle?" is answered by the reverse
    # relation `instance.mantle`. Templates themselves can be shared across
    # multiple mantles (two mantle swords, one "Sword" template, two
    # different ItemInstance rows).

    # No new constraints needed — `PositiveSmallIntegerField` already
    # enforces non-negativity at the DB level.
```

`gear_archetype` enum lives in `world/items/constants.py`:

```python
class GearArchetype(models.TextChoices):
    """Gear categorization for covenant role compatibility.

    Final list TBD via playtest; this is the starting set.
    """
    LIGHT_ARMOR = "light_armor", "Light Armor"
    MEDIUM_ARMOR = "medium_armor", "Medium Armor"
    HEAVY_ARMOR = "heavy_armor", "Heavy Armor"
    ROBE = "robe", "Robe"
    MELEE_ONE_HAND = "melee_one_hand", "One-Handed Melee"
    MELEE_TWO_HAND = "melee_two_hand", "Two-Handed Melee"
    RANGED = "ranged", "Ranged"
    THROWN = "thrown", "Thrown"
    SHIELD = "shield", "Shield"
    JEWELRY = "jewelry", "Jewelry"
    CLOTHING = "clothing", "Clothing"  # non-armor body wear (gowns, robes)
    OTHER = "other", "Other"
```

### 4.2 New model: `world.items.ItemFacet`

Through-model linking `ItemInstance` to `Facet` with attachment quality and
crafter provenance.

```python
class ItemFacet(SharedMemoryModel):
    """A single facet attached to an item instance.

    Items carry facets either at craft time (baked in by the item's crafter)
    or via post-craft decoration (a different crafter adding their work).
    Each facet on an item is a separate row with its own attachment quality,
    independent of the item instance's overall quality tier.

    Facets do NOT carry threads directly; threads live on Facet (the global
    lookup model in world.magic). When computing a wearer's bonuses, the
    pipeline walks worn items -> ItemFacet rows -> matches against the
    wearer's Threads on those Facets.
    """

    item_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="item_facets",
        help_text="The item carrying this facet.",
    )
    facet = models.ForeignKey(
        "magic.Facet",
        on_delete=models.PROTECT,
        related_name="item_attachments",
        help_text="Which facet (in the global Facet hierarchy).",
    )
    applied_by_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facet_applications",
        help_text="The crafter / decorator who applied this facet.",
    )
    attachment_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.PROTECT,
        related_name="facet_attachments",
        help_text=(
            "Quality of the attachment itself. Independent of "
            "item_instance.quality_tier. The crafter's skill at the time "
            "of attachment determines this."
        ),
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "facet"],
                name="items_unique_itemfacet_per_instance",
            ),
        ]
```

**Capacity validation.** A `clean()` check on `ItemFacet` enforces
`ItemInstance.item_facets.count() < ItemInstance.template.facet_capacity` at
write time. Service functions also enforce this; `clean()` is the safety net.

### 4.3 New models: `world.items.Mantle`, `MantleLevelDefinition`, `MantleLevelClearance`

```python
class Mantle(SharedMemoryModel):
    """An attunable artifact with a story.

    Each Mantle is one specific ItemInstance in the world (a particular
    sword, amulet, banner, etc.) — not a category. The OneToOne FK to
    ItemInstance makes that explicit: at most one Mantle per item, at most
    one item per Mantle. Multiple mantles can share an ItemTemplate (two
    mantles that are both swords are two different ItemInstances of the
    "Sword" template), with no conflict.

    PROTECT on the FK prevents accidental deletion of an ItemInstance that
    has mantle metadata; staff would need to explicitly retire the Mantle
    first.

    Each Mantle has 1..N authored levels (MantleLevelDefinition rows). Characters
    progress by clearing each level's research (CodexEntry) + mission gates
    in order, recording MantleLevelClearance rows. Attunement to a mantle is
    represented as a Thread of kind=MANTLE anchored on the Mantle; the
    thread's level cannot exceed the character's max-cleared mantle level.
    Each character must clear gates and weave their own thread separately.
    """
    item_instance = models.OneToOneField(
        "items.ItemInstance",
        on_delete=models.PROTECT,
        related_name="mantle",
        help_text="The unique ItemInstance that is this Mantle.",
    )
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(
        help_text="The flavor lore visible to authors and (selectively) players.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If false, attunement weaving is blocked.",
    )
    max_level = models.PositiveSmallIntegerField(
        default=5,
        help_text="How many attunement levels exist for this mantle.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_level__gte=1) & models.Q(max_level__lte=10),
                name="items_mantle_max_level_range",
            ),
        ]


class MantleLevelDefinition(SharedMemoryModel):
    """Authored content for a single mantle level.

    Each level requires both a Codex entry to be researched and a mission
    to be completed before the level's clearance can be recorded.
    """
    mantle = models.ForeignKey(
        Mantle,
        on_delete=models.CASCADE,
        related_name="level_defs",
    )
    level = models.PositiveSmallIntegerField()
    codex_entry_required = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        related_name="mantle_level_gates",
        help_text="Lore the character must research before this level can clear.",
    )

    # No `mission_required` FK in this spec. Mission system is a future
    # spec; once it ships, that spec adds a `mission_required` FK to
    # MantleLevelDefinition via migration and updates the clearance logic
    # to require both gates. PR2 of this spec gates mantle clearances by
    # Codex research alone.
    unlock_description = models.TextField(
        help_text="Player-facing description of what this level grants.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mantle", "level"],
                name="items_unique_mantle_level",
            ),
        ]


class MantleLevelClearance(SharedMemoryModel):
    """Per-character record that a mantle's level N gates have been cleared.

    Created when both research and mission gates are met. Existence of a
    clearance row at level N raises the character's effective MANTLE thread
    cap on that mantle to N × 10 (subject to path cap min).
    """
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="mantle_clearances",
    )
    mantle = models.ForeignKey(
        Mantle,
        on_delete=models.CASCADE,
        related_name="clearances",
    )
    level = models.PositiveSmallIntegerField()
    cleared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "mantle", "level"],
                name="items_unique_mantle_clearance_per_character",
            ),
        ]
```

### 4.4 New models: `world.covenants.CharacterCovenantRole`, `GearArchetypeCompatibility`

```python
class CharacterCovenantRole(SharedMemoryModel):
    """Per-character record of a covenant role assignment.

    Records that a character holds (or formerly held) a CovenantRole.
    left_at IS NULL marks the assignment as currently active. The pipeline
    gate for COVENANT_ROLE thread weaving checks "has any row ever existed
    for this (character, covenant_role)" — i.e., the character must have
    taken the role at least once via the covenant ritual.

    No `covenant_instance` FK in this spec. The CovenantInstance model
    doesn't exist yet — it will land with the future covenant group system,
    along with a follow-up migration that adds the FK here and relaxes the
    unique constraint to include it. Until then, every active row is an
    unambiguous "this character holds this role" — multi-covenant
    participation isn't possible yet because covenants themselves aren't
    fully modeled.
    """
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="covenant_role_assignments",
    )
    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.PROTECT,
        related_name="character_assignments",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "covenant_role"],
                condition=models.Q(left_at__isnull=True),
                name="covenants_one_active_role_assignment",
            ),
        ]
```

```python
class GearArchetypeCompatibility(SharedMemoryModel):
    """Authored lookup: which CovenantRoles are compatible with which gear archetypes.

    Existence-only join. Row present for `(role, archetype)` = role bonuses
    add to mundane gear stats on that archetype (compatible). Row absent =
    incompatible (per-slot contribution becomes `max(role_bonus, gear_stat)`
    rather than additive). No `is_compatible` column — the row IS the
    statement that this role can use this gear.

    Default: every (role, archetype) pair is incompatible until staff
    authors a row. No implicit-permissive fallback.
    """
    covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.CASCADE,
        related_name="gear_compatibilities",
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "gear_archetype"],
                name="covenants_unique_role_archetype_compat",
            ),
        ]
```

### 4.5 Thread discriminator extension (`world.magic.Thread`)

Extends Spec A's existing `Thread` model. New `target_kind` values and typed
FKs:

```python
class TargetKind(models.TextChoices):
    # ... existing values: TRAIT, TECHNIQUE, RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE, ROOM ...
    FACET = "facet", "Facet"               # NEW
    MANTLE = "mantle", "Mantle"            # NEW
    COVENANT_ROLE = "covenant_role", "Covenant Role"  # NEW
    # ITEM = "item", "Item"  -- DROPPED (was placeholder, no data)
```

New typed FKs added to `Thread`:

```python
class Thread(SharedMemoryModel):
    # ... existing fields ...
    target_facet = models.ForeignKey(
        "magic.Facet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="threads",
    )
    target_mantle = models.ForeignKey(
        "items.Mantle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="threads",
    )
    target_covenant_role = models.ForeignKey(
        "covenants.CovenantRole",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="threads",
    )

    class Meta:
        constraints = [
            # ... existing per-kind unique + check constraints ...

            models.UniqueConstraint(
                fields=["owner", "target_facet"],
                condition=models.Q(target_kind="facet", retired_at__isnull=True),
                name="magic_thread_unique_facet_per_owner",
            ),
            models.UniqueConstraint(
                fields=["owner", "target_mantle"],
                condition=models.Q(target_kind="mantle", retired_at__isnull=True),
                name="magic_thread_unique_mantle_per_owner",
            ),
            models.UniqueConstraint(
                fields=["owner", "target_covenant_role"],
                condition=models.Q(target_kind="covenant_role", retired_at__isnull=True),
                name="magic_thread_unique_covenant_role_per_owner",
            ),

            # Per-kind exact-one-FK check constraints follow Spec A pattern.
            # FACET: target_facet set, others null
            models.CheckConstraint(
                check=(
                    ~models.Q(target_kind="facet")
                    | (
                        models.Q(target_facet__isnull=False)
                        & models.Q(target_trait__isnull=True)
                        & models.Q(target_technique__isnull=True)
                        & models.Q(target_object__isnull=True)
                        & models.Q(target_relationship_track__isnull=True)
                        & models.Q(target_capstone__isnull=True)
                        & models.Q(target_mantle__isnull=True)
                        & models.Q(target_covenant_role__isnull=True)
                    )
                ),
                name="magic_thread_facet_exclusive_fk",
            ),
            # MANTLE and COVENANT_ROLE follow the same pattern.
        ]
```

`clean()` mirrors the constraint set as application-layer validation per Spec
A's triple-layer integrity convention.

### 4.6 Models being dropped

#### `world.magic.CharacterFacet`

Replaced by Thread-on-Facet. The existing model captures (character, facet,
resonance, narrative). All four are present on `Thread` after this spec
(`Thread.owner`, `Thread.target_facet`, `Thread.resonance`, `Thread.narrative`).

**Migration plan:**

The project is pre-alpha — no players, no production data, no data
migrations needed.

1. Add the new Thread fields and discriminator values (additive schema migration).
2. Drop the `CharacterFacet` model + table (schema migration).
3. Refactor test factories that create `CharacterFacet` rows to weave
   Threads instead. CG verification confirmed `world.character_creation`
   does not create `CharacterFacet` rows at finalization in any code path —
   only test factories do, and those get refactored as part of the same PR.

## 5. Pipelines

### 5.1 Resonance regen pipeline (the headline)

**Trigger:** the existing `resonance_daily_tick` scheduler in `world.magic`,
already running daily.

**Activation:** the existing `ResonanceGainConfig.outfit_daily_trickle_per_item_resonance`
field (currently inert) becomes load-bearing.

**Algorithm:**

```python
def outfit_daily_trickle_for_character(sheet: CharacterSheet) -> None:
    """Daily resonance trickle from worn facet-bearing items.

    For each equipped item:
      For each ItemFacet on the item:
        If the wearer has a Thread on that Facet:
          grant_resonance(
            sheet,
            thread.resonance,
            amount=trickle_for(item, item_facet, thread),
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
          )

    No thread on the facet -> no trickle.
    No matching item worn -> no trickle for that thread.
    """
    config = get_resonance_gain_config()
    base = config.outfit_daily_trickle_per_item_resonance

    # All collection access below is cached-handler reads, no queries.
    for item_facet in sheet.character.equipped_items.iter_item_facets():
        item = item_facet.item_instance
        item_q_mult = item.quality_tier.stat_multiplier if item.quality_tier else Decimal(1)
        attach_q_mult = item_facet.attachment_quality_tier.stat_multiplier

        thread = sheet.character.threads.thread_for_facet(item_facet.facet)
        if thread is None:
            continue

        level_factor = max(1, thread.level)  # level 0 = ×1, level 5 = ×5
        amount = int(base * item_q_mult * attach_q_mult * level_factor)
        if amount <= 0:
            continue

        grant_resonance(
            sheet,
            thread.resonance,
            amount=amount,
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
        )
```

**`GainSource.OUTFIT_TRICKLE`** is a new value on the existing `GainSource`
enum (the discriminator on `ResonanceGrant`). The audit ledger gains a new
typed FK column `outfit_item_facet → ItemFacet` (Spec C's typed-FK pattern
applies; new sources add their own columns).

**Tuning knobs:**
- `outfit_daily_trickle_per_item_resonance` (existing, currently default 1)
- `level_factor` formula — `max(1, thread.level)` is the simple choice. Could
  cap at `min(thread.level, max_level_factor)` to prevent runaway. Default:
  uncapped linear (lifetime ratchet on lifetime_earned acts as the indirect cap).

**Why this is the headline:** a character who wears 5 items each bearing
their primary-resonance facet, all at quality tier 3 with attachment quality
tier 3, and a level-5 thread on that facet, gets:
`5 × 1 × 3.0 × 3.0 × 5 = 225` resonance trickle per day vs Spec C's residence
trickle of 1-3/day. Two orders of magnitude difference. **This is the design
intent** — fashion-coherent dressing should be the dominant non-RP regen path.

### 5.2 Tier-0 passive facet bonuses

Spec A's existing `ThreadPullEffect` model accepts tier-0 rows that fire
passively (without resonance spend). For `target_kind=FACET`, tier-0 effects
are gated on the wearer having at least one matching item worn:

```python
def passive_facet_bonuses(sheet: CharacterSheet, target: ModifierTarget) -> int:
    """Sum tier-0 FACET ThreadPullEffect contributions for this target.

    Walks character's facet threads -> for each, finds matching equipped
    items via handler -> sums effect contribution per (item, facet) match.

    All character-side collection access is via cached handlers. The
    ThreadPullEffect query is read-once-per-call against authored content
    (a SharedMemoryModel lookup table — identity-mapped after first read).
    """
    total = 0
    for thread in sheet.character.threads.threads_of_kind(TargetKind.FACET):
        matching = sheet.character.equipped_items.item_facets_for(thread.target_facet)
        if not matching:
            continue  # no matching worn item -> tier-0 doesn't fire

        effects = _facet_pull_effects_for(thread.resonance, target, tier=0)
        for effect in effects:
            for item_facet in matching:
                contribution = _facet_effect_contribution(
                    effect=effect,
                    thread=thread,
                    item=item_facet.item_instance,
                    item_facet=item_facet,
                )
                total += contribution
    return total


def _facet_effect_contribution(
    *,
    effect: ThreadPullEffect,
    thread: Thread,
    item: ItemInstance,
    item_facet: ItemFacet,
) -> int:
    """Compute one (item, facet) contribution to a tier-0 effect."""
    base = effect.flat_bonus_amount or 0
    item_mult = item.quality_tier.stat_multiplier if item.quality_tier else Decimal(1)
    attach_mult = item_facet.attachment_quality_tier.stat_multiplier
    level_mult = max(1, thread.level)
    return int(base * item_mult * attach_mult * level_mult)
```

`_facet_pull_effects_for(resonance, target, tier)` reads `ThreadPullEffect`
rows. ThreadPullEffect is authored content (lookup table, SharedMemoryModel),
not character-related — so a query against it is correct and identity-mapped
after first load. The "no queries against CharacterSheet relationships" rule
applies to per-character data, not authored catalogs.

This composes with the existing `passive_vital_bonuses` pattern — same shape,
keyed by ModifierTarget instead of vital_target.

### 5.3 Tier 1+ thread pulls (FACET-aware)

Existing `spend_resonance_for_pull` and `resolve_pull_effects` work as-is. The
extension: when resolving pull effects for a `target_kind=FACET` thread,
multiply `scaled_value` by the worn-item-facet aggregate:

```python
# Inside resolve_pull_effects, for FACET-anchored threads:
matching = sheet.character.equipped_items.item_facets_for(thread.target_facet)
if not matching:
    continue  # no matching worn item -> pull effects don't fire (mirrors tier-0 gate)

worn_aggregate = sum(
    item_facet.item_instance.quality_tier.stat_multiplier
    * item_facet.attachment_quality_tier.stat_multiplier
    for item_facet in matching
)
scaled_value = effect.authored_value * thread.level_multiplier * worn_aggregate
```

Pulls without matching worn items are blocked **server-side before resonance
deduction**, not silently absorbed. `spend_resonance_for_pull` performs the
worn-items check up front for `target_kind=FACET` threads:

```python
# Inside spend_resonance_for_pull, before resonance deduction:
if thread.target_kind == TargetKind.FACET:
    if not sheet.character.equipped_items.item_facets_for(thread.target_facet):
        raise NoMatchingWornFacetItemsError(thread.target_facet.name)
```

`NoMatchingWornFacetItemsError` follows the typed-exception pattern with
`user_message` and SAFE_MESSAGES allowlist. The action UI prevents submission
as a UX nicety (greyed-out pull button when no matching items worn); the
server gate is authoritative. No resonance is consumed when the gate trips.

### 5.4 Mantle attunement pipeline

```
Player learns Codex entry for Mantle X level N
  -> world.codex.services records the learning
  -> Mantle service: check_and_record_clearance(sheet, mantle, level=N)
     -> If codex_entry_required cleared:
        -> create MantleLevelClearance(sheet, mantle, level=N)

Player weaves Thread on Mantle X
  -> weave_thread(sheet, target_kind=MANTLE, target_mantle=mantle, resonance=...)
  -> Validates: at least level-1 clearance exists
  -> Creates Thread(level=0, owner=sheet, target_mantle=mantle)

Player imbues Mantle thread up to level N
  -> spend_resonance_for_imbuing(...)
  -> Cap: min(path_stage * 10, max_cleared_level * 10)
  -> Cannot level past max-cleared mantle level

Player pulls Mantle thread during action
  -> ThreadPullEffect rows authored per (target_kind=MANTLE, mantle FK, tier)
  -> Effects fire as authored unique bonuses (no aggregation across items)
```

**Soulbound:** Thread is per-character. Another character must clear all
gates and weave their own thread. The Mantle's ItemInstance (a specific
sword, amulet, banner) can be physically held by anyone, but only the
attuned character benefits from the thread's effects.

**Mission gate (future):** Mantle attunement is intended to be gated by both
research AND mission completion. This spec ships the codex-research half;
when the Mission system spec lands, it adds a `mission_required` FK to
MantleLevelDefinition via migration, updates the clearance service to
require both gates, and authors the actual mission rows. PR2 of this spec
gates by Codex research alone.

### 5.5 Modifier walk on demand

Equipment-driven modifier contributions are computed at query time, not
written as `CharacterModifier` rows.

```python
def get_modifier_total(sheet: CharacterSheet, target: ModifierTarget) -> int:
    """Sum all modifier contributions for this character + target.

    Eager path: read from sheet.modifiers handler (no query).
    Equipment path: read from cached handlers (no query) when category is
    equipment-relevant.
    """
    eager_total = sheet.modifiers.total_for_target(target)

    equipment_total = 0
    if target.category in EQUIPMENT_RELEVANT_CATEGORIES:
        equipment_total = passive_facet_bonuses(sheet, target)
        equipment_total += covenant_role_bonus(sheet, target)
        # Future: ItemCapabilityGrant contributions (PR3)

    return eager_total + equipment_total
```

`EQUIPMENT_RELEVANT_CATEGORIES` is a constant set of `ModifierCategory`
values indicating which categories can receive equipment contributions.
Most distinction- or condition-driven categories don't trigger the
equipment walk.

**No queries during a modifier total call.** All character-relationship
reads go through cached handlers (§3.3): `sheet.modifiers`,
`sheet.character.equipped_items`, `sheet.character.threads`. Authored
catalogs (`ThreadPullEffect`, `GearArchetypeCompatibility`) are
SharedMemoryModel and identity-mapped after first read. Per-call cost in
the steady state is Python iteration over already-loaded objects.

**Cache invalidation.** Service functions that mutate equipment, threads,
or modifiers explicitly invalidate the relevant handler:

```python
def equip_item(...) -> EquippedItem:
    equipped = EquippedItem.objects.create(...)
    character.equipped_items.invalidate()
    return equipped
```

This is the standard Spec A pattern (`CharacterThreadHandler.invalidate()`).
Mutations are explicit and rare; reads are frequent and never query.

### 5.6 Covenant role × gear archetype compatibility

Covenant role bonuses are **always granted in full**, regardless of the gear
the character is wearing. The role-vs-gear interaction is per-slot, and it
governs whether the slot's mundane gear stats *stack on top of* the role
bonus or *only count if higher*.

Per equipped item, the contribution to a `ModifierTarget` is:

- **Compatible gear:** `role_bonus + gear_stat` (additive)
- **Incompatible gear:** `max(role_bonus, gear_stat)` (highest of the two only)

At low character levels `gear_stat > role_bonus`, so the slot's contribution
is dominated by the gear regardless of compatibility — wearing "wrong" gear
costs nothing. At higher levels `role_bonus > gear_stat`, so compatible gear
adds a small mundane-stat increment on top of the role bonus while
incompatible gear contributes only the role bonus (the gear's mundane stat
is wasted). Either way, the character never loses their role bonus; they
just don't get to stack mundane gear stats on top when wearing incompatible
archetypes.

```python
def covenant_role_bonus(sheet: CharacterSheet, target: ModifierTarget) -> int:
    """Per-equipped-item covenant role + gear contribution to this target.

    Walks equipped items via cached handler and sums per-slot contributions
    per the compatible/incompatible rule above.
    """
    role = sheet.character.covenant_roles.currently_held()
    if role is None:
        return 0

    char_level = sheet.current_level
    role_bonus = role_base_bonus_for_target(role, target, char_level)

    total = 0
    for equipped in sheet.character.equipped_items:
        item = equipped.item_instance
        gear_stat = item_mundane_stat_for_target(item, target)
        archetype = item.template.gear_archetype
        if is_gear_compatible(role, archetype):
            total += role_bonus + gear_stat  # additive
        else:
            total += max(role_bonus, gear_stat)  # take the higher

    return total
```

The math is explicit per equipped item because each slot independently
chooses additive vs max — a character wearing 3 compatible items + 2
incompatible items gets `3 × (role + gear) + 2 × max(role, gear)`.

`role_base_bonus_for_target(role, target, character_level)` reads role-
specific scaling from authored data (TBD location — likely a new
`CovenantRoleBonus` model keyed by role + ModifierTarget + per-level
coefficient). PR1 ships a placeholder that returns 0 for all targets; PR3
wires actual values once combat balance is addressed.

`item_mundane_stat_for_target(item, target)` reads mundane gear stats
(weapon damage, armor protection, etc.) from the item's combat stat block —
not yet authored. PR3 adds the `ItemCombatStat` model and the lookup
function; until then this returns 0. Quality tier scales mundane stat
magnitude (higher quality = larger flat contribution).

**Why this composes cleanly even when both lookups return 0 in PR1:** with
both returning 0, `max(0, 0) == 0 + 0`, so the structural pipeline is
identical to a fully-authored future state. PR1 tests inject non-zero
values to validate the additive vs max branching without depending on PR3's
authoring choices.

## 6. Anchor Cap Formulas

All caps use Spec A's `compute_anchor_cap(thread)` and
`compute_effective_cap(thread) = min(compute_path_cap(owner), compute_anchor_cap(thread))`
pattern.

### 6.1 FACET

```python
def compute_anchor_cap(thread: Thread) -> int:
    match thread.target_kind:
        # ... existing kinds ...
        case TargetKind.FACET:
            lifetime = thread.owner.character.resonances.lifetime(thread.resonance)
            divisor = ANCHOR_CAP_FACET_DIVISOR  # default 50
            hard_max = thread.owner.path_stage * ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE  # default 20
            return min(lifetime // divisor, hard_max)
```

**Tuning knobs:**
- `ANCHOR_CAP_FACET_DIVISOR = 50` — 500 lifetime resonance → cap level 10.
- `ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE = 20` — at path stage 1, hard max = 20
  (well above path cap of 10); at path stage 6, hard max = 120 (well above
  path cap of 60).
- Both live in `world.magic.constants` as module-level constants. Adjusting
  is a code change, not a settings/admin change.

**Effective cap composition:**
- Path cap = `path_stage × 10`. Always applies.
- Anchor cap = `min(lifetime/50, path_stage × 20)`.
- Effective cap = `min(path_cap, anchor_cap)` = `min(path_stage × 10, lifetime/50, path_stage × 20)`.
- Path cap binds for low-lifetime characters (early game).
- Lifetime cap binds for mid-game (you've earned, but not enough yet).
- Hard ceiling binds only at the extreme tail (massive lifetime accumulation
  at a stage where path_stage × 20 < lifetime/50, i.e., very late game).

### 6.2 MANTLE

```python
case TargetKind.MANTLE:
    max_cleared = thread.owner.character.mantle_clearances.max_cleared_level(
        thread.target_mantle
    )
    return max_cleared * 10
```

A character with no clearance rows has cap 0 — they cannot weave a Mantle
thread. Each level cleared raises the cap by 10. Effective cap = `min(path_cap, max_cleared × 10)`.

### 6.3 COVENANT_ROLE

```python
case TargetKind.COVENANT_ROLE:
    return thread.owner.current_level * 10
```

`current_level` reads from the existing `CharacterSheet.current_level`
property, which sums character class levels. Effective cap = `min(path_cap, character_level × 10)`.

**Weave gate (separate from cap):** `weave_thread` for `COVENANT_ROLE` rejects
weaves when no `CharacterCovenantRole` row has ever existed for
`(owner, target_covenant_role)`. The character must have taken the role at
least once via the covenant ritual. Removed roles still satisfy the gate.

```python
def _validate_covenant_role_weave(owner: CharacterSheet, role: CovenantRole) -> None:
    if not owner.character.covenant_roles.has_ever_held(role):
        raise CovenantRoleNeverHeldError(role.name)
```

`CovenantRoleNeverHeldError` follows the existing `MagicError` /
`AtonementAffinityError` pattern: typed exception with `user_message` and
SAFE_MESSAGES allowlist for API-safe responses.

### 6.4 ROOM (deferred)

`ROOM` thread anchor cap remains `AnchorCapNotImplemented`. Out of scope for
this spec. Future room-imbuing spec can adopt similar patterns.

## 7. Service Function Surface

### 7.1 New service functions in `world.items.services`

```python
def attach_facet_to_item(
    *,
    crafter: AccountDB,
    item_instance: ItemInstance,
    facet: Facet,
    attachment_quality_tier: QualityTier,
) -> ItemFacet:
    """Apply a Facet to an ItemInstance.

    Raises:
        FacetCapacityExceeded — item has no remaining slots
        FacetAlreadyAttached — this facet is already on the item
    """


def remove_facet_from_item(
    *,
    item_facet: ItemFacet,
    actor: AccountDB,
) -> None:
    """Remove a Facet from an ItemInstance.

    Decoration removal — primarily for crafter mistakes, NPC vendor cleanup,
    or staff intervention. Raises if any active threads would be orphaned.
    """


def equip_item(
    *,
    character: CharacterSheet,
    item_instance: ItemInstance,
    body_region: BodyRegion,
    equipment_layer: EquipmentLayer,
) -> EquippedItem:
    """Place item in the given slot. Replaces any existing slot occupant.

    Raises:
        SlotConflict — region/layer already occupied
        SlotIncompatible — template doesn't declare this region/layer
    """


def unequip_item(
    *,
    character: CharacterSheet,
    body_region: BodyRegion,
    equipment_layer: EquipmentLayer,
) -> None:
    """Remove the item in the given slot. No-op if slot is empty."""
```

### 7.2 New service functions in `world.items.services.mantles`

```python
def record_codex_research_for_mantle(
    *,
    character_sheet: CharacterSheet,
    mantle: Mantle,
    level: int,
) -> None:
    """Triggered after the character learns the codex entry for level N.

    If both codex + mission gates are now cleared, creates a
    MantleLevelClearance row.
    """


def record_mission_completion_for_mantle(
    *,
    character_sheet: CharacterSheet,
    mantle: Mantle,
    level: int,
) -> None:
    """Triggered after mission completion. Same logic as codex side."""


def get_max_cleared_mantle_level(
    *,
    character_sheet: CharacterSheet,
    mantle: Mantle,
) -> int:
    """Return the highest cleared level for this character + mantle (0 if none)."""
```

### 7.3 New service functions in `world.covenants.services`

```python
def assign_covenant_role(
    *,
    character_sheet: CharacterSheet,
    covenant_role: CovenantRole,
) -> CharacterCovenantRole:
    """Record that a character has taken a covenant role.

    Triggered by the covenant ritual (when that system exists). For PR1,
    seeded via tests + admin. The future covenant group spec adds a
    `covenant_instance` parameter and FK target.
    """


def end_covenant_role(
    *,
    assignment: CharacterCovenantRole,
) -> None:
    """Mark a role assignment as ended (sets left_at)."""


def current_covenant_role(
    sheet: CharacterSheet,
) -> Optional[CovenantRole]:
    """Return the character's currently-active role, if any.

    Returns the single active role, or None. Multi-covenant participation
    (where a character could hold a Battle role and a Durance role
    simultaneously) requires the future CovenantInstance model and is not
    expressible until that spec lands.
    """


def is_gear_compatible(
    role: CovenantRole,
    archetype: GearArchetype,
) -> bool:
    """True iff a GearArchetypeCompatibility row exists for (role, archetype).

    Existence-only check. No row means incompatible.
    """
```

### 7.4 Extension to `world.magic.services.threads.weave_thread`

Adds match arms for FACET, MANTLE, COVENANT_ROLE in the existing
`weave_thread` service. FACET requires the `ThreadWeavingUnlock` (single
global unlock for FACET kind, no per-facet gating). MANTLE requires at least
level-1 clearance. COVENANT_ROLE requires "has ever held the role."

### 7.5 Extension to `world.magic.services.threads.compute_anchor_cap`

Adds match arms per §6 above. Removes the `AnchorCapNotImplemented` raise
for ITEM (kind dropped) and replaces with new FACET/MANTLE/COVENANT_ROLE
arms. ROOM remains as `AnchorCapNotImplemented`.

### 7.6 Extension to `world.magic.services.gain.resonance_daily_tick`

Adds the `outfit_daily_trickle_for_character` step per §5.1. The existing
residence trickle and outfit-stub paths compose into one daily orchestrator.

### 7.7 Extension to `world.mechanics.services.get_modifier_total`

Per §5.5 — adds equipment walk for relevant ModifierTargets.

## 8. API Surface

Most additions are read-mostly:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/items/item-facets/` | GET (filter by item) | List facets on an item |
| `/api/items/item-facets/` | POST | Crafter attaches a facet (gated on permissions) |
| `/api/items/mantles/` | GET | Catalog of mantles |
| `/api/items/mantles/{id}/levels/` | GET | Per-level def + my clearance status |
| `/api/items/mantles/{id}/clearances/` | GET | My clearance rows |
| `/api/items/equipped/` | GET | My equipped items + facets |
| `/api/items/equipped/` | POST | Equip an item to a slot |
| `/api/items/equipped/{id}/` | DELETE | Unequip |
| `/api/covenants/role-assignments/` | GET | My role assignments (active + historical) |
| `/api/covenants/gear-compatibilities/` | GET | Compatibility lookup table |

The existing `/api/magic/threads/` ViewSet handles FACET, MANTLE, and
COVENANT_ROLE Threads via the same endpoint (the discriminator already
flows through). New `target_kind` values just need serializer support.

## 9. Migration Plan

### 9.1 Schema migrations

Migrations land in dependency order:

1. `world.magic` — add `Thread.target_facet`, `target_mantle`,
   `target_covenant_role` FKs (nullable to start). Add new TargetKind values.
   Add per-kind unique + check constraints.
2. `world.items` — add `ItemTemplate.facet_capacity`, `gear_archetype`.
   Create `ItemFacet`, `Mantle` (with OneToOne FK to ItemInstance),
   `MantleLevelDefinition`, `MantleLevelClearance` models.
3. `world.covenants` — create `CharacterCovenantRole` (no `covenant_instance`
   FK; that field is added by the future covenant group spec via migration).
   Create `GearArchetypeCompatibility`.
4. `world.magic` — drop `CharacterFacet` model + table. Drop `TargetKind.ITEM`
   value. No data migration; pre-alpha, no production data.

### 9.2 Factory updates

- `CharacterFacetFactory` deprecated; replaced by `ThreadFactory(as_facet_thread=True)`.
- New factories with explicit natural keys:

  | Factory | Natural key (`django_get_or_create`) |
  |---|---|
  | `ItemFacetFactory` | `("item_instance", "facet")` |
  | `MantleFactory` | `("name",)` |
  | `MantleLevelDefinitionFactory` | `("mantle", "level")` |
  | `MantleLevelClearanceFactory` | `("character_sheet", "mantle", "level")` |
  | `CharacterCovenantRoleFactory` | `("character_sheet", "covenant_role")` (rows are unique only when `left_at IS NULL`, so factory callers may need to pass `left_at` explicitly to disambiguate test fixtures with multiple historical assignments) |
  | `GearArchetypeCompatibilityFactory` | `("covenant_role", "gear_archetype")` |

### 9.3 Seed extensions

`seed_magic_dev` gains:
- `seed_facet_thread_unlock()` — authors a single global FACET ThreadWeavingUnlock.
- `seed_mantle_starter_catalog()` — 1-2 reference mantles with full level
  authoring (codex entries + per-level effects). Mission gate seeded by a
  future Mission-system spec.

`world.items` gains a new seed module:
- `seed_items_dev()` — composes `seed_item_template_starter_catalog()`,
  `seed_quality_tier_starter()`, `seed_gear_archetype_compatibility()`.

`world.covenants` gains:
- `seed_gear_archetype_compatibility()` — authors compatibility rows for the
  current 6+ canonical CovenantRoles (Sword/Shield/Crown × Durance + future).

## 10. Phasing

**The spec ships as one design document. Implementation is 4 sequenced PRs.**

### PR1 — Facets, Resonance Regen, Covenant Compat, FACET Anchor Cap

The minimum viable items integration. Lands:

- All schema changes for ItemFacet, ItemTemplate extensions, Thread FACET kind,
  CharacterFacet drop. No data migration (pre-alpha).
- `attach_facet_to_item`, `equip_item`, `unequip_item` service functions.
- Resonance regen pipeline (§5.1) and ResonanceGrant typed-FK column for
  `outfit_item_facet`.
- Tier-0 facet bonus pipeline (§5.2) and modifier walk extension (§5.5,
  facet half).
- FACET anchor cap formula (§6.1).
- `CharacterCovenantRole` model + assignment service functions.
- `GearArchetypeCompatibility` model + `is_gear_compatible` lookup.
- Covenant role × gear archetype compatibility math (§5.6). Both
  `role_base_bonus_for_target` and `item_mundane_stat_for_target` return 0
  placeholders in PR1. The `covenant_role_bonus` walker IS wired into
  `get_modifier_total` in PR1 and runs on every modifier query touching
  equipment-relevant categories — it just contributes 0 for every target
  until PR3 authors per-role bonus values and the `ItemCombatStat` model.
  This is intentional: PR1 ships the structural integration (pipeline
  doesn't crash, walker is on the hot path, modifier breakdown reports the
  walker as a contributing source), and PR3 lights up the values without
  any wiring changes. The PR1 `test_gear_compatibility_pipeline` test
  asserts shape (no exceptions, contribution rows present) and uses
  test-injected non-zero values for both lookups to validate the additive
  vs max branching without depending on PR3's eventual authoring choices.
- COVENANT_ROLE Thread kind + cap formula + weave gate (§6.3).
- `gear_archetype` on ItemTemplate.
- Seed extensions for facet unlock + ItemTemplate starter catalog.
- Pipeline integration tests for §5.1 + §5.2 + §5.6.
- API endpoints for ItemFacet CRUD, equip/unequip.

**Why this slice:** every part is needed for the headline mechanic (regen +
fashion incentive). Mantles are a separate authored-content surface; combat
stats need combat balance; transfer service functions are independent.

### PR2 — Mantles

- All Mantle schema (Mantle, MantleLevelDefinition, MantleLevelClearance).
- MANTLE Thread kind + anchor cap formula (§6.2).
- `record_codex_research_for_mantle`, `record_mission_completion_for_mantle`,
  `get_max_cleared_mantle_level` service functions.
- Mantle ↔ ItemInstance OneToOne wiring (Mantle.item_instance FK).
- Reference mantle seed (1-2 mantles fully authored).
- Mantle pipeline integration tests.
- API endpoints for mantle catalog + clearance status.
- Mission gate stays nullable until missions ship.

### PR3 — Combat Stats + ItemCapabilityGrant

- `ItemCombatStat` model (or fields on ItemTemplate/Instance) for weapon damage,
  armor protection, durability.
- `ItemCapabilityGrant` model — items as capability sources, parallel to
  `TechniqueCapabilityGrant`.
- `_get_equipment_sources` extension to `get_capability_sources_for_character`.
- Wire `role_base_bonus_for_target` to actual values once combat balance is
  set. Mundane stat formulas land here.
- Combat pipeline integration test exercising the full equipped → role bonus
  → mundane stat → modifier total chain.

### PR4 — Transfer Service Functions + Crafting Recipe Foundation

- `give_item`, `pick_up_item`, `drop_item`, `steal_item`, `transfer_item`
  service functions on top of the existing `OwnershipEvent` ledger.
- Crafting recipe foundation (model + skill gating + material cost).
  Designed in a *separate* spec — this PR is just the items-side scaffolding
  for crafted item creation.

## 11. Testing Strategy

### 11.1 Unit tests per app

- `world.items.tests.test_item_facet` — capacity validation, attachment,
  removal, unique constraint, attachment quality independence.
- `world.items.tests.test_mantle` — Mantle/Level/Clearance shape, level
  ordering, clearance lookup.
- `world.covenants.tests.test_character_covenant_role` — assignment, ending,
  has-ever-held lookup, current role lookup.
- `world.covenants.tests.test_gear_compatibility` — compatibility lookup
  (row present = compatible, row absent = incompatible).
- `world.magic.tests.test_anchor_cap` — extends existing test class with
  FACET, MANTLE, COVENANT_ROLE cases. Removes the
  `test_item_raises_not_implemented` test (kind dropped).

### 11.2 Pipeline integration tests

`src/integration_tests/pipeline/`:

- `test_outfit_resonance_trickle_pipeline.py` — full chain:
  seed_magic_config → equip facet-bearing item → daily tick → ResonanceGrant
  ledger row + balance increment.
- `test_facet_passive_bonus_pipeline.py` — equip matching items → walk
  modifier → tier-0 contribution appears.
- `test_facet_thread_pull_pipeline.py` — weave FACET thread → spend
  resonance for pull → CombatPullResolvedEffect with FACET-aware scaling.
- `test_mantle_attunement_pipeline.py` (PR2) — research codex + complete
  mission → MantleLevelClearance → weave Mantle thread → cap reflects level.
- `test_covenant_role_thread_pipeline.py` — assign role → weave thread →
  level-cap matches character level → bonus contribution.
- `test_gear_compatibility_pipeline.py` — equip compatible vs incompatible
  gear → role bonus contribution differs per archetype.

### 11.3 Handler-as-cache verification

- `test_modifier_total_no_query.py` — uses `assertNumQueries(0)` to verify
  that `get_modifier_total` performs no queries against character-relationship
  tables when the relevant handlers are warm. Catches regressions where a
  service function bypasses a handler and slips a query in.

## 12. Tuning Knobs (Playtest TBD)

| Knob | Location | Default | Rationale |
|---|---|---|---|
| `outfit_daily_trickle_per_item_resonance` | ResonanceGainConfig | 1 | Existing field, may need to scale up substantially given the level/quality multiplications. |
| `ANCHOR_CAP_FACET_DIVISOR` | world.magic.constants | 50 | Lifetime/50 → cap level. |
| `ANCHOR_CAP_FACET_HARD_MAX_PER_STAGE` | world.magic.constants | 20 | path_stage × 20 hard ceiling. |
| `outfit_thread_level_factor` formula | world.magic.services.gain | `max(1, thread.level)` | Linear amplification; could cap or use sqrt for diminishing returns. |
| Tier-0 facet bonus level scaling | world.magic.services | `max(1, thread.level)` | Same shape as regen. |
| FACET thread pull worn-aggregate scaling | world.magic.services.threads | linear sum | Could log-scale to reduce gear-stacking dominance. |

All these are flagged for playtest iteration. The spec's design intent is
"strong but not absurd" — tuning happens once the mechanism ships and players
are interacting with it.

## 13. Out of Scope and Dependencies

### 13.1 Hard dependencies

- **Codex system** — `MantleLevelDefinition.codex_entry_required` requires
  `world.codex.CodexEntry` rows. PR2 must seed Codex entries for the reference
  mantles.
- **Mission system (future spec).** Mantle attunement is intended to be gated
  by both research AND mission completion, but only the codex half ships in
  this spec because the Mission model doesn't exist yet. The future Mission
  system spec adds a `mission_required` FK to `MantleLevelDefinition` via
  migration and updates the clearance service to require both gates. No
  blocker for PR2 — mantles work end-to-end with codex-only gating until
  missions land.
- **Covenant group model (future spec).** Multi-covenant participation
  requires a `CovenantInstance` model (or equivalent) that doesn't exist
  yet. The future covenant group spec adds a `covenant_instance` FK to
  `CharacterCovenantRole` via migration and relaxes the unique constraint
  to include it. Until then, every active CharacterCovenantRole row is the
  character's single role assignment — no ambiguity, no blocker.

### 13.2 Soft dependencies (future specs)

- **Combat balance** — PR3 needs combat to be sufficiently balanced for
  `role_base_bonus_for_target` to have meaningful values.
- **Crafting recipe spec** — PR4's transfer service functions are
  independent, but crafted-item creation needs the recipe model from a
  separate spec.

### 13.3 Explicitly deferred

- ROOM thread anchor cap (separate room-imbuing spec).
- Visible equipment rendering for character appearance (frontend concern).
- Inventory UI / equipping UI / facet attachment UI (frontend concern,
  follows pipeline tests passing).
- Covenant ritual flow (covenant system's concern).
- Public fashion leaderboard / "most-admired outfit" mechanics (post-MVP).
- **Motif / aura / style as a magical-significance axis (future spec — explicit gap).**
  Resonance covers thematic affinity (Praedari = predator, Aggrandi = web-trap, etc.).
  Facets cover specific imagery (Spider, Wolf, Silver). **Neither covers stylistic
  vibe** — "seductive," "beguiling," "menacing," "austere," "regal," "feral." A
  paladin's getup, an evil sorceress's robes, battle lingerie on a Sword-archetype
  warrior — these communicate something about the character that doesn't reduce to
  resonance theme or imagery hierarchy.

  The existing `Motif`, `MotifResonance`, and `MotifResonanceAssociation` models in
  `world.magic.models.motifs` are scaffolding for this concept but **a coherent system
  has not yet been designed around them**. A dedicated future spec needs to address:

  - How items carry style tags (parallel to but distinct from facets — `ItemMotif`?
    `ItemStyleTag`? Some other shape?).
  - Whether threads can anchor on Motifs (new `MOTIF` Thread kind), with bonuses
    parallel to FACET (regen + tier-0 + tier 1+ pulls).
  - Crafter mini-games around adapting an item to a specific style — "remake this
    chain shirt as battle lingerie" as an authored craft action with a skill check
    and material cost. This is part of the crafter participation surface this spec
    creates pressure for but does not design.
  - How style tags compose with (or contradict) facets when both are on the same item.
  - Public-perception interaction (does being seen in a "seductive" outfit at a
    salon scene boost the wearer the way endorsement-pose mechanics already work for
    resonance gain?).

  **Design intent that should NOT be lost when this future spec lands:** flamboyant
  fashion that emphasizes a character's identity is meant to be a *strong* mechanical
  axis. The architectural patterns this spec establishes (typed-FK Thread anchor,
  attachment quality on through-model, on-demand modifier walk, lifetime-earned
  anchor cap) are intended to compose with style/motif when it ships, but the
  *design surface* — what styles exist, how they're authored, how they overlap with
  resonance, what crafter actions adapt items to them — needs its own pass. **No
  Motif model changes or pipeline work land in this spec.** This entry exists so
  the gap stays visible.

## 14. Open Questions

These are bounded enough to settle in implementation, not blocking spec
sign-off:

1. **`CharacterCovenantRole.covenant_instance` FK** — **resolved: not in this spec.**
   Django requires FK targets to exist; the `CovenantInstance` model is the
   future covenant group spec's concern. This spec ships
   `CharacterCovenantRole` without that FK. When the covenant group spec
   lands, a follow-up migration adds the FK and relaxes the unique
   constraint to include it.
2. **Mission gate** — **resolved: not in this spec.** Same reason as #1 —
   no Mission model exists yet. PR2 mantle clearances gate by Codex
   research alone; the future Mission spec adds the FK + the both-gates
   requirement.
3. **FACET thread pull when no matching items worn** — refund the resonance,
   or block at action UI? Lean: block at UI, no refund. Spec the prevention
   in PR1.
4. **Facet capacity exceeded — UI flow** — does the API reject silently or
   surface "capacity full"? Lean: surface explicit error; client-side
   capacity preview.
5. **Per-CovenantRole bonus authoring (`role_base_bonus_for_target`)** —
   model shape decided in PR3 once combat balance is addressed.
6. **`COMPAT_DAMPENING_MULTIPLIER` value** — 0.20 is a starting guess. May
   need to be 0.10 or 0.30 depending on how quickly role bonuses outscale
   mundane stats. Playtest iteration.

---

## Summary

This spec lands the items system's headline gameplay (fashion-resonance
regen, facet-thread bonuses, mantle attunement, covenant gear compatibility)
in a single coherent design, sequenced into 4 implementation PRs. The spec
preserves Spec A's typed-FK Thread invariant by adding three new kinds
(FACET, MANTLE, COVENANT_ROLE) with proper typed FKs and per-kind constraints,
replaces the ITEM placeholder, and folds the narrative-only `CharacterFacet`
model into Thread-on-Facet for a single source of truth.

The on-demand modifier walk pattern keeps equipment contributions out of
the eager `CharacterModifier` table and leans on existing SharedMemoryModel
caching to stay performant. Mantles introduce per-level Codex + Mission
gating that compose with Spec A's existing thread weaving services.

Phasing is intentionally aggressive — PR1 ships the headline (regen + tier-0
bonuses + covenant compat) and the rest follows. By the time PR4 lands,
crafters have a meaningful role in driving every other character's
mechanical ceiling, fashion is the dominant non-RP regen path, and covenant
roles are the dominant late-game stat contributor on compatible gear.
