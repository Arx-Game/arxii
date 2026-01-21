# Magic System

Power flows from identity and connection. Characters have auras (affinity balance),
resonances (style tags), gifts (power categories), and threads (magical relationships).

**Source:** `src/world/magic/`
**API Base:** `/api/magic/`
**Design Doc:** `docs/plans/2026-01-20-magic-system-design.md`

---

## Enums (types.py)

```python
from world.magic.types import (
    AffinityType,        # CELESTIAL, PRIMAL, ABYSSAL
    ResonanceScope,      # SELF, AREA
    ResonanceStrength,   # MINOR, MODERATE, MAJOR
    AnimaRitualCategory, # SOLITARY, COLLABORATIVE, ENVIRONMENTAL, CEREMONIAL
    ThreadAxis,          # ROMANTIC, TRUST, RIVALRY, PROTECTIVE, ENMITY
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Affinity` | Three magical sources | `affinity_type`, `name`, `description` |
| `Resonance` | Style tags for magical identity | `name`, `slug`, `default_affinity` |
| `IntensityTier` | Power effect thresholds | `threshold`, `control_modifier`, `name` |
| `Gift` | Categories of magical powers | `name`, `slug`, `affinity`, `level_requirement`, `resonances` (M2M) |
| `Power` | Individual magical abilities | `name`, `slug`, `gift`, `affinity`, `base_intensity`, `base_control`, `anima_cost` |
| `AnimaRitualType` | Predefined recovery rituals | `name`, `slug`, `category`, `base_recovery` |
| `ThreadType` | Relationship archetypes | `romantic_threshold`, `trust_threshold`, etc., `grants_resonance` |

### Character State

| Model | Purpose | Key Fields | Relationship |
|-------|---------|------------|--------------|
| `CharacterAura` | Affinity percentages (must sum to 100) | `celestial`, `primal`, `abyssal` | OneToOne via `character.aura` |
| `CharacterResonance` | Personal resonances | `resonance`, `scope`, `strength`, `is_active` | FK via `character.resonances` |
| `CharacterGift` | Acquired gifts | `gift`, `acquired_at`, `notes` | FK via `character.gifts` |
| `CharacterPower` | Unlocked powers | `power`, `times_used`, `unlocked_at` | FK via `character.powers` |
| `CharacterAnima` | Magical energy pool | `current`, `maximum`, `last_recovery` | OneToOne via `character.anima` |
| `CharacterAnimaRitual` | Personalized rituals | `ritual_type`, `personal_description`, `is_primary` | FK via `character.anima_rituals` |

### Relationships (Threads)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Thread` | Connection between two characters | `initiator`, `receiver`, `romantic`, `trust`, `rivalry`, `protective`, `enmity`, `is_soul_tether` |
| `ThreadJournal` | IC journal entries on threads | `thread`, `author`, `content`, `*_change` fields |
| `ThreadResonance` | Resonances attached to threads | `thread`, `resonance`, `strength` |

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

### Thread

```python
# Get all thread types this thread qualifies for
matching_types = thread.get_matching_types()  # Returns list[ThreadType]

# Check if thread matches a specific type (internal method)
thread._matches_type(thread_type)  # Returns bool
```

---

## Common Queries

### Check if character has a gift

```python
from world.magic.models import CharacterGift

# By gift slug
has_pyromancy = CharacterGift.objects.filter(
    character=character,
    gift__slug="pyromancy"
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

### Get character's powers from a specific gift

```python
from world.magic.models import CharacterPower

powers = CharacterPower.objects.filter(
    character=character,
    power__gift__slug="shadow-majesty"
).select_related("power", "power__gift")
```

### Get all threads for a character

```python
from django.db.models import Q
from world.magic.models import Thread

threads = Thread.objects.filter(
    Q(initiator=character) | Q(receiver=character)
).select_related("initiator", "receiver")
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
| `/affinities/` | GET | List all affinities (3 total) |
| `/resonances/` | GET | List all resonances (~40 total) |
| `/intensity-tiers/` | GET | List intensity tiers (6 total) |
| `/gifts/` | GET | List all gifts |
| `/gifts/{id}/` | GET | Gift detail with nested powers |
| `/powers/` | GET | List all powers |
| `/anima-ritual-types/` | GET | List ritual types |
| `/thread-types/` | GET | List thread types |

### Character Data (Filtered to owned characters)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/character-auras/` | GET/POST | Character aura data |
| `/character-resonances/` | GET/POST/PATCH/DELETE | Character resonances |
| `/character-gifts/` | GET/POST/DELETE | Character's acquired gifts |
| `/character-powers/` | GET/POST/PATCH | Character's unlocked powers |
| `/character-anima/` | GET/POST/PATCH | Character anima pool |
| `/character-anima-rituals/` | GET/POST/PATCH/DELETE | Character's rituals |

### Threads

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/threads/` | GET/POST | Character threads (list shows lightweight serializer) |
| `/threads/{id}/` | GET/PATCH | Thread detail with matching types and resonances |
| `/thread-journals/` | GET/POST | Journal entries on threads |
| `/thread-resonances/` | GET/POST/DELETE | Resonances on threads |

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
    "intensity": calculated_intensity,
})
```

---

## Notes

- **No services.py yet** - Most logic is in model methods or will be added as service functions when combat/gameplay is implemented
- **Aura validation** - CharacterAura enforces percentages sum to 100 via `clean()`
- **Thread uniqueness** - Only one thread per character pair (unique_together on initiator/receiver)
- **SharedMemoryModel** - Lookup tables use Evennia's caching for performance
