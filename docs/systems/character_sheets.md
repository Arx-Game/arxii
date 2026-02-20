# Character Sheets System

Character identity, appearance, demographics, and the guise (disguise/alias) system.

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
| `Guise` | Contextual appearance for scenes/disguises | `character` (FK to ObjectDB), `name`, `colored_name`, `description`, `thumbnail`, `is_default`, `is_persistent` |

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

### Guise

```python
from world.character_sheets.models import Guise

# Get all guises for a character
Guise.objects.filter(character=character)

# Get default guise
Guise.objects.get(character=character, is_default=True)

# Only one default per character (enforced in save())
guise.is_default = True
guise.save()  # Automatically clears is_default on other guises

# Persistent aliases can join orgs; temporary disguises cannot
guise.is_persistent  # True = established alias, False = temporary
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

## Guise System

Guises allow characters to appear differently in scenes through disguises, transformations, or alternate identities.

- **Default guise** (`is_default=True`): The character's true appearance. One per character (enforced on save).
- **Persistent guise** (`is_persistent=True`): An established alias that can join organizations and build reputation.
- **Temporary guise** (both False): A disposable disguise that cannot join organizations or build reputation.
- Characters have a `unique_together` constraint on `(character, name)` to prevent duplicate guise names.

---

## Integration Points

- **Societies**: Guises are the identity layer for organization memberships, reputation, and legend
- **Character Creation**: `CharacterSheet` fields are populated during `finalize_character()`
- **Roster**: `CharacterSheet.family` links to `roster.Family`
- **Species**: `CharacterSheet.species` and `CharacteristicValue.allowed_for_species`
- **Tarot**: `CharacterSheet.tarot_card` for familyless character surnames
- **Forms**: `CharacterSheet.build` links to `forms.Build` for body type
- **Realms**: `CharacterSheet.origin_realm` links to `realms.Realm`

---

## Admin

All models registered in Django admin:

- `GenderAdmin` / `PronounsAdmin` - Lookup table management
- `CharacterSheetAdmin` - Full editing with fieldsets for identity, social, descriptions; `CharacterSheetValueInline` for characteristics
- `GuiseAdmin` - Guise management with default filter
- `CharacteristicAdmin` - With `CharacteristicValueInline` for values
- `CharacteristicValueAdmin` - Value management with characteristic filter
