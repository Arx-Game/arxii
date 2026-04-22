# Magic System

Power flows from identity and connection. Characters have auras (affinity balance),
resonances (style tags), gifts (power categories), and threads (magical relationships).
Techniques are the primary magical abilities, powered by intensity and control stats.

**Source:** `src/world/magic/`
**API Base:** `/api/magic/`
**Design Docs:**
- `docs/plans/2026-01-20-magic-system-design.md` (original system design)
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` (cantrip/technique alignment)
- `docs/superpowers/specs/2026-04-18-resonance-pivot-spec-a-threads-and-currency-design.md` (Resonance Pivot Spec A — Threads + Currency + Rituals + Mage Scars rename)
- `docs/superpowers/plans/2026-04-19-resonance-pivot-spec-a-threads-and-currency.md` (19-phase Spec A implementation plan)

---

## Enums (types.py + constants.py)

```python
from world.magic.types import (
    AffinityType,        # CELESTIAL, PRIMAL, ABYSSAL
    AnimaRitualCategory, # SOLITARY, COLLABORATIVE, ENVIRONMENTAL, CEREMONIAL
)

from world.magic.constants import (
    TargetKind,              # Thread discriminator: TRAIT, TECHNIQUE, ITEM, ROOM,
                             # RELATIONSHIP_TRACK, RELATIONSHIP_CAPSTONE
    EffectKind,              # ThreadPullEffect payload: FLAT_BONUS,
                             # INTENSITY_BUMP, VITAL_BONUS, CAPABILITY_GRANT,
                             # NARRATIVE_ONLY
    VitalBonusTarget,        # MAX_HEALTH, DAMAGE_TAKEN_REDUCTION
    RitualExecutionKind,     # SERVICE, FLOW
    PendingAlterationStatus, # OPEN, RESOLVED, STAFF_CLEARED
    AlterationTier,
    ALTERATION_TIER_CAPS,
    THREADWEAVING_ITEM_TYPECLASSES,
)
```

Legacy enums `ResonanceScope`, `ResonanceStrength`, and `ThreadAxis` were
removed as part of Resonance Pivot Spec A — `CharacterResonance.scope/strength`
and the 5-axis Thread model no longer exist.

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `EffectType` | Types of magical effects (Attack, Defense, Movement) | `name`, `description`, `base_power`, `base_anima_cost`, `has_power_scaling` |
| `TechniqueStyle` | How magic manifests (Manifestation, Subtle, Prayer) | `name`, `description`, `allowed_paths` (M2M to `classes.Path`) |
| `IntensityTier` | Power effect thresholds | `name`, `threshold`, `control_modifier`, `description` |
| `Restriction` | Limitations that grant power bonuses | `name`, `description`, `power_bonus` |
| `Facet` | Hierarchical imagery/symbolism (Category > Subcategory > Specific) | `name`, `parent` (self-FK), `description` |
| `Gift` | Thematic collections of techniques | `name`, `description`, `resonances` (M2M to `Resonance`), `creator` (FK to CharacterSheet) |
| `Affinity` | CELESTIAL / PRIMAL / ABYSSAL | `name`, optional OneToOne `modifier_target` |
| `Resonance` | Identity resonance tags | `name`, `affinity` FK, `opposite` self-OneToOne, optional `modifier_target` OneToOne |

**Note:** `Affinity` and `Resonance` are proper first-class domain models in
this app (each with an optional OneToOne link back to `mechanics.ModifierTarget`
for modifier-system integration). The old `ThreadType` lookup was deleted as
part of the Resonance Pivot — relationship flavor is now carried by
`relationships.RelationshipTrack`.

### Character State

| Model | Purpose | Key Fields | Relationship |
|-------|---------|------------|--------------|
| `CharacterAura` | Affinity percentages (must sum to 100) | `celestial`, `primal`, `abyssal` | OneToOne via `character.aura` |
| `CharacterResonance` | Per-character per-resonance identity + currency (Spec A §2.2) | `character_sheet` FK, `resonance` FK, `balance`, `lifetime_earned`, `claimed_at`, `flavor_text` | FK via `character_sheet.resonances` (unique_together: (character_sheet, resonance)) |
| `CharacterGift` | Acquired gifts | `gift`, `acquired_at` | FK via `character.character_gifts` |
| `CharacterTechnique` | Known techniques | `technique`, `acquired_at` | FK via `character.character_techniques` |
| `CharacterAnima` | Magical energy pool | `current`, `maximum`, `last_recovery` | OneToOne via `character.anima` |
| `CharacterAnimaRitual` | Personalized recovery rituals | `stat`, `skill`, `resonance`, `personal_description`, `is_primary` | FK via `character.anima_rituals` |
| `CharacterAffinityTotal` | Cached affinity totals | `character`, `affinity`, `total` | FK via character |

**CharacterResonance reshape note.** Prior to Spec A, `CharacterResonance`
carried `scope`, `strength`, `is_active`, and FK'd `ObjectDB`. Those fields
were dropped (no readers beyond Mage Scars, which now uses
`character.resonances.most_recently_earned()`), `character` was re-FK'd to
`CharacterSheet`, and `balance` + `lifetime_earned` were added. Row existence
replaces the old `is_active` flag. `CharacterResonanceTotal` (denormalized
aggregate) was deleted — aura recompute now reads `CharacterModifier` rows
whose target category is `resonance` directly.

### Techniques (Player-Created Abilities)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Technique` | A specific magical ability within a Gift | `name`, `gift` (FK), `style` (FK to TechniqueStyle), `effect_type` (FK to EffectType), `restrictions` (M2M), `level`, `intensity`, `control`, `anima_cost`, `creator` |

Key fields: `intensity` (base power), `control` (base safety/precision), `level` (progression gate, derives tier).
Key property: `tier` (derived from level: 1-5=T1, 6-10=T2, etc.)

**Intensity and Control:** These are base/static values on the technique. Runtime casting
values (after resonance bonuses, combat escalation, audere states) are tracked by a
separate casting handler. When intensity exceeds control at runtime, effects become
unpredictable and anima cost spikes. If anima cost exceeds the character's pool, the
excess deals damage to the caster.

### Cantrips (CG Technique Templates)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Cantrip` | Staff-curated starter technique template | `name`, `description`, `archetype`, `effect_type` (FK), `style` (FK), `base_intensity`, `base_control`, `base_anima_cost`, `requires_facet`, `allowed_facets` (M2M) |

Cantrips are baby techniques. At CG finalization, a cantrip creates a real Technique
(intensity=base_intensity, control=base_control, etc.) in the character's Gift.
Mechanical fields are hidden from the player — they only see name, description,
archetype grouping, and optional facet selection. Filtered by Path (cantrip's style
must be in Path's allowed_styles).

### Motif System

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Motif` | Character-level magical aesthetic | `character`, `name`, `description` |
| `MotifResonance` | Resonances in a motif | `motif`, `resonance` (FK to ModifierTarget) |
| `MotifResonanceAssociation` | Links resonances to facets in a motif | `motif_resonance`, `facet` |
| `CharacterFacet` | Links characters to facets | `character`, `facet`, `resonance` |

### Threads as Currency Consumers (Resonance Pivot Spec A §2.1)

The legacy 5-axis `Thread` / `ThreadType` / `ThreadJournal` / `ThreadResonance`
family was deleted in favor of a discriminator + typed-FK design. A Thread is
owned by a CharacterSheet, channels a single Resonance, and is anchored to
exactly one of: Trait / Technique / Item-ObjectDB / Room-ObjectDB /
RelationshipTrackProgress / RelationshipCapstone.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Thread` | Per-character attachment to one anchor that channels one Resonance | `owner` FK CharacterSheet, `resonance` FK, `target_kind`, `target_trait` / `target_technique` / `target_object` / `target_relationship_track` / `target_capstone` (exactly one populated per kind), `name`, `description`, `developed_points`, `level`, `created_at`, `updated_at`, `retired_at` (soft-retire) |
| `ThreadLevelUnlock` | Per-thread XP-locked-boundary receipt | `thread` FK, `unlocked_level`, `xp_spent`, `acquired_at` (unique per (thread, unlocked_level)) |

**Integrity layers on Thread.** (1) `clean()` asserts exactly one `target_*`
FK is populated and matches `target_kind`, and validates ITEM typeclass paths
against `THREADWEAVING_ITEM_TYPECLASSES`. (2) Per-kind `CheckConstraint`s
mirror the same rule at the DB layer. (3) Per-kind partial
`UniqueConstraint`s prevent duplicate threads for the same
(owner, resonance, target_kind, target_*) combination while still allowing
both an ITEM thread and a ROOM thread on the same ObjectDB. All typed FKs
use `on_delete=PROTECT` — anchors cannot be deleted while threads reference
them.

### Thread Lookup / Authoring Catalogs (Spec A §2.1 and §4.3)

All SharedMemoryModel lookups.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ThreadPullCost` | Per-tier pull pricing knobs | `tier` (unique: 1/2/3), `resonance_cost`, `anima_per_thread`, `label`. Cost *shape* lives in `spend_resonance_for_pull`; this table only holds the per-tier numbers |
| `ThreadXPLockedLevel` | XP-locked-boundary price list | `level` (unique; 20/30/40 on the internal scale), `xp_cost` |
| `ThreadPullEffect` | Authored pull-effect template | `target_kind`, `resonance` FK, `tier` (0..3), `min_thread_level`, `effect_kind`, + mutually-exclusive payload columns: `flat_bonus_amount`, `intensity_bump_amount`, `vital_bonus_amount` (+ `vital_target`), `capability_grant` FK to `CapabilityType`, `narrative_snippet`. Tier 0 = passive always-on; tiers 1–3 = paid pulls. Unique per (target_kind, resonance, tier, min_thread_level). CheckConstraints enforce payload/effect_kind alignment |
| `ImbuingProseTemplate` | Fallback narrative prose for Imbuing | `resonance` FK (nullable), `target_kind` (nullable), `prose`. Row with both NULL = universal fallback |
| `Ritual` | Authored ritual procedure | `name`, `description`, `hedge_accessible`, `glimpse_eligible`, `narrative_prose`, `execution_kind` (SERVICE/FLOW), `service_function_path` (SERVICE), `flow` FK (FLOW), optional `site_property` FK. CheckConstraint: exactly one dispatch payload |
| `RitualComponentRequirement` | Items required to perform a Ritual | `ritual` FK, `item_template` FK, `quantity`, optional `min_quality_tier` FK, `authored_provenance` |

### ThreadWeaving Acquisition (Spec A §2.1 / §4.2)

How a character gains the *right* to weave threads on a given anchor scope.
Same discriminator + typed-FK pattern as `Thread`. Gifts and Paths are not
thread anchors — they appear here only as unlock dimensions.

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ThreadWeavingUnlock` | Authored unlock catalog | `target_kind`, one of (`unlock_trait` FK Trait / `unlock_gift` FK Gift / `unlock_item_typeclass_path` str / `unlock_room_property` FK Property / `unlock_track` FK RelationshipTrack), `xp_cost`, `paths` M2M (in-band Paths), `out_of_path_multiplier` Decimal default 2.0. Per-kind partial unique constraints guarantee one unlock per anchor. CheckConstraints mirror the typed-FK rule; `target_kind=RELATIONSHIP_CAPSTONE` is forbidden (inherited from parent track). Has a derived `display_name` property |
| `CharacterThreadWeavingUnlock` | Per-character purchase record | `character` FK CharacterSheet, `unlock` FK, `acquired_at`, `xp_spent` (actual — in-Path=xp_cost, out-of-Path=xp_cost × multiplier), optional `teacher` FK RosterTenure. Unique per (character, unlock) |
| `ThreadWeavingTeachingOffer` | Teacher-side offer | `teacher` FK RosterTenure, `unlock` FK, `pitch`, `gold_cost`, `banked_ap`, `created_at`. Mirrors `CodexTeachingOffer` |

### Combat Pulls (live in `world/combat`, Spec A §3.8 / §2.1)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CombatPull` | Per-round commit envelope for a thread pull | `participant` FK, `encounter` FK, `round_number`, `resonance` FK, `tier` (1/2/3), `threads` M2M, `resonance_spent`, `anima_spent`, `committed_at`. Unique per (participant, round_number); indexed on (encounter, round_number) |
| `CombatPullResolvedEffect` | Frozen snapshot of one resolved effect at pull commit | `pull` FK, `kind`, `authored_value`, `level_multiplier`, `scaled_value`, `vital_target`, `source_thread` FK, `source_thread_level`, `source_tier`, `granted_capability` FK, `narrative_snippet`. CheckConstraints mirror ThreadPullEffect payload rules |

A CombatPull is considered *active* while `round_number == encounter.round_number`
(canonical liveness check). `expire_pulls_for_round` (combat services) deletes
stale rows on round advance and invalidates the per-character
`CharacterCombatPullHandler` cache.

### Mage Scars (renamed from Magical Scars — §7.2)

Cosmetic rename only. Class names, table names, and migration code paths
unchanged. Verbose_names, CLI strings, API-visible labels, and documentation
now say "Mage Scars."

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `MagicalAlterationTemplate` | OneToOne on ConditionTemplate; magic-specific alteration metadata | `tier`, `origin_affinity`, `origin_resonance`, `is_library`, `visibility_required` |
| `PendingAlteration` | Queued unresolved Mage Scar | `character` FK, `status` (OPEN/RESOLVED/STAFF_CLEARED), `scene` FK, triggering-state snapshot fields |
| `MagicalAlterationEvent` | Immutable provenance audit log | `pending`, `event_type`, `data`, `created_at` |

### Other

| Model | Purpose |
|-------|---------|
| `AnimaRitualPerformance` | Historical record of ritual performances |
| `Reincarnation` | Tracks character reincarnation events |

---

## Key Methods and Properties

### CharacterAura

```python
# Get a character's aura (OneToOne relationship)
aura = character.aura  # May raise DoesNotExist if not created

# Get dominant affinity
aura.dominant_affinity  # Returns AffinityType enum (CELESTIAL, PRIMAL, or ABYSSAL)

# Validation: percentages must sum to 100
aura.celestial = Decimal("50.00")
aura.primal = Decimal("30.00")
aura.abyssal = Decimal("20.00")
aura.save()  # Calls full_clean() automatically
```

### Thread (new Spec A model)

```python
# The populated FK, picked by target_kind
thread.target   # Returns the Trait / Technique / ObjectDB / RelationshipTrackProgress / RelationshipCapstone

# Resolved level cap (per Spec A §2.4)
from world.magic.services import (
    compute_anchor_cap,
    compute_path_cap,
    compute_effective_cap,
)
cap = compute_effective_cap(thread)   # min(path_cap, anchor_cap)
```

### Per-Character Handlers

```python
# character is a Character typeclass instance
threads = character.threads.all()                    # list[Thread] (cached, retired_at filtered)
threads_for_res = character.threads.by_resonance(resonance)
passive_hp = character.threads.passive_vital_bonuses("MAX_HEALTH")

balance = character.resonances.balance(resonance)    # int
lifetime = character.resonances.lifetime(resonance)  # int
cr = character.resonances.get_or_create(resonance)   # CharacterResonance (lazy create)
most_recent = character.resonances.most_recently_earned()   # used by Mage Scars

active_pulls = character.combat_pulls.active()       # list[CombatPull]
pulls_in_enc = character.combat_pulls.active_for_encounter(encounter)
pulled_hp = character.combat_pulls.active_pull_vital_bonuses("MAX_HEALTH")

# After any mutation that changes these collections, call:
character.threads.invalidate()
character.resonances.invalidate()
character.combat_pulls.invalidate()
```

### Technique

```python
technique.tier       # Derived from level: 1-5=T1, 6-10=T2, etc.
technique.intensity  # Base power stat
technique.control    # Base safety/precision stat
technique.anima_cost # Base anima cost to activate
```

---

## Common Queries

### Check if character has a gift

```python
from world.magic.models import CharacterGift

# By gift name
has_pyromancy = CharacterGift.objects.filter(
    character=character,
    gift__name="Pyromancy"
).exists()

# Get all character's gifts
character_gifts = CharacterGift.objects.filter(character=character).select_related("gift")
```

### Get character's aura or create default

```python
from world.magic.models import CharacterAura

aura, created = CharacterAura.objects.get_or_create(
    character=character,
    defaults={
        "celestial": Decimal("0.00"),
        "primal": Decimal("80.00"),
        "abyssal": Decimal("20.00"),
    }
)
```

### Get character's techniques from a specific gift

```python
from world.magic.models import CharacterTechnique

techniques = CharacterTechnique.objects.filter(
    character=character,
    technique__gift__name="Shadow Majesty"
).select_related("technique", "technique__gift")
```

### Get all threads for a character

```python
# Preferred: use the cached handler (single query, select_related on all targets).
threads = character.threads.all()

# Direct ORM (bypasses the handler cache):
from world.magic.models import Thread

threads = Thread.objects.filter(
    owner=character_sheet,
    retired_at__isnull=True,
).select_related(
    "resonance__affinity",
    "target_trait",
    "target_technique",
    "target_object",
    "target_relationship_track",
    "target_capstone",
)
```

### Grant and spend resonance currency

```python
from world.magic.services import (
    grant_resonance,
    spend_resonance_for_imbuing,
    spend_resonance_for_pull,
    preview_resonance_pull,
    weave_thread,
    accept_thread_weaving_unlock,
    compute_thread_weaving_xp_cost,
)

# Earn (Spec C will author the gain surfaces that call this):
cr = grant_resonance(
    character_sheet=sheet,
    resonance=resonance,
    amount=3,
    source="social_scene_endorsement",
    source_ref=scene.pk,
)
assert cr.balance >= 3 and cr.lifetime_earned >= 3

# Imbue a Thread (greedy advancement through developed_points -> level):
result = spend_resonance_for_imbuing(
    character_sheet=sheet,
    thread=thread,
    amount=20,
)
# result is a ThreadImbueResult dataclass with the starting/ending level,
# dp remaining, and blocked_by reason if the bucket stopped early.

# Pay XP at an XP-locked boundary (level 20/30/40 on the internal scale):
from world.magic.services import cross_thread_xp_lock
cross_thread_xp_lock(character_sheet=sheet, thread=thread, level=20)

# Pull (combat or ephemeral):
pull_result = spend_resonance_for_pull(...)

# Weave a new thread (requires the unlock):
new_thread = weave_thread(
    character_sheet=sheet,
    resonance=resonance,
    target_kind="TRAIT",
    target=trait_instance,
    name="Grandfather's patience",
)

# Acquire a ThreadWeavingUnlock (in-band or out-of-band pricing):
cost = compute_thread_weaving_xp_cost(sheet, unlock)
accept_thread_weaving_unlock(character_sheet=sheet, unlock=unlock, teacher=tenure_or_none)
```

### Preview a pull without mutating state

```python
from world.magic.services import preview_resonance_pull

preview = preview_resonance_pull(
    character_sheet=sheet,
    resonance=resonance,
    tier=2,
    threads=[thread_a, thread_b],
    combat_encounter=encounter_or_none,
)
# preview.resonance_cost / preview.anima_cost / preview.affordable
# preview.resolved_effects — list of scaled per-effect snapshots
```

### UI helper queries

```python
from world.magic.services import (
    imbue_ready_threads,
    near_xp_lock_threads,
    threads_blocked_by_cap,
)

ready = imbue_ready_threads(sheet)      # threads whose bucket is near a level-up
near = near_xp_lock_threads(sheet)      # threads approaching an XP-locked boundary
capped = threads_blocked_by_cap(sheet)  # threads blocked by path or anchor cap
```

### Get intensity tier for a value

```python
from world.magic.models import IntensityTier

# Get the highest tier at or below the intensity value
tier = IntensityTier.objects.filter(
    threshold__lte=intensity_value
).order_by("-threshold").first()
```

---

## API Endpoints

All endpoints require authentication. Base URL: `/api/magic/`

### Lookup Tables (Read-Only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/styles/` | GET | List technique styles |
| `/effect-types/` | GET | List effect types |
| `/restrictions/` | GET | List restrictions |
| `/facets/` | GET | List facets (hierarchical) |
| `/gifts/` | GET | List all gifts |
| `/gifts/{id}/` | GET | Gift detail with nested techniques |

**Note:** The `/thread-types/` endpoint was removed as part of Spec A —
the legacy ThreadType lookup no longer exists.

### Character Data (Filtered to owned characters)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/character-auras/` | GET/POST | Character aura data |
| `/character-resonances/` | GET | Character resonances (balance + lifetime_earned per Spec A §2.2; create/delete via service functions, not REST mutations) |
| `/character-gifts/` | GET/POST/DELETE | Character's acquired gifts |
| `/character-anima/` | GET/POST/PATCH | Character anima pool |
| `/character-anima-rituals/` | GET/POST/PATCH/DELETE | Character's rituals |
| `/character-facets/` | GET/POST/PATCH/DELETE | Character facet assignments |
| `/techniques/` | GET/POST/PATCH | Character techniques |

### Mage Scars (renamed from Magical Scars — §7.2 display-only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pending-alterations/` | GET | List open Mage Scars for the requesting account |
| `/pending-alterations/{id}/` | GET | Retrieve one Mage Scar |
| `/pending-alterations/{id}/resolve/` | POST | Resolve via library pick or author-from-scratch |
| `/pending-alterations/{id}/library/` | GET | Tier-matched library template list |

### Threads, Pull Preview, Rituals, ThreadWeaving (Spec A §4.5)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/threads/` | GET | List threads owned by requesting account (staff see all); excludes retired |
| `/threads/` | POST | Weave a new thread. Body must include `character_sheet_id`; serializer delegates to `weave_thread` |
| `/threads/{id}/` | GET | Thread detail with anchor + resonance |
| `/threads/{id}/` | DELETE | Soft-retire (stamps `retired_at`; row remains for historical references) |
| `/thread-pull-preview/` | POST | Read-only preview; body `{character_sheet_id, resonance_id, tier, thread_ids[], action_context?}`; returns resonance/anima cost + `affordable` + `resolved_effects[]` |
| `/rituals/perform/` | POST | Dispatch a Ritual via PerformRitualAction. Body `{character_sheet_id, ritual_id, kwargs, components[]}`; Imbuing takes `{thread_id}` in kwargs (view resolves into Thread instance) |
| `/teaching-offers/` | GET | Read-only list of `ThreadWeavingTeachingOffer` records |

**API conventions.**
- All mutations that need a character context require an explicit
  `character_sheet_id` — no implicit first-sheet selection.
- Service functions raise typed exceptions with `user_message` properties
  (`AnchorCapExceeded`, `AnchorCapNotImplemented`, `InvalidImbueAmount`,
  `ResonanceInsufficient`, `WeavingUnlockMissing`, `XPInsufficient`,
  `RitualComponentError`). Views surface those messages as HTTP 400 detail
  (never raw `str(exc)`).
- `ThreadViewSet` uses `IsThreadOwner` permission plus ownership filtering
  in `get_queryset()`; staff see all.

**Endpoints removed by Spec A.** `/thread-types/`, `/thread-journals/`,
`/thread-resonances/` — the underlying models were deleted. Journaling now
flows through relationships-app writeups for relationship-anchored threads,
and `JournalEntry.related_threads` M2M for all thread kinds.

---

## Frontend Integration

### Types
`frontend/src/character-creation/types.ts`
- `Affinity`, `Resonance`, `Gift`, `GiftListItem`, `AnimaRitualType`
- `AFFINITY_TYPES` constant: `['celestial', 'primal', 'abyssal']`
- `AffinityType` type alias

### API Hooks
`frontend/src/character-creation/queries.ts`
```typescript
// Fetch all affinities
const { data: affinities } = useAffinities();

// Fetch all resonances
const { data: resonances } = useResonances();

// Fetch all gifts (list view)
const { data: gifts } = useGifts();

// Fetch anima ritual types
const { data: ritualTypes } = useAnimaRitualTypes();
```

### Components
- `MagicStage.tsx` - Character creation magic selection UI

---

## Integration Points

### With Traits System (Future)
Magic intensity calculations will factor in trait values:
```python
# Example pattern (not yet implemented)
from world.traits.services import get_trait_value
willpower = get_trait_value(character, "willpower")
modified_intensity = base_intensity + (willpower * modifier)
```

### With Flows (Future)
Magic effects will execute via the flow engine:
```python
# Example pattern (not yet implemented)
from flows.engine import execute_flow
execute_flow("cast_power", context={
    "caster": character,
    "power": power,
    "target": target,
    "intensity": effective_intensity,
})
```

---

## Notes

- **Aura validation** - CharacterAura enforces percentages sum to 100 via `clean()`
- **Thread uniqueness (Spec A)** - One thread per (owner, resonance, target_kind, target_*) combination, enforced via per-kind partial `UniqueConstraint`s. Soft-retired threads (retired_at set) don't block new ones at the uniqueness level but are filtered out of handler caches and API listings.
- **Thread PROTECT FKs** - All five typed `target_*` FKs use `on_delete=PROTECT`. Anchors cannot be deleted while threads reference them. This is why `CharacterThreadHandler.passive_vital_bonuses` doesn't need an anchor-in-scope runtime filter.
- **Currency has no cap** - `CharacterResonance.balance` grows freely; the strategic tension is over allocation, not over a ceiling.
- **Pull-cost tuning surface** - `ThreadPullCost` rows hold per-tier numbers; the cost *formula shape* lives in `spend_resonance_for_pull`. Both the model docstring and service docstring cross-reference this split.
- **SharedMemoryModel** - All lookup tables + identity rows use Evennia's identity-map cache
- **Affinity/Resonance are domain models** - First-class models in this app with optional OneToOne links to `ModifierTarget` for modifier integration
- **Techniques are player-created** - Unlike lookup tables, techniques are unique per character
- **Cantrips are technique templates** - Staff-curated, produce real Techniques at CG finalization
- **Intensity/Control** - Base stats on techniques. Runtime values modified by resonance, combat, audere, and thread pull effects
- **No healing** - Shielding yes, restoration no. Healing is counter to the escalation-based combat design
