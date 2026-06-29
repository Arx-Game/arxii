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
| `FormCombatProfile` | Battle-form stat-suite (alt-self modifiers) | `form` (FK CharacterForm), `display_name`, `depth` (band-selection axis; crit→highest, mid→middle, fail→lowest) |
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
switch_form(character, target_form)  # Raises FormOwnershipError if wrong character

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
active = assume_alternate_self(sheet, alt_self)  # Raises AlternateSelfActiveError if
                                                 # a different alt-self is active;
                                                 # FormOwnershipError / ActivePersonaError
                                                 # on a cross-sheet form/persona FK.
revert_alternate_self(sheet)                     # Raises RevertBlockedError while not
                                                 # in_control; ValueError if none active.
```

### Alternate-self services

- `assume_alternate_self(sheet, alt)` — assume an `AlternateSelf` grant. Swaps form
  and/or persona, creates one `ModifierSource` + `CharacterModifier` rows per profile
  effect and `CharacterTechnique` rows per technique, and stores return anchors. Not
  gated by `in_control`. **Strictly-one-active**: raises `AlternateSelfActiveError`
  if a *different* alt-self is already active (assumption over an active one would
  orphan its grants with no revert path) — revert the active one first. The same call
  raises `FormOwnershipError` / `ActivePersonaError` (both `ValueError` subclasses)
  if the alt-self's `form` or `persona` FK points at another sheet (bad seed/admin
  edit — neither FK has a cross-sheet DB guard).
- `revert_alternate_self(sheet)` — restore return anchors and delete the granted
  modifier / technique rows. Blocked while `not sheet.in_control`; raises
  `RevertBlockedError`. The canonical blocker is the fury `Berserk` condition,
  whose `Control` category has `alters_behavior=True`; it is cleared by the existing
  `RestoreSenseAction` (`restore_sense`) calm-down action.
- `trigger_transformation(sheet, alt, *, cause, instance_value=1.0)` (in
  `world/forms/services/transformation.py`) — the single seam both non-command
  cause-paths call. Wraps `assume_alternate_self(sheet, alt, instance_value=...)`;
  `cause` is an audit tag (`"technique"` | `"trigger"` | `"command"`) and
  `instance_value` is the per-instance multiplier (default `1.0` = no scaling).
  Scales each granted `CharacterModifier.value` by `alt.tuning_value` (the
  per-character baseline; `None`/`1` = neutral) and `instance_value`, divided by
  `SCALE = 10`. The **neutral case** (`tuning_value` is `None`/`1` AND
  `instance_value == 1.0`) short-circuits to the raw `effect.value` — a
  regression guard so existing grants are unchanged. This is how two characters
  sharing a form-template get differently-tuned stat-suites (#1604), and how a
  strong cast / violent onset scales a single assumption.
- `RevertBlockedError(user_message=...)` — the exception surfaced when revert is
  blocked.
- `AlternateSelfActiveError(user_message=...)` — raised when a different alt-self is
  already active (strictly-one-active).
- `FormOwnershipError(user_message=...)` — raised by `switch_form` on a cross-sheet
  `CharacterForm` FK; surfaced as a safe failure by the actions.

### Alternate-self actions

Both verbs are thin REGISTRY actions in `actions/definitions/forms.py` so telnet
and the web share the same `action.run()` path:

- `ShiftFormAction` (key `"shift_form"`) — wraps `assume_alternate_self`. Receives
  kwarg `alternate_self_id`; validates the grant belongs to the actor's sheet.
  **Not `in_control`-gated**. Gated instead by `HoldsCapabilityPrerequisite`:
  only characters holding the seeded `at_will_shifting` capability (effective
  value `>= 1`) may shift at will — a niche escape hatch for characters who can
  shift between forms freely without casting. Everyone else is refused by the
  prerequisite with a clean failure result (never an exception). Catches
  `AlternateSelfActiveError`, `ActivePersonaError`, and `FormOwnershipError`
  and surfaces each `user_message` as a failure result — a cross-sheet
  `form`/`persona` FK never propagates uncaught (`Action.run` calls `execute`
  bare, so an uncaught exception would 500 on web).
- `RevertFormAction` (key `"revert_form"`) — wraps `revert_alternate_self`.
  Catches `RevertBlockedError`, `ActivePersonaError`, `FormOwnershipError`, and
  `AlternateSelfActiveError` (each → `exc.user_message`); the no-active case uses a
  safe constant. Never surfaces `str(exc)` — the viewset maps every failure to a
  safe 400 via `detail.message`.

### Transformation cause-paths (#1604)

Transformation is normally driven by a technique cast or an involuntary trigger,
not by the at-will command above. All three paths converge on the
`trigger_transformation` seam (and thus on `assume_alternate_self`):

1. **Technique (primary).** A weave/technique carries an `EffectKind.ASSUME_ALTERNATE_SELF`
   pull effect (in `world/magic/models/threads.py`), whose `target_form` FK names
   which `CharacterForm` to assume. At cast resolution (`use_technique` in
   `world/magic/services/techniques.py`), the success band selects a
   `FormCombatProfile` by `depth` (fail → lowest, ordinary success → middle, crit
   → highest) and scales the suite via `instance_value` (fail → `1.0`,
   mid → `1.5`, crit → `2.0`), then calls `trigger_transformation(..., cause="technique")`.
   The selected `AlternateSelf` grant must already exist for
   `(sheet, form, combat_profile)`; a missing grant is a silent no-op with a
   logged warning.
2. **Involuntary trigger (primary).** A reactive condition (e.g. lycanthropy rage)
   fires `CONDITION_APPLIED` → a `TriggerDefinition` launches a flow → a
   `CALL_SERVICE_FUNCTION` step invokes `flow_trigger_transformation` (registered
   in `flows/service_functions/forms.py`). The wrapper resolves the
   `AlternateSelf` by `(sheet, form__name)` — the trigger author picks the form —
   and calls `trigger_transformation(..., cause="trigger")`. A resist-check branch
   (`flow_perform_check` → `EVALUATE_EQUALS` on the failure outcome) authors the
   "fail a check to *not* change" journey: the shift is forced only when the
   resist fails. While the rage is active `sheet.in_control` is `False`, so
   `revert_alternate_self` raises `RevertBlockedError`; clearing the condition
   re-derives `in_control=True` and unblocks a later self-revert.
3. **At-will command (niche).** `ShiftFormAction` above — only for characters with
   the `at_will_shifting` capability.

The gift-level modulation of the resist check (minor-gift level easing/hardening
the resist) is deferred to #1578 (the specialization engine).

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
