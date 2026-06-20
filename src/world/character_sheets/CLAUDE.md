# Character Sheets - Source of Truth

**CharacterSheet is the single source-of-truth anchor for all character-related data.** Every playable character has one CharacterSheet (OneToOne to ObjectDB, `primary_key=True`, sharing pk with the character). All related models — `Persona`, `RosterEntry`, `CharacterVitals`, and mechanical systems — FK back to CharacterSheet.

## Key Files

### `models.py`
- **`CharacterSheet`**: Primary character data (age, gender, demographics, appearance). Anchor for character-related FKs. Has `primary_persona` cached property and thin `display_*` delegates that call through to the primary persona.
- **`Profile`** (#1270): the narrative bio (concept, real_concept, quote, personality, background, obituary), sliced out of CharacterSheet so a cover identity can present its own bio. `CharacterSheet.true_profile` (OneToOne) is the real bio; `Persona.profile` (FK) is what a face presents. `sheet.concept` etc. are forwarding read/write properties → `true_profile` (with a `save()` cascade), so existing access is unchanged. **Set bio via the sheet properties or the profile directly — they're no longer CharacterSheet columns.**
- **`Heritage`**: Origin story types (Sleeper, Misbegotten, Normal) - SharedMemoryModel
- **`Gender`** / **`Pronouns`**: Canonical lookup tables - SharedMemoryModel

**Appearance is NOT here.** Skin/eye/hair (and other physical traits) live in the
`forms` app (`FormTrait`/`FormTraitOption`/`CharacterForm`), with per-persona flavor
in `forms.PersonaTraitDescriptor`. Read the composed result via
`forms.services.get_presented_appearance` (the single source for telnet `item_data`
and the web serializer). The legacy `Characteristic`/`CharacteristicValue`/
`CharacterSheetValue` models were retired in favour of that (#1119).

### `services.py`
- **`create_character_with_sheet()`**: The blessed character creation path. Atomically creates the Character typeclass, CharacterSheet, and PRIMARY Persona in a single transaction. Factories and the character_creation app both use this.

### `types.py`
- Type definitions and TextChoices enums (MaritalStatus, Gender choices, etc.)

## Primary Persona Invariant

Every CharacterSheet should have exactly one `Persona` with `persona_type=PRIMARY`, enforced by a partial unique constraint. Access via `sheet.primary_persona` (cached property). If no PRIMARY exists, it raises `Persona.DoesNotExist` — intentionally loud, not a silent None.

## Display Helpers

Three display tiers live on `Persona` (`display_ic`, `display_with_history`, `display_to_staff`). CharacterSheet has thin delegates that call through to `primary_persona`:

```python
sheet.display_to_staff()                # uses primary persona
persona.display_to_staff()              # uses that specific persona
membership.persona.display_to_staff()   # context-pinned persona (e.g., GM table)
```

When a caller has a specific persona (membership, event enrollment), call directly on the persona. When you have only a sheet, use the delegate.

## Item Data Integration

Character data accessed through the unified item_data system:

```python
character.item_data.age        # Routes to CharacterSheet
character.item_data.sheet      # Direct CharacterSheet access
```

## Integration Points

- **Scenes**: `Persona.character_sheet` FK; `sheet.primary_persona` accesses PRIMARY
- **Roster**: `RosterEntry` is OneToOne to CharacterSheet
- **Vitals**: `CharacterVitals` is OneToOne to CharacterSheet
- **Evennia Extensions**: item_data system for unified access
- **Species / Forms / Realms**: FK fields on CharacterSheet
- **Character Creation**: Populates sheet fields via `finalize_character()`, using `create_character_with_sheet()` as the creation entry point
