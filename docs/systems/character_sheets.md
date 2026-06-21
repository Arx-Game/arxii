# Character Sheets — Source of Truth

CharacterSheet is the single anchor for all character-related data.

**Source:** `src/world/character_sheets/`

---

## The Model

`CharacterSheet` is OneToOne to ObjectDB (`primary_key=True` — shares pk), holding demographics/appearance fields. Every playable character has one.

The **narrative bio** (concept, real_concept, quote, personality, background, obituary) was sliced out into a separate **`Profile`** model (#1270) so a cover identity can present its own bio. The sheet owns one `true_profile` (its real bio), and the PRIMARY persona points at it. `CharacterSheet` keeps read/write forwarding properties (`sheet.concept` → `true_profile.concept`, with a `save()` cascade), so existing reads/writes are unchanged — bio just lives on the profile now. **Cover-bio display is wired** (#1270 slice 2): the profile serializer reads concept/quote/story from the *presented* persona's profile (`_presented_bio_profile`) — the real `true_profile` when revealed, a cover persona's own authored profile when presenting one, else blank (never the real bio for a non-revealed face). Lineage FKs (family/heritage/tarot/origin) and the cover-bio *authoring* form are the remaining follow-up slices.

## Privacy Tiers (#1271)

Each mechanical sheet section carries a player-controlled visibility tier
(`SheetVisibility`: `SELF` / `FRIENDS` / `PUBLIC`) — `stats_visibility`, `skills_visibility`,
`magic_visibility`, `goals_visibility` on `CharacterSheet`, defaulting to `SELF` (the #1109
"private by default" behaviour). The profile serializer resolves the viewer's openness once
(`_viewer_access_level`: staff/owner = SELF, on the owner's `PlayerAllowList` = FRIENDS, else
PUBLIC) and shows each section when access meets its tier (`SHEET_VISIBILITY_RANK`). The FRIENDS
allow-list lookup runs only when a section is actually FRIENDS-gated, so the all-default case adds
no query. Bio/story tiers (entangled with the presented-identity gating) and the player-facing
tier-setting UI are follow-ups.

## Related Models

All character-related models FK back to CharacterSheet:

- **`Profile`** (#1270) — the narrative bio surface a persona presents. `CharacterSheet.true_profile` (OneToOne) is the real bio; `Persona.profile` (FK) is the bio that face presents (PRIMARY → the sheet's `true_profile`; a cover persona may own its own). Null `Persona.profile` falls back to the sheet's `true_profile`.
- **`Persona`** (scenes) — IC identity of a character. FK via `character_sheet`. A character can have multiple personas (PRIMARY, ESTABLISHED, TEMPORARY). The unique PRIMARY persona per sheet is accessed via `sheet.primary_persona`.
- **`RosterEntry`** (roster) — tracks which character is being played and by whom. OneToOne to CharacterSheet.
- **`CharacterVitals`** (vitals) — health/status tracking. OneToOne to CharacterSheet.
- Mechanical systems (combat, magic, achievements, etc.) — FK to CharacterSheet.

## Primary Persona Invariant

Every CharacterSheet should have exactly one Persona with `persona_type=PRIMARY`. This is enforced by a partial unique constraint. The `primary_persona` cached property on CharacterSheet fetches it. If no PRIMARY exists, it raises `Persona.DoesNotExist` — intentionally loud, not a silent None.

## Character Creation

Use `world.character_sheets.services.create_character_with_sheet()` to create a playable character. It atomically creates the Character typeclass, CharacterSheet, and PRIMARY Persona in a single transaction. This is the blessed creation path — factories and the character_creation app both use it.

## Display Helpers

Three display tiers for character identity, primary implementations on Persona:

- **`display_ic()`** — Just the persona name. What IC observers see.
- **`display_with_history()`** — Adds tenure disambiguation (e.g., "Bob (Thomas #2)") when there's ambiguity; collapses redundancy when persona name matches character name.
- **`display_to_staff()`** — Full staff context including account: "Bob (Thomas #2, played by Fred)".

CharacterSheet has thin delegates that call `primary_persona.display_*()`:

```python
sheet.display_to_staff()                # uses primary persona
persona.display_to_staff()              # uses that specific persona
membership.persona.display_to_staff()   # context-pinned persona (e.g., GM table)
```

When a caller has a specific persona (membership, event enrollment, etc.), call display helpers directly on the persona. When you have only a sheet, use the delegates.

## Why Not CharacterIdentity?

`CharacterIdentity` existed historically as a separate model and was deleted in the 2026-04 refactor. Its only unique contribution was `active_persona` — which is now derived from `persona_type=PRIMARY`. Having two OneToOne peers (CharacterSheet + CharacterIdentity) hanging off the same ObjectDB was confusing to agents reading the code.

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

## Lookup Tables (SharedMemoryModel - cached, rarely change)

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `Heritage` | Origin story types (Sleeper, Misbegotten, Normal) | `name`, `description`, `is_special`, `family_known`, `family_display` |
| `Gender` | Canonical gender identities | `key`, `display_name`, `is_default` |
| `Pronouns` | Canonical pronoun sets (decoupled from gender) | `key`, `display_name`, `subject`, `object`, `possessive`, `is_default` |
| `Characteristic` | Physical trait types (eye_color, hair_color, etc.) | `name`, `display_name`, `description`, `is_active`, `required_for_races` |
| `CharacteristicValue` | Specific values per trait type (blue, green, brown) | `characteristic` (FK), `value`, `display_value`, `is_active`, `allowed_for_species` (M2M) |

## Character Data

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `CharacterSheet` | Primary character demographics, identity, and source-of-truth anchor | `character` (OneToOne to ObjectDB, primary_key), `age`, `real_age`, `gender`, `pronouns`, pronoun fields, `heritage`, `origin_realm`, `species`, `family`, `tarot_card`, `tarot_reversed`, `social_rank`, `marital_status`, `additional_desc`, `true_profile` (OneToOne → Profile). Narrative bio (`concept`/`quote`/`background`/…) is read/written through forwarding properties → `true_profile` (#1270). |
| `Profile` | The narrative bio a persona presents (#1270) | `concept`, `real_concept`, `quote`, `personality`, `background`, `obituary`. Referenced by `CharacterSheet.true_profile` and `Persona.profile`. |
| `CharacterSheetValue` | Links characters to characteristic values | `character_sheet` (FK), `characteristic_value` (FK) |

---

## Integration Points

- **Societies**: Personas are the identity layer for organization memberships, reputation, and legend
- **Character Creation**: `CharacterSheet` fields are populated during `finalize_character()`; use `create_character_with_sheet()` as the blessed creation path
- **Roster**: `RosterEntry` is OneToOne to CharacterSheet; `CharacterSheet.family` links to `roster.Family`
- **Species**: `CharacterSheet.species` and `CharacteristicValue.allowed_for_species`
- **Tarot**: `CharacterSheet.tarot_card` for familyless character surnames
- **Forms**: `CharacterSheet.build` links to `forms.Build` for body type
- **Realms**: `CharacterSheet.origin_realm` links to `realms.Realm`
- **Scenes**: `Persona.character_sheet` FK links sheets to their personas; `sheet.primary_persona` accesses the PRIMARY
- **Vitals**: `CharacterVitals` is OneToOne to CharacterSheet
