# Persona Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collapse Guise and old Persona into a single Persona model with PersonaType
(PRIMARY/ESTABLISHED/TEMPORARY), simplify CharacterIdentity to one FK, add
PersonaDiscovery, and update all references across the codebase.

**Architecture:** The new Persona model absorbs all Guise fields plus identity-type
semantics. CharacterIdentity simplifies to `character` + `active_persona`. PersonaDiscovery
stores discovery pairs. All FK references to Guise across societies, legend, skills,
scenes, and interactions are updated to point to the new Persona. Since there is no
production data, we delete all affected migrations and regenerate from scratch.

**Tech Stack:** Django/DRF, SharedMemoryModel, PostgreSQL, FactoryBoy

**Design doc:** `docs/plans/2026-03-22-persona-simplification-design.md`

**Key conventions:**
- SharedMemoryModel for all models
- Type annotations on all functions in typed apps
- Absolute imports only, TextChoices in constants.py
- No queries in loops, Prefetch with to_attr
- Run tests: `echo "yes" | arx test <app>`
- Full suite: `uv run arx test`
- Run lint: `ruff check <file>`

---

## Task 1: Add PersonaType Constant

**Files:**
- Modify: `src/world/scenes/constants.py`

Add PersonaType TextChoices:

```python
class PersonaType(TextChoices):
    """The permanence level of a persona."""
    PRIMARY = "primary", "Primary"
    ESTABLISHED = "established", "Established"
    TEMPORARY = "temporary", "Temporary"
```

Commit: `feat(scenes): add PersonaType constant`

---

## Task 2: Create New Persona Model

**Files:**
- Modify: `src/world/scenes/models.py`

Replace the existing Persona model entirely. The new Persona absorbs Guise fields and
adds PersonaType. Key changes from old Persona:

- Remove `participation` FK (dropped per design)
- Remove `guise` FK (Persona IS the identity now)
- Add `character_identity` FK to CharacterIdentity (non-nullable)
- Add `persona_type` CharField with PersonaType choices
- Add Guise fields: `colored_name`, `thumbnail` FK, `updated_at`
- Keep: `character` FK, `name`, `is_fake_name`, `description`, `thumbnail_url`, `created_at`
- Add constraints: unique primary per character_identity, primary must not have is_fake_name

```python
class Persona(SharedMemoryModel):
    """A face the character shows the world.

    Replaces both the old Guise and old Persona models. Every character has at
    least one primary persona (their 'real' identity). Additional established
    personas are persistent alter egos. Temporary personas are throwaway disguises.
    """

    character_identity = models.ForeignKey(
        "character_sheets.CharacterIdentity",
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The real character behind this persona",
    )
    character = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The character object (denormalized from character_identity for queries)",
    )
    name = models.CharField(max_length=255, help_text="Display name for this persona")
    colored_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name with color formatting codes",
    )
    description = models.TextField(blank=True, help_text="Physical description text")
    thumbnail_url = models.URLField(blank=True, max_length=500)
    thumbnail = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persona_thumbnails",
        help_text="Visual representation",
    )
    persona_type = models.CharField(
        max_length=20,
        choices=PersonaType.choices,
        default=PersonaType.TEMPORARY,
        help_text="PRIMARY = real identity, ESTABLISHED = persistent alter ego, "
        "TEMPORARY = throwaway disguise",
    )
    is_fake_name = models.BooleanField(
        default=False,
        help_text="True when this persona obscures the character's identity",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_identity"],
                condition=models.Q(persona_type="primary"),
                name="unique_primary_persona",
            ),
            models.UniqueConstraint(
                fields=["character_identity", "name"],
                name="unique_persona_name_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_persona_type_display()})"

    @property
    def is_established_or_primary(self) -> bool:
        """Whether this persona can have relationships, reputation, legend."""
        return self.persona_type in (PersonaType.PRIMARY, PersonaType.ESTABLISHED)
```

NOTE: The old Persona had `scene` and `participation` properties — remove those.
SceneParticipation still exists separately for tracking who joined a scene.

---

## Task 3: Add PersonaDiscovery Model

**Files:**
- Modify: `src/world/scenes/models.py`

Add after Persona, replacing PersonaIdentification:

```python
class PersonaDiscovery(SharedMemoryModel):
    """Records that a character discovered two personas are the same person.

    Stores only raw discovery pairs. A service function handles resolution
    logic (what name to display, transitive chains, etc.).
    """

    persona_a = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="discoveries_as_a",
    )
    persona_b = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="discoveries_as_b",
    )
    discovered_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="persona_discoveries",
        help_text="The character who figured out these two personas are the same person",
    )
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona_a", "persona_b", "discovered_by"],
                name="unique_persona_discovery",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.discovered_by} knows "
            f"{self.persona_a.name} = {self.persona_b.name}"
        )
```

Remove PersonaIdentification model.

---

## Task 4: Simplify CharacterIdentity

**Files:**
- Modify: `src/world/character_sheets/models.py`

Remove `primary_guise` and `active_guise` FKs. Keep only `active_persona`. Remove
Guise import/references.

```python
class CharacterIdentity(SharedMemoryModel):
    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="character_identity",
    )
    active_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="active_for_identities",
        help_text="Who this character is presenting as right now",
    )

    def __str__(self) -> str:
        return f"Identity: {self.active_persona.name} ({self.character.db_key})"

    def clean(self) -> None:
        super().clean()
        if (
            self.active_persona_id
            and self.active_persona.character_identity_id != self.pk
        ):
            raise ValidationError(
                {"active_persona": "Active persona must belong to this character identity."}
            )
```

---

## Task 5: Remove Guise Model

**Files:**
- Modify: `src/world/character_sheets/models.py`

Delete the entire Guise class. Remove `_ensure_default_persona` method (no longer needed —
Persona creation is handled by `ensure_character_identity` service).

---

## Task 6: Update Societies Models — FK Guise → Persona

**Files:**
- Modify: `src/world/societies/models.py`

Rename all `guise` FKs to `persona` across 7 models:

1. `OrganizationMembership.guise` → `.persona` (FK to `scenes.Persona`)
2. `SocietyReputation.guise` → `.persona`
3. `OrganizationReputation.guise` → `.persona`
4. `LegendEntry.guise` → `.persona`
5. `LegendSpread.spreader_guise` → `.spreader_persona`
6. `LegendDeedStory.author` (guise FK) → `.author` (persona FK)
7. `GuiseLegendSummary.guise` → rename model to `PersonaLegendSummary`, field to `.persona`

Update all `related_name` values accordingly. Update `__str__` methods.
Update clean() methods that validate `is_default` or `is_persistent` to check
`persona_type` instead (PRIMARY/ESTABLISHED = can have memberships, TEMPORARY = cannot).

---

## Task 7: Update Skills Models — FK Guise → Persona

**Files:**
- Modify: `src/world/skills/models.py`

`TrainingAllocation.mentor` FK points to Guise. Change to point to `scenes.Persona`.

---

## Task 8: Update Scenes Models — Remove Guise References

**Files:**
- Modify: `src/world/scenes/models.py`

InteractionAudience currently has `guise` FK. Since Persona IS the identity now, change:
- `InteractionAudience.guise` → `InteractionAudience.persona` (FK to Persona)

This makes sense because the audience record now tracks "which persona was watching" —
the same model that the writer's identity uses.

Also update InteractionAudience unique constraint and indexes.

---

## Task 9: Delete ALL Affected Migrations, Regenerate

**Files:**
- Delete: `src/world/scenes/migrations/0002_*.py`, `0003_*.py`
- Delete: `src/world/character_sheets/migrations/0004_*.py`
- Delete: `src/world/relationships/migrations/0002_*.py`
- Delete: `src/world/societies/migrations/` (all non-0001)
- Delete: `src/world/skills/migrations/` (all non-0001)
- Potentially others depending on dependency chain

Since there is no production data, delete ALL non-initial migrations for affected apps
and regenerate fresh:

```bash
arx manage makemigrations character_sheets scenes societies skills relationships
arx manage migrate
```

Also update the partition SQL files (`src/world/scenes/sql/`) if the Interaction table
schema changed (persona FK is already there, but verify column names match).

Recreate `0003_partition_interaction.py` with correct dependency.

---

## Task 10: Update Societies Services

**Files:**
- Modify: `src/world/societies/services.py`

Rename all `guise` params to `persona`. Update function signatures:
- `create_solo_deed(persona=...)` instead of `guise=...`
- `create_legend_event(personas=...)` instead of `guises=...`
- `spread_deed(spreader_persona=...)` instead of `spreader_guise=...`
- `spread_event(spreader_persona=...)` instead of `spreader_guise=...`
- `get_guise_legend_total()` → `get_persona_legend_total()`

Update internal logic to check `persona.is_established_or_primary` instead of
`guise.is_default or guise.is_persistent`.

---

## Task 11: Update Interaction Services

**Files:**
- Modify: `src/world/scenes/interaction_services.py`

- `create_interaction()`: rename `audience_guises` → `audience_personas`
- `resolve_audience()`: return `list[Persona]` instead of `list[Guise]`, read
  `identity.active_persona` instead of `identity.active_guise`
- `can_view_interaction()`: rename `guise` → `persona`
- `mark_very_private()`: rename `guise` → `persona`
- `delete_interaction()`: rename `guise` → `persona`, check `interaction.persona_id == persona.pk`

---

## Task 12: Update Identity Services

**Files:**
- Modify: `src/world/character_sheets/identity_services.py`

`ensure_character_identity()` no longer creates Guises. Instead:
1. Create primary Persona (persona_type=PRIMARY, is_fake_name=False)
2. Create CharacterIdentity with active_persona pointing to primary

---

## Task 13: Update Interaction Serializers, Permissions, Filters, Views

**Files:**
- Modify: `src/world/scenes/interaction_serializers.py`
- Modify: `src/world/scenes/interaction_permissions.py`
- Modify: `src/world/scenes/interaction_filters.py`
- Modify: `src/world/scenes/interaction_views.py`

Serializers: rename `guise_name` → keep as `persona_name` (already exists) or rename
for clarity. `InteractionAudienceSerializer` changes `guise_name` → `persona_name`.

Permissions: `get_account_guises()` → `get_account_personas()`. Returns persona IDs
instead of guise IDs.

Filters: `guise` filter → `persona` filter (it may already exist).

Views: update `select_related` paths — remove `persona__guise` chain, just
`persona__character_identity`. UNION subquery branches use `persona_id__in` and
`audience__persona_id__in`.

---

## Task 14: Update Character Sheets Serializers and Data Handler

**Files:**
- Modify: `src/world/character_sheets/serializers.py`
- Modify: `src/evennia_extensions/data_handlers/character_data.py`

Serializers: `_build_guises()` → `_build_personas()`. Update prefetch paths.

Data handler: `_get_guises()` → `_get_personas()`, `get_default_guise()` →
`get_primary_persona()`, `_get_active_guise()` → `_get_active_persona()`.
Update `get_display_name()` and `get_display_description()` to use persona.

---

## Task 15: Update All Factories

**Files:**
- Modify: `src/world/character_sheets/factories.py`
- Modify: `src/world/scenes/factories.py`
- Modify: `src/world/societies/factories.py`

character_sheets: Remove GuiseFactory. Update CharacterIdentityFactory to create
a primary Persona directly. Remove CompleteCharacterFactory's guise creation.

scenes: PersonaFactory updated — no `guise` SubFactory, has `character_identity`
SubFactory and `persona_type` field. Remove `_create` override (no more auto-created
default persona to conflict with).

societies: All factories rename `guise` → `persona`, import PersonaFactory from
scenes instead of GuiseFactory from character_sheets. PersistentGuiseFactory →
EstablishedPersonaFactory or similar.

---

## Task 16: Update All Admin

**Files:**
- Modify: `src/world/character_sheets/admin.py`
- Modify: `src/world/societies/admin.py` (if it references guise)

character_sheets: Remove GuiseAdmin. Update CharacterIdentityAdmin — remove
`primary_guise`, `active_guise` from list_display.

societies: Update any admin referencing `guise` field to `persona`.

---

## Task 17: Update All Tests

**Files:** All test files referencing Guise, GuiseFactory, or guise fields.

This is the biggest task. Mechanical but widespread:
- Replace `GuiseFactory` with `PersonaFactory` (with persona_type=PRIMARY or ESTABLISHED)
- Replace `.guise` field access with `.persona`
- Replace `guise=` kwargs with `persona=`
- Update CharacterIdentity test setup (one FK instead of three)
- Add PersonaDiscovery tests
- Remove PersonaIdentification tests

Key test files:
- `src/world/character_sheets/tests/test_models.py`
- `src/world/character_sheets/tests/test_handlers.py`
- `src/world/character_sheets/tests/test_viewset.py`
- `src/world/scenes/tests/test_models.py`
- `src/world/scenes/tests/test_interaction_services.py`
- `src/world/scenes/tests/test_interaction_views.py`
- `src/world/scenes/tests/test_permissions.py`
- `src/world/scenes/tests/test_summary_views.py`
- `src/world/scenes/tests/test_view_actions_permissions.py`
- `src/world/scenes/tests/test_views.py`
- `src/world/societies/tests/test_models.py`
- `src/world/societies/tests/test_services.py`
- `src/world/skills/tests/test_training.py`
- `src/world/progression/tests/test_models.py`
- `src/flows/tests/test_message_location.py`

---

## Task 18: Update Partition SQL

**Files:**
- Modify: `src/world/scenes/sql/partition_interaction_forward.sql`
- Modify: `src/world/scenes/sql/partition_interaction_reverse.sql`

Verify the Interaction table schema in the SQL matches the model. The `persona_id`
column should still be there. If InteractionAudience changed from `guise_id` to
`persona_id`, update the composite FK constraint name.

---

## Task 19: Full Test Suite Pass

Run: `uv run arx test`
Fix all failures.
Run: `ruff check src/`

Commit:
```
git commit -m "refactor: collapse Guise + Persona into unified Persona model

- Replace Guise model with Persona (PersonaType: PRIMARY/ESTABLISHED/TEMPORARY)
- Simplify CharacterIdentity to character + active_persona (one FK)
- Add PersonaDiscovery for identity link tracking
- Update all FK references across societies, legend, skills, scenes, interactions
- Regenerate all affected migrations

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Summary

| Task | What | Scope |
|------|------|-------|
| 1 | PersonaType constant | 1 file |
| 2 | New Persona model | 1 file |
| 3 | PersonaDiscovery model | 1 file |
| 4 | Simplify CharacterIdentity | 1 file |
| 5 | Remove Guise model | 1 file |
| 6 | Societies FK rename | 1 file (7 models) |
| 7 | Skills FK rename | 1 file |
| 8 | Scenes InteractionAudience FK | 1 file |
| 9 | Delete + regenerate migrations | Many files |
| 10 | Societies services | 1 file |
| 11 | Interaction services | 1 file |
| 12 | Identity services | 1 file |
| 13 | Interaction serializers/permissions/filters/views | 4 files |
| 14 | Character sheets serializers + data handler | 2 files |
| 15 | All factories | 3 files |
| 16 | All admin | 2 files |
| 17 | All tests | ~15 files |
| 18 | Partition SQL | 2 files |
| 19 | Full test suite | Integration |

### Not in this plan
- PersonaDiscovery resolution handler (display logic) — future service function
- Discovery gameplay mechanics
- Guise switching UX / frontend
- Persona promotion workflow (temporary → established)
