# Character Sheets System

Character identity, appearance, demographics, and the CharacterIdentity link to the Persona system.

**Source:** `src/world/character_sheets/`

---

## Enums (types.py)

```python
from world.character_sheets.types import MaritalStatus
# Values: SINGLE, MARRIED, WIDOWED, DIVORCED

from world.character_sheets.types import Gender as GenderChoices
# Values: MALE, FEMALE, NON_BINARY, OTHER
# Note: This TextChoices enum is separate from the Gender model below.
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Heritage` | Origin story types (Sleeper, Misbegotten, Normal) | `name`, `description`, `is_special`, `family_known`, `family_display` |
| `Gender` | Canonical gender identities | `key`, `display_name`, `is_default` |
| `Pronouns` | Canonical pronoun sets (decoupled from gender) | `key`, `display_name`, `subject`, `object`, `possessive`, `is_default` |
| `Characteristic` | Physical trait types (eye_color, hair_color, etc.) | `name`, `display_name`, `description`, `is_active`, `required_for_races` |
| `CharacteristicValue` | Specific values per trait type (blue, green, brown) | `characteristic` (FK), `value`, `display_value`, `is_active`, `allowed_for_species` (M2M) |

### Character Data (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterSheet` | Primary character demographics and identity | `character` (OneToOne to ObjectDB), `age`, `real_age`, `gender`, `pronouns`, pronoun fields, `heritage`, `origin_realm`, `species`, `concept`, `family`, `tarot_card`, `tarot_reversed`, `social_rank`, `marital_status`, description text fields |
| `CharacterSheetValue` | Links characters to characteristic values | `character_sheet` (FK), `characteristic_value` (FK) |
| `CharacterIdentity` | Links character to their active Persona | `character` (OneToOne to ObjectDB), `active_persona` (FK to `scenes.Persona`) |

---

## Key Methods

### CharacterSheet

```python
from world.character_sheets.models import CharacterSheet

# Access via OneToOne from character
sheet = character.sheet_data
sheet.age           # 25
sheet.concept       # "Disgraced knight seeking redemption"
sheet.gender        # Gender model instance
sheet.species       # Species model instance
sheet.family        # Family model instance (nullable)
```

### CharacterIdentity

```python
from world.character_sheets.models import CharacterIdentity

# Get identity for a character (OneToOne)
identity = character.character_identity

# Get active persona
persona = identity.active_persona

# All personas for this identity
identity.personas.all()
```

### CharacterSheetValue

```python
from world.character_sheets.models import CharacterSheetValue

# Get character's characteristics
CharacterSheetValue.objects.filter(character_sheet=sheet)

# Validation: one value per characteristic type per character
# Raises ValidationError if character already has eye_color set
csv = CharacterSheetValue(character_sheet=sheet, characteristic_value=blue_eyes)
csv.save()  # Runs full_clean() automatically
```

### CharacteristicValue

```python
from world.character_sheets.models import CharacteristicValue

# Get all values for a characteristic type
CharacteristicValue.objects.filter(characteristic__name="eye_color", is_active=True)

# Species-restricted values (empty M2M = available to all)
CharacteristicValue.objects.filter(allowed_for_species=species)
```

---

## Persona System

Personas allow characters to appear differently in scenes through disguises, transformations, or alternate identities. The Persona model lives in the `scenes` app; CharacterIdentity in this app bridges characters to personas.

- **Primary persona** (`persona_type=PRIMARY`): The character's true identity. One per CharacterIdentity (enforced by unique constraint).
- **Established persona** (`persona_type=ESTABLISHED`): A persistent alter ego that can join organizations and build reputation.
- **Temporary persona** (`persona_type=TEMPORARY`): A disposable disguise that cannot join organizations or build reputation.
- `is_established_or_primary` property on Persona controls permission checks.
- Unique constraint on `(character_identity, name)` prevents duplicate persona names.

---

## Integration Points

- **Societies**: Personas are the identity layer for organization memberships, reputation, and legend
- **Character Creation**: `CharacterSheet` fields are populated during `finalize_character()`
- **Roster**: `CharacterSheet.family` links to `roster.Family`
- **Species**: `CharacterSheet.species` and `CharacteristicValue.allowed_for_species`
- **Tarot**: `CharacterSheet.tarot_card` for familyless character surnames
- **Forms**: `CharacterSheet.build` links to `forms.Build` for body type
- **Realms**: `CharacterSheet.origin_realm` links to `realms.Realm`
- **Scenes**: `CharacterIdentity` bridges characters to the Persona system in `scenes` app

---

## Admin

Models registered in Django admin (Heritage is not registered):

- `GenderAdmin` / `PronounsAdmin` - Lookup table management
- `CharacterSheetAdmin` - Full editing with fieldsets for identity, social, descriptions; `CharacterSheetValueInline` for characteristics
- `CharacterIdentityAdmin` - Identity management with active persona display
- `CharacteristicAdmin` - With `CharacteristicValueInline` for values
- `CharacteristicValueAdmin` - Value management with characteristic filter
