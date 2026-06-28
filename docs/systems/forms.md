# Forms System

Physical appearance options (height, build, hair/eye colors) with true form, alternate form, disguise, and temporary override support.

**Source:** `src/world/forms/`
**API Base:** `/api/forms/`

---

## Enums (models.py)

```python
from world.forms.models import (
    TraitType,     # COLOR, STYLE - categorizes form traits
    FormType,      # TRUE, ALTERNATE, DISGUISE - type of saved character form
    SourceType,    # EQUIPPED_ITEM, APPLIED_ITEM, SPELL, SYSTEM - source of temporary changes
    DurationType,  # UNTIL_REMOVED, REAL_TIME, GAME_TIME, SCENE - how temporary changes expire
)
```

---

## Models

### Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `HeightBand` | Height ranges mapping to descriptive bands | `name`, `display_name`, `min_inches`, `max_inches`, `weight_min`, `weight_max`, `is_cg_selectable`, `hide_build`, `sort_order` |
| `Build` | Body type with weight calculation factor | `name`, `display_name`, `weight_factor` (Decimal), `is_cg_selectable`, `sort_order` |
| `FormTrait` | Physical characteristic type (e.g., hair_color) | `name`, `display_name`, `trait_type` (TraitType), `sort_order` |
| `FormTraitOption` | Valid value for a trait (e.g., "black" for hair_color) | `trait` (FK), `name`, `display_name`, `height_modifier_inches` (nullable), `sort_order` |
| `SpeciesFormTrait` | Links species to available traits/options in CG | `species` (FK), `trait` (FK), `is_available_in_cg`, `allowed_options` (M2M, empty = all) |

### Character Data (models.Model - per-character instances)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterForm` | A saved set of form trait values | `character` (FK ObjectDB), `name`, `form_type` (FormType), `is_player_created`, `created_at` |
| `CharacterFormValue` | Single trait value within a form | `form` (FK), `trait` (FK), `option` (FK) |
| `CharacterFormState` | Tracks active form (OneToOne per character) | `character` (OneToOne ObjectDB), `active_form` (FK CharacterForm, nullable) |
| `TemporaryFormChange` | Temporary override on top of active form | `character` (FK), `trait` (FK), `option` (FK), `source_type`, `source_id`, `duration_type`, `expires_at`, `expires_after_scenes` |
| `FormCombatProfile` | Battle-form stat-suite (alt-self modifiers) | `form` (FK CharacterForm), `display_name` |
| `FormCombatProfileEffect` | One stat modifier inside a profile | `profile` (FK), `target` (FK mechanics.ModifierTarget), `value` |
| `AlternateSelf` | A character's access to an alternate self/facet bundle | `character` (FK CharacterSheet), `form` (FK CharacterForm, nullable), `persona` (FK scenes.Persona, nullable), `combat_profile` (FK FormCombatProfile, nullable), `techniques` (M2M magic.Technique), `tuning_value`, `display_name` |
| `ActiveAlternateSelf` | Currently-assumed alternate self + return anchors | `character` (OneToOne CharacterSheet), `alternate_self` (FK AlternateSelf, nullable), `return_form` (FK CharacterForm, nullable), `return_persona` (FK scenes.Persona, nullable) |

---

## Key Methods

### HeightBand

```python
from world.forms.models import HeightBand

# Get midpoint of a band's range
band.midpoint  # (min_inches + max_inches) // 2
```

### SpeciesFormTrait

```python
from world.forms.models import SpeciesFormTrait

# Get available options (respects allowed_options filter)
species_trait.get_available_options()
# Returns allowed_options if set, otherwise all options for the trait
```

### TemporaryFormChange

```python
from world.forms.models import TemporaryFormChange

# Query active (non-expired) temporary changes
TemporaryFormChange.objects.active()

# Check if a specific change has expired
change.is_expired()  # Checks real-time expiry; game_time/scene require external tracking
```

### Service Functions

```python
from world.forms.services import (
    get_apparent_form,
    switch_form,
    revert_to_true_form,
    get_cg_form_options,
    create_true_form,
    get_height_band,
    calculate_weight,
    get_apparent_height,
    get_apparent_build,
    get_cg_height_bands,
    get_cg_builds,
)

# Get apparent form (base + temporary overrides)
apparent = get_apparent_form(character)
# Returns: dict[FormTrait, FormTraitOption]

# Switch a character to a different form
switch_form(character, target_form)  # Raises ValueError if wrong character

# Revert to true form
revert_to_true_form(character)

# Get CG options for a species (respects SpeciesFormTrait restrictions)
options = get_cg_form_options(species)
# Returns: dict[FormTrait, list[FormTraitOption]]

# Create true form during character creation
form = create_true_form(character, {hair_trait: black_option, eye_trait: blue_option})
# Raises ValueError if true form already exists

# Height/build calculations
band = get_height_band(70)  # Returns HeightBand or None
weight = calculate_weight(70, build)  # height * factor, clamped by band bounds
apparent_height, band = get_apparent_height(character)  # Includes trait modifiers
apparent_build = get_apparent_build(character)  # None if band.hide_build

# CG-selectable queries
bands = get_cg_height_bands()  # HeightBand.objects.filter(is_cg_selectable=True)
builds = get_cg_builds()       # Build.objects.filter(is_cg_selectable=True)

# Alternate-self lifecycle (slice 4)
active = assume_alternate_self(sheet, alt_self)  # Raises on wrong-character form
revert_alternate_self(sheet)                     # Raises RevertBlockedError
```

### Alternate-self services

- `assume_alternate_self(sheet, alt)` — assume an `AlternateSelf` grant. Swaps form
  and/or persona, creates one `ModifierSource` + `CharacterModifier` rows per profile
  effect and `CharacterTechnique` rows per technique, and stores return anchors. Not
  gated by `in_control`.
- `revert_alternate_self(sheet)` — restore return anchors and delete the granted
  modifier / technique rows. Blocked while `not sheet.in_control`; raises
  `RevertBlockedError`. The canonical blocker is the fury `Berserk` condition,
  whose `Control` category has `alters_behavior=True`; it is cleared by the existing
  `RestoreSenseAction` (`restore_sense`) calm-down action.
- `RevertBlockedError(user_message=...)` — the exception surfaced when revert is
  blocked.

### Alternate-self actions

Both verbs are thin REGISTRY actions in `actions/definitions/forms.py` so telnet
and the web share the same `action.run()` path:

- `ShiftFormAction` (key `"shift_form"`) — wraps `assume_alternate_self`. Receives
  kwarg `alternate_self_id`; validates the grant belongs to the actor's sheet.
  **Not `in_control`-gated**.
- `RevertFormAction` (key `"revert_form"`) — wraps `revert_alternate_self`.
  Catches `RevertBlockedError` and surfaces `exc.user_message` as a failure result.

### Web surface

`frontend/src/game/components/FormSwitcher.tsx` mirrors `PersonaSwitcher.tsx`: a
 top-bar control next to the face switcher that shows the active alternate self (or
"True self") and lets the player shift or revert. `frontend/src/game/formQueries.ts`
holds the React Query hooks (`useAlternateSelvesQuery`, `useShiftFormMutation`,
`useRevertFormMutation`) that hit the endpoints above. Revert errors from the action
(e.g. "You can't revert while not in control of yourself.") are surfaced inline.

### Telnet surface

- `form` / `form list` — status hub: shows current alternate self (or true self),
  available alternate selves, and whether revert is blocked while not in control.
- `form shift <name|id>` — assume a named alternate self.
- `form revert` — revert to the true self.

Implemented in `commands/form.py` as `CmdForm`; routes through
`dispatch_player_action` to the same REGISTRY actions the web uses.

The decoupling of control from the shift and the stacking guard are documented in
[`appearance_and_identity.md`](appearance_and_identity.md).

---

## API Endpoints

### Form Traits
- `GET /api/forms/traits/` - List all form trait definitions with nested options
- `GET /api/forms/traits/{id}/` - Get single trait with options

### Character Forms
- `GET /api/forms/character-forms/` - List forms for current user's characters
- `GET /api/forms/character-forms/{id}/` - Get single form with values
- `GET /api/forms/character-forms/apparent/` - Get apparent form for active character (base + temporaries)

### Height Bands
- `GET /api/forms/height-bands/` - List CG-selectable height bands (all for staff)
- `GET /api/forms/height-bands/{id}/` - Get single height band

### Builds
- `GET /api/forms/builds/` - List CG-selectable builds (all for staff)
- `GET /api/forms/builds/{id}/` - Get single build

### Alternate Selves
- `GET /api/forms/alternate-selves/` - List the played character's alternate selves
  (`character_sheet` filter required at the API level; the viewset scopes results to the
  caller's played character). Response is paginated; each entry carries `id`,
  `display_name`, `persona_name`, `form_name`, `has_combat_profile`, `has_techniques`,
  and `is_active`.
- `GET /api/forms/alternate-selves/{id}/` - Get a single alternate self (caller-owned
  via the viewset queryset scoping).
- `POST /api/forms/alternate-selves/shift/` - Assume an alternate self; body is
  `{"alternate_self_id": <id>}`. Dispatches `ShiftFormAction` (key `"shift_form"`)
  through `dispatch_player_action` → `action.run()`. A foreign/unknown id returns 400
  with a uniform safe message (no repertoire leak).
- `POST /api/forms/alternate-selves/revert/` - Revert the active alternate self.
  Dispatches `RevertFormAction` (key `"revert_form"`) through the same action seam.
  Returns 400 with `RevertBlockedError.user_message` while `not in_control` (rage,
  possession, charm, mind-control).

All endpoints require `IsAuthenticated`.

---

## Integration Points

- **Species System** (`world.species`): `SpeciesFormTrait` links species to available traits/options, controlling what appears in CG.
- **Character Sheets** (`world.character_sheets`): `CharacterSheet.true_height_inches` and `CharacterSheet.build` provide base values for apparent height/build calculations.

---

## Admin

All models registered with appropriate filters, search, and inline editing:

- **`HeightBandAdmin`** - List-editable sort order, CG selectability, and hide_build flag.
- **`BuildAdmin`** - List-editable weight factor and CG selectability.
- **`FormTraitAdmin`** - Inline `FormTraitOptionInline` for managing options.
- **`FormTraitOptionAdmin`** - Custom changelist template with grouped display by trait. List-editable height modifier.
- **`SpeciesFormTraitAdmin`** - Custom form that filters `allowed_options` to only show options matching the selected trait. Uses `filter_horizontal` for option selection.
- **`CharacterFormAdmin`** - Inline `CharacterFormValueInline` with autocomplete fields.
- **`CharacterFormStateAdmin`** - Simple list of character-to-active-form mappings.
- **`TemporaryFormChangeAdmin`** - Filtered by source type and duration type.
