# Identity Hierarchy & Persona Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple Persona from SceneParticipation, back every persona with a Guise,
simplify Interaction to 7 columns (persona, scene, content, mode, visibility, timestamp + id),
and add PersonaIdentification for disguise reveals.

**Architecture:** Persona becomes a point-in-time appearance of a Guise. Every interaction
has a non-nullable persona FK. Guise is the persistent identity (relationships, reputation,
legend). The Interaction model drops roster_entry, location, and sequence_number — all
derivable through persona.guise.character or scene.location. InteractionAudience switches
from roster_entry to guise for viewer tracking.

**Tech Stack:** Django/DRF, SharedMemoryModel, PostgreSQL declarative partitioning, FactoryBoy

**Design doc:** `docs/plans/2026-03-20-identity-hierarchy-persona-refactor-design.md`

**Key conventions (from CLAUDE.md):**
- All models use `SharedMemoryModel` (import from `evennia.utils.idmapper.models`)
- Type annotations on all functions (scenes is in typed apps)
- Absolute imports only, TextChoices in constants.py
- No JSON fields, no signals, FilterSets for query params
- Prefetch with to_attr, no queries in loops
- Run tests: `echo "yes" | arx test world.scenes`
- Run lint: `ruff check <file>`

---

## Task 1: Modify Persona Model

**Files:**
- Modify: `src/world/scenes/models.py` (Persona class, ~line 136-172)

**Changes:**

1. Make `participation` nullable:
```python
participation = models.ForeignKey(
    SceneParticipation,
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name="personas",
    help_text="Scene participation if this persona is scene-scoped. "
    "Null for personas outside of scenes (organic grid RP).",
)
```

2. Add `guise` FK (non-nullable):
```python
guise = models.ForeignKey(
    "character_sheets.Guise",
    on_delete=models.CASCADE,
    related_name="personas",
    help_text="The persistent identity this persona represents. Every persona "
    "is a point-in-time appearance of a guise — it could be identical to the "
    "guise (default case), a modified appearance, or a temporary disguise that "
    "obscures the guise entirely (is_fake_name=True).",
)
```

3. Update `is_fake_name` help_text:
```python
is_fake_name = models.BooleanField(
    default=False,
    help_text="True when the persona obscures its guise — other characters "
    "cannot determine the guise until they identify it through gameplay. "
    "False when the persona is transparent (name matches guise).",
)
```

4. Change unique_together from `["participation", "name"]` to allow non-scene personas:
```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["participation", "name"],
            name="unique_persona_per_participation",
            condition=models.Q(participation__isnull=False),
        ),
        models.UniqueConstraint(
            fields=["guise"],
            name="unique_default_persona_per_guise",
            condition=models.Q(is_fake_name=False, participation__isnull=True),
        ),
    ]
```

The second constraint ensures each guise has at most one non-scene transparent persona
(the "default" persona that represents the guise as-is).

5. Update `__str__` to not assume participation exists:
```python
def __str__(self) -> str:
    if self.participation_id:
        return f"{self.name} in {self.participation.scene.name}"
    return f"{self.name} ({self.guise.name})"
```

6. Update `scene` property to handle nullable participation:
```python
@property
def scene(self) -> Scene | None:
    """Convenience access to the persona's scene, if any."""
    if self.participation_id:
        return self.participation.scene
    return None
```

**Step 1:** Make the changes above.
**Step 2:** Run `ruff check src/world/scenes/models.py`
**Step 3:** Do NOT generate migration yet — wait for Task 3.

---

## Task 2: Add PersonaIdentification Model

**Files:**
- Modify: `src/world/scenes/models.py`

**Add after Persona class:**

```python
class PersonaIdentification(SharedMemoryModel):
    """Tracks which characters have identified an obscured persona's guise.

    Knowledge belongs to the character (the mind), not the guise (the face).
    If Ariel figures out who the Hooded Figure is while disguised as The Masked
    Robber, Ariel still knows when she's just being Ariel.
    """

    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="identifications",
        help_text="The obscured persona that was identified",
    )
    identified_by = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="persona_identifications",
        help_text="The character who figured out the disguise. Uses CharacterSheet "
        "as stand-in for a dedicated Character model (see design doc TODO).",
    )
    identified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "identified_by"],
                name="unique_identification_per_character",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.identified_by} identified "
            f"{self.persona.name} as {self.persona.guise.name}"
        )
```

**Step 1:** Add the model.
**Step 2:** Run lint.

---

## Task 3: Simplify Interaction Model to 7 Columns

**Files:**
- Modify: `src/world/scenes/models.py` (Interaction class, ~line 274+)

**Changes:**

1. Remove `roster_entry` FK
2. Remove `location` FK
3. Remove `sequence_number` field
4. Remove `save()` override (was for auto-sequencing)
5. Make `persona` non-nullable (remove null=True, blank=True)
6. Update help_text on persona:
```python
persona = models.ForeignKey(
    Persona,
    on_delete=models.CASCADE,
    related_name="interactions_written",
    help_text="How the writer appeared at this moment. Always set — every "
    "interaction has a persona, even if it's just the default appearance "
    "matching the character's guise.",
)
```

7. Update `__str__`:
```python
def __str__(self) -> str:
    content_preview = str(self.content)[:50]
    return f"{self.persona.name}: {content_preview}..."
```

8. Update Meta.indexes — remove indexes referencing removed fields:
```python
class Meta:
    indexes = [
        models.Index(fields=["persona", "timestamp"]),
        models.Index(fields=["scene", "timestamp"]),
        models.Index(
            fields=["timestamp"],
            name="interaction_very_private_idx",
            condition=models.Q(visibility="very_private"),
        ),
        models.Index(
            fields=["timestamp"],
            name="interaction_no_scene_idx",
            condition=models.Q(scene__isnull=True),
        ),
    ]
```

9. Remove `cached_target_personas` property (the M2M still exists but the cached
   property setter pattern stays the same — just keep it).

---

## Task 4: Update InteractionAudience — Guise Instead of RosterEntry

**Files:**
- Modify: `src/world/scenes/models.py` (InteractionAudience class)

**Changes:**

1. Replace `roster_entry` FK with `guise` FK:
```python
guise = models.ForeignKey(
    "character_sheets.Guise",
    on_delete=models.CASCADE,
    related_name="interactions_witnessed",
    help_text="The viewer's persistent identity when they witnessed this interaction",
)
```

2. Keep `persona` FK nullable (only set if viewer was also disguised).

3. Update unique constraint:
```python
constraints = [
    models.UniqueConstraint(
        fields=["interaction", "guise"],
        name="unique_audience_per_interaction",
    ),
]
```

4. Update index:
```python
indexes = [
    models.Index(fields=["guise", "interaction"]),
    models.Index(fields=["timestamp"], name="interactionaudience_ts_brin"),
]
```

5. Update `__str__`:
```python
def __str__(self) -> str:
    name = self.persona.name if self.persona else self.guise.name
    return f"{name} witnessed interaction {self.interaction_id}"
```

---

## Task 5: Update InteractionFavorite — Keep RosterEntry (OOC)

InteractionFavorite already uses `roster_entry` which is correct — favorites are OOC
bookmarks, not IC actions. **No changes needed** except confirming it's still correct
after the other model changes.

---

## Task 6: Delete Migrations, Regenerate, and Update Partition SQL

**Files:**
- Delete: `src/world/scenes/migrations/0002_*.py`
- Delete: `src/world/scenes/migrations/0003_*.py`
- Delete: `src/world/relationships/migrations/0002_*.py`
- Modify: `src/world/scenes/sql/partition_interaction_forward.sql`
- Modify: `src/world/scenes/sql/partition_interaction_reverse.sql`

**Steps:**

1. Delete the old migrations.
2. Run `arx manage makemigrations scenes` — generates fresh 0002 with all model changes.
3. Run `arx manage makemigrations relationships` — regenerates 0002 for linked_interaction.
4. Update `partition_interaction_forward.sql`:
   - Remove `roster_entry_id`, `location_id`, `sequence_number` from CREATE TABLE
   - Change `persona_id bigint` to `persona_id bigint NOT NULL`
   - Remove indexes referencing removed columns
   - Add `(persona_id, timestamp)` index
   - Remove FK constraints for roster_entry and location
   - Update child table FK constraints if column names changed
5. Update `partition_interaction_reverse.sql` to match.
6. Recreate `0003_partition_interaction.py` (it reads from the SQL files, so just ensure
   the dependency is correct).
7. Run `arx manage migrate`
8. Run `echo "yes" | arx test world.scenes` to verify.

---

## Task 7: Update create_interaction Service

**Files:**
- Modify: `src/world/scenes/interaction_services.py`

**Changes to `create_interaction()`:**

1. Replace `roster_entry` param with `persona` (non-nullable):
```python
def create_interaction(
    *,
    persona: Persona,
    content: str,
    mode: str,
    audience_guises: list[Guise],
    scene: Scene | None = None,
    target_personas: list[Persona] | None = None,
    audience_personas: dict[int, Persona] | None = None,
) -> Interaction | None:
```

2. Update Interaction.objects.create:
```python
interaction = Interaction.objects.create(
    persona=persona,
    content=content,
    mode=mode,
    scene=scene,
)
```

3. Update audience creation — use `guise` instead of `roster_entry`:
```python
audience_persona_map = audience_personas or {}
audience_records = [
    InteractionAudience(
        interaction=interaction,
        timestamp=interaction.timestamp,
        guise=g,
        persona=audience_persona_map.get(g.pk),
    )
    for g in audience_guises
]
```

**Changes to `can_view_interaction()`:**

Replace `roster_entry` param with `guise`:
```python
def can_view_interaction(
    interaction: Interaction,
    guise: Guise,
    *,
    is_staff: bool = False,
) -> bool:
```

Update audience check:
```python
is_audience = InteractionAudience.objects.filter(
    interaction=interaction, guise=guise,
).exists()
is_writer = interaction.persona.guise_id == guise.pk
```

**Changes to `mark_very_private()` and `delete_interaction()`:**

These need the roster_entry for ownership checks. The caller should resolve
roster_entry from `guise.character.roster_entry` before calling. Update signatures
to accept `guise` and derive roster_entry internally:

```python
def mark_very_private(interaction: Interaction, guise: Guise) -> None:
    is_audience = InteractionAudience.objects.filter(
        interaction=interaction, guise=guise,
    ).exists()
    is_writer = interaction.persona.guise_id == guise.pk
    if not (is_audience or is_writer):
        return
    interaction.visibility = InteractionVisibility.VERY_PRIVATE
    interaction.save(update_fields=["visibility"])


def delete_interaction(interaction: Interaction, guise: Guise) -> bool:
    if interaction.persona.guise_id != guise.pk:
        return False
    age = timezone.now() - interaction.timestamp
    if age > timedelta(days=DELETION_WINDOW_DAYS):
        return False
    interaction.delete()
    return True
```

---

## Task 8: Update Interaction Serializers

**Files:**
- Modify: `src/world/scenes/interaction_serializers.py`

**Changes:**

1. `InteractionListSerializer` — update fields:
   - Remove `character_name`, `location`
   - Add `guise_name` (from `persona.guise.name`)
   - `persona_name` comes from `persona.name`
   - Keep `scene`, `content`, `mode`, `visibility`, `timestamp`
   - `is_favorited` stays (checks roster_entry from favorites, which is OOC)

2. `InteractionAudienceSerializer` — change from roster_entry to guise:
   - Show `guise_name` and `guise_id` instead of persona

3. Update `select_related` paths in viewset to include `persona__guise__character__roster_entry`

---

## Task 9: Update Interaction Permissions

**Files:**
- Modify: `src/world/scenes/interaction_permissions.py`

**Changes:**

Update `get_account_roster_entries` to also return guises for the account's characters.
Or add a parallel `get_account_guises(request)` helper.

`CanViewInteraction` — check audience guises against account's guises.
`IsInteractionWriter` — check `interaction.persona.guise.character.roster_entry`
against account's roster entries.

---

## Task 10: Update Interaction ViewSet

**Files:**
- Modify: `src/world/scenes/interaction_views.py`

**Changes:**

1. Update `get_queryset` — the UNION subquery pattern needs updating:
   - "Writer" branch: `Q(persona__guise__in=account_guises)` instead of roster_entry
   - "Audience" branch: `Q(audience__guise__in=account_guises)`
   - Public scene and organic branches stay the same

2. Update `select_related`:
```python
.select_related("persona__guise__character__roster_entry", "scene")
```

3. Update `destroy` and `mark_private` to work with guises.

---

## Task 11: Update Interaction Filters

**Files:**
- Modify: `src/world/scenes/interaction_filters.py`

**Changes:**

- Remove `character` filter (was going through roster_entry)
- Add `guise` filter: `NumberFilter(field_name="persona__guise_id")`
- Add `persona` filter: `NumberFilter(field_name="persona_id")`
- Keep `scene`, `mode`, `visibility`, `since`, `until`
- Remove `roster_entry` filter

---

## Task 12: Update Factories

**Files:**
- Modify: `src/world/scenes/factories.py`
- Modify: `src/world/character_sheets/factories.py` (if GuiseFactory needs changes)

**Changes:**

1. `PersonaFactory` — add `guise` SubFactory, make `participation` nullable:
```python
class PersonaFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Persona

    guise = factory.SubFactory(GuiseFactory)
    character = factory.LazyAttribute(lambda o: o.guise.character)
    name = factory.LazyAttribute(lambda o: o.guise.name)
    participation = None  # Default: no scene
```

2. `InteractionFactory` — replace `roster_entry` with `persona`:
```python
class InteractionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Interaction

    persona = factory.SubFactory(PersonaFactory)
    content = factory.Faker("text", max_nb_chars=500)
    mode = InteractionMode.POSE
    visibility = InteractionVisibility.DEFAULT
```

Remove `location` and `roster_entry`.

3. `InteractionAudienceFactory` — replace `roster_entry` with `guise`:
```python
class InteractionAudienceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionAudience

    guise = factory.SubFactory(GuiseFactory)
```

4. Add `PersonaIdentificationFactory`.

---

## Task 13: Update All Tests

**Files:**
- Modify: `src/world/scenes/tests/test_models.py`
- Modify: `src/world/scenes/tests/test_interaction_services.py`
- Modify: `src/world/scenes/tests/test_interaction_views.py`
- Modify: `src/world/scenes/tests/test_summary_views.py`

**Changes across all test files:**

1. Replace `roster_entry=` with `persona=` in Interaction creation
2. Replace `roster_entry=` with `guise=` in InteractionAudience creation
3. Remove `location=` and `character=` from Interaction creation
4. Update `setUpTestData` to create Guises and Personas instead of just RosterEntries
5. Update service function call signatures
6. Add tests for PersonaIdentification model
7. Update visibility test to use guise instead of roster_entry

**New test cases:**
- PersonaIdentification creation and unique constraint
- Persona with nullable participation
- Persona backed by guise
- Interaction with non-nullable persona
- can_view_interaction with guise parameter

---

## Task 14: Update Admin

**Files:**
- Modify: `src/world/scenes/admin.py`

**Changes:**
- Update `InteractionAdmin.list_display` to use `persona` instead of `roster_entry`
- Add `PersonaIdentificationAdmin` registration
- Update `PersonaAdmin` if it exists (or the inline) to show guise

---

## Task 15: Run Full Test Suite and Lint

**Steps:**
1. Run `echo "yes" | arx test world.scenes`
2. Run `echo "yes" | arx test world.relationships`
3. Run `ruff check src/world/scenes/`
4. Fix any failures.

**Commit:**
```
git commit -m "refactor(scenes): identity hierarchy — persona backed by guise, 7-column Interaction"
```

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | Modify Persona — nullable participation, add guise FK | `scenes/models.py` |
| 2 | Add PersonaIdentification model | `scenes/models.py` |
| 3 | Simplify Interaction to 7 columns | `scenes/models.py` |
| 4 | InteractionAudience — guise instead of roster_entry | `scenes/models.py` |
| 5 | InteractionFavorite — confirm no changes | `scenes/models.py` |
| 6 | Delete migrations, regenerate, update partition SQL | migrations, SQL files |
| 7 | Update create_interaction and visibility services | `interaction_services.py` |
| 8 | Update serializers | `interaction_serializers.py` |
| 9 | Update permissions | `interaction_permissions.py` |
| 10 | Update viewset | `interaction_views.py` |
| 11 | Update filters | `interaction_filters.py` |
| 12 | Update factories | `factories.py` |
| 13 | Update all tests | `tests/test_*.py` |
| 14 | Update admin | `admin.py` |
| 15 | Full test suite pass | All files |

### Not in this plan

- **Persona auto-creation service** — how/when default personas are created for characters
  walking the grid. Depends on the communication flow integration.
- **Identification gameplay mechanics** — what checks/skills reveal a persona's guise.
  Depends on the capability/check system.
- **Guise switching UX** — frontend for switching active guise.
- **Character model extraction** — future refactor to create a proper Character model
  that CharacterSheet, Guise, and RosterEntry all point to, replacing ObjectDB as the
  identity anchor. Needed for codex knowledge persistence through roster entry changes.
