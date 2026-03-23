# CharacterIdentity & Interaction Wiring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add CharacterIdentity model as the single source of truth for "who is this
character right now," wire communication actions to create Interactions, and clean up
message_location() to be a pure broadcast function.

**Architecture:** CharacterIdentity (OneToOne with ObjectDB, in character_sheets app) holds
primary_guise, active_guise, active_persona — all non-nullable. Guise.save() auto-creates
a default persona. record_interaction() reads active_persona and resolves audience from
the room. Action classes call message_location() for broadcast + record_interaction() for
persistence. message_location() is stripped of all database writes.

**Tech Stack:** Django/DRF, SharedMemoryModel, PostgreSQL, FactoryBoy

**Design doc:** `docs/plans/2026-03-21-character-identity-interaction-wiring-design.md`

**Key conventions:**
- SharedMemoryModel for all models (import from `evennia.utils.idmapper.models`)
- Type annotations on all functions in typed apps (character_sheets and scenes are typed)
- Absolute imports only, TextChoices in constants.py
- Run tests: `echo "yes" | arx test world.character_sheets world.scenes`
- Full suite: `uv run arx test`
- Run lint: `ruff check <file>`

---

## Task 1: CharacterIdentity Model

**Files:**
- Modify: `src/world/character_sheets/models.py`
- Test: `src/world/character_sheets/tests/test_models.py`

Add the CharacterIdentity model after Guise (or at end of file). It sits alongside
CharacterSheet — same ObjectDB anchor, different concerns.

```python
class CharacterIdentity(SharedMemoryModel):
    """Single source of truth for who a character presents as and what they know.

    Sits alongside CharacterSheet: CharacterSheet = what they are (stats,
    demographics). CharacterIdentity = who they present as (guises, personas)
    and what they know (identifications, future codex knowledge).

    All three FK fields are non-nullable. At any point, you can ask
    'who is this character right now?' and get a definitive answer.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="character_identity",
        help_text="The character this identity belongs to",
    )
    primary_guise = models.ForeignKey(
        Guise,
        on_delete=models.PROTECT,
        related_name="primary_for_identities",
        help_text="The character's 'real' identity. Always exists, never null.",
    )
    active_guise = models.ForeignKey(
        Guise,
        on_delete=models.PROTECT,
        related_name="active_for_identities",
        help_text="Which identity the character is currently presenting as. "
        "Defaults to primary_guise. Changes when switching to an alter ego.",
    )
    active_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="active_for_identities",
        help_text="Current appearance. Defaults to active_guise's default persona. "
        "Changes to a disguise persona when wearing a mask/illusion.",
    )

    class Meta:
        verbose_name = "Character Identity"
        verbose_name_plural = "Character Identities"

    def __str__(self) -> str:
        return f"Identity: {self.active_persona.name} ({self.character.db_key})"
```

**Tests:**
- Creation with all FKs
- OneToOne constraint (can't create two for same character)
- `__str__` shows persona name and character name

---

## Task 2: Default Persona Auto-Creation on Guise Save

**Files:**
- Modify: `src/world/character_sheets/models.py` (Guise.save)
- Modify: `src/world/scenes/models.py` (Persona — may need import adjustment)
- Test: `src/world/character_sheets/tests/test_models.py`

When a Guise is saved, ensure a default Persona exists for it. This guarantees that
`active_persona` always has something valid to point to.

Add to Guise.save() after the existing default-uniqueness logic:

```python
def save(self, *args: Any, **kwargs: Any) -> None:
    if self.is_default:
        Guise.objects.filter(character=self.character, is_default=True).exclude(
            pk=self.pk,
        ).update(is_default=False)
    super().save(*args, **kwargs)
    # Ensure a default persona exists for this guise
    self._ensure_default_persona()

def _ensure_default_persona(self) -> None:
    """Create a default (non-disguise) persona if one doesn't exist."""
    from world.scenes.models import Persona

    Persona.objects.get_or_create(
        guise=self,
        is_fake_name=False,
        participation=None,
        defaults={
            "name": self.name,
            "description": self.description,
            "character": self.character,
        },
    )
```

**Tests:**
- Creating a Guise auto-creates a default Persona
- The persona has `is_fake_name=False`, `participation=None`, name matches guise
- Creating a second Guise doesn't affect the first's persona
- Updating a Guise name does NOT update the existing persona name (personas are
  point-in-time snapshots — but the default persona arguably should track. Leave for
  now, this is an open question from the design doc.)

---

## Task 3: CharacterIdentity Auto-Creation Service

**Files:**
- Create: `src/world/character_sheets/identity_services.py`
- Test: `src/world/character_sheets/tests/test_identity_services.py`

Service function to create or ensure a CharacterIdentity exists for a character:

```python
def ensure_character_identity(character: ObjectDB) -> CharacterIdentity:
    """Ensure a CharacterIdentity exists for the character.

    Creates the default guise, default persona, and CharacterIdentity if needed.
    Idempotent — safe to call multiple times.
    """
    from world.character_sheets.models import CharacterIdentity, Guise
    from world.scenes.models import Persona

    # Ensure default guise exists
    guise, _ = Guise.objects.get_or_create(
        character=character,
        is_default=True,
        defaults={"name": character.db_key},
    )

    # Guise.save() ensures default persona exists, but get it explicitly
    persona = Persona.objects.filter(
        guise=guise, is_fake_name=False, participation=None,
    ).first()
    if persona is None:
        persona = Persona.objects.create(
            guise=guise,
            is_fake_name=False,
            participation=None,
            name=guise.name,
            character=character,
        )

    # Ensure CharacterIdentity exists
    identity, _ = CharacterIdentity.objects.get_or_create(
        character=character,
        defaults={
            "primary_guise": guise,
            "active_guise": guise,
            "active_persona": persona,
        },
    )

    return identity
```

**Tests:**
- Creates identity, guise, and persona from scratch for a bare character
- Idempotent — calling twice returns the same identity
- Respects existing guise/persona if already present

---

## Task 4: Generate Migration

**Files:**
- Generate: `src/world/character_sheets/migrations/`

Run: `arx manage makemigrations character_sheets`
Run: `arx manage migrate`
Run: `echo "yes" | arx test world.character_sheets`

---

## Task 5: CharacterIdentity Factory

**Files:**
- Modify: `src/world/character_sheets/factories.py`

```python
class CharacterIdentityFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = CharacterIdentity

    character = factory.SubFactory(CharacterFactory)
    primary_guise = factory.LazyAttribute(
        lambda o: GuiseFactory(character=o.character, is_default=True)
    )
    active_guise = factory.LazyAttribute(lambda o: o.primary_guise)
    active_persona = factory.LazyAttribute(
        lambda o: PersonaFactory(guise=o.primary_guise, is_fake_name=False, participation=None)
    )
```

Import PersonaFactory from `world.scenes.factories`.

**Test:** Factory creates valid CharacterIdentity with all relations.

---

## Task 6: record_interaction() Service Function

**Files:**
- Modify: `src/world/scenes/interaction_services.py`
- Test: `src/world/scenes/tests/test_interaction_services.py`

Add two new functions:

### resolve_audience()

```python
def resolve_audience(character: ObjectDB) -> list[Guise]:
    """Get the active guises of all other characters in the room.

    Returns empty list if the character is alone or has no location.
    Characters without a CharacterIdentity (NPCs) are skipped.
    """
    location = character.location
    if location is None:
        return []

    guises = []
    for obj in location.contents:
        if obj == character:
            continue
        try:
            identity = obj.character_identity
            guises.append(identity.active_guise)
        except (AttributeError, ObjectDoesNotExist):
            continue
    return guises
```

Note: `ObjectDoesNotExist` comes from `django.core.exceptions` — it's the base for
RelatedObjectDoesNotExist which is raised when accessing a OneToOne reverse that
doesn't exist.

### record_interaction()

```python
def record_interaction(
    *,
    character: ObjectDB,
    content: str,
    mode: str,
    scene: Scene | None = None,
    target_personas: list[Persona] | None = None,
) -> Interaction | None:
    """Record an IC interaction to the database.

    Reads the character's active_persona from CharacterIdentity. Resolves
    audience from other characters in the room. Skips recording if:
    - Character has no CharacterIdentity
    - No audience (character is alone)
    - Scene is ephemeral

    This is the persistence layer only — does NOT broadcast to clients.
    Call message_location() separately for real-time delivery.
    """
    from world.character_sheets.models import CharacterIdentity

    try:
        identity = character.character_identity
    except CharacterIdentity.DoesNotExist:
        return None

    persona = identity.active_persona
    audience_guises = resolve_audience(character)

    if not audience_guises:
        return None

    # Resolve scene from location if not provided
    if scene is None and character.location is not None:
        scene = getattr(character.location, "active_scene", None)

    return create_interaction(
        persona=persona,
        content=content,
        mode=mode,
        audience_guises=audience_guises,
        scene=scene,
        target_personas=target_personas,
    )
```

**Tests:**
- Records interaction when audience present
- Returns None when alone
- Returns None when no CharacterIdentity
- Returns None for ephemeral scene
- Uses active_persona from CharacterIdentity
- Resolves audience from room contents

---

## Task 7: Clean Up message_location()

**Files:**
- Modify: `src/flows/service_functions/communication.py`

Strip all database writes from `message_location()`. Remove:
- SceneParticipation.objects.get_or_create
- Guise.objects.get_or_create
- Persona.objects.get_or_create
- SceneMessage.objects.create
- The `active_scene` block entirely

Remove unused imports: `Guise`, `Persona`, `SceneMessage`, `SceneParticipation`,
`MessageContext`, `MessageMode`.

The function becomes ~15 lines: resolve mapping, parse text, `location.msg_contents()`.

**Tests:**
- Update `src/flows/tests/test_message_location.py` — the two tests that verify
  SceneMessage creation need to be rewritten. They should verify that
  `message_location()` only broadcasts (no DB writes).

---

## Task 8: Wire Communication Actions

**Files:**
- Modify: `src/actions/definitions/communication.py`

### PoseAction.execute()

```python
def execute(self, actor, context=None, **kwargs):
    text = kwargs.get("text", "")
    if not text:
        return ActionResult(success=False, message="Pose what?")

    sdm = context.scene_data if context else SceneDataManager()
    caller_state = sdm.initialize_state_for_object(actor)

    # Broadcast to room (real-time delivery)
    message_location(caller_state, text)

    # Record the interaction (persistence)
    record_interaction(
        character=actor,
        content=text,
        mode=InteractionMode.POSE,
    )

    return ActionResult(success=True)
```

### SayAction.execute()

Same pattern but with `mode=InteractionMode.SAY` and the formatted text.

### WhisperAction.execute()

Whisper is trickier — it goes to a specific target, not the whole room. The broadcast
uses `send_message()` (to one person), and the interaction should record with:
- `mode=InteractionMode.WHISPER`
- `audience_guises` = only the target's guise (not the whole room)

```python
def execute(self, actor, context=None, **kwargs):
    target = kwargs.get("target")
    text = kwargs.get("text", "")
    if target is None or not text:
        return ActionResult(success=False, message="Whisper what to whom?")

    sdm = context.scene_data if context else SceneDataManager()
    caller_state = sdm.initialize_state_for_object(actor)
    target_state = sdm.initialize_state_for_object(target)

    # Broadcast to target only (real-time delivery)
    send_message(
        target_state,
        f'{caller_state.get_display_name(looker=target_state)} whispers "{text}"',
    )

    # Record the interaction (whisper = target-only audience)
    record_whisper_interaction(
        character=actor,
        target=target,
        content=text,
    )

    return ActionResult(success=True)
```

### record_whisper_interaction() (new helper)

```python
def record_whisper_interaction(
    *,
    character: ObjectDB,
    target: ObjectDB,
    content: str,
) -> Interaction | None:
    """Record a whisper interaction with only the target as audience."""
    from world.character_sheets.models import CharacterIdentity

    try:
        writer_identity = character.character_identity
        target_identity = target.character_identity
    except CharacterIdentity.DoesNotExist:
        return None

    persona = writer_identity.active_persona
    target_guise = target_identity.active_guise
    target_persona = target_identity.active_persona

    scene = getattr(character.location, "active_scene", None) if character.location else None

    return create_interaction(
        persona=persona,
        content=content,
        mode=InteractionMode.WHISPER,
        audience_guises=[target_guise],
        scene=scene,
        target_personas=[target_persona],
    )
```

Add to `interaction_services.py`.

Import `InteractionMode` and `record_interaction` in the actions file.

---

## Task 9: Update Admin

**Files:**
- Modify: `src/world/character_sheets/admin.py`

Register CharacterIdentity:

```python
@admin.register(CharacterIdentity)
class CharacterIdentityAdmin(admin.ModelAdmin):
    list_display = ["character", "primary_guise", "active_guise", "active_persona"]
    list_select_related = ["primary_guise", "active_guise", "active_persona"]
```

---

## Task 10: Full Test Suite Pass

Run: `uv run arx test`

Fix any failures. The main risk areas:
- `flows/tests/test_message_location.py` — SceneMessage tests need updating
- Any test that creates characters and expects them to have identities
- Factory chain issues

Commit everything:
```
git commit -m "feat: CharacterIdentity model, record_interaction(), interaction wiring

- CharacterIdentity: single source of truth for primary_guise, active_guise,
  active_persona (all non-nullable, in character_sheets app)
- Guise.save() auto-creates default persona
- record_interaction(): persistence service that reads active_persona and
  resolves audience from room contents. Skips if alone or ephemeral.
- record_whisper_interaction(): whisper-specific variant with target-only audience
- message_location() stripped to pure broadcast (no DB writes)
- PoseAction/SayAction/WhisperAction call both broadcast + record explicitly

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | CharacterIdentity model | `character_sheets/models.py` |
| 2 | Default persona on Guise.save() | `character_sheets/models.py` |
| 3 | ensure_character_identity() service | `character_sheets/identity_services.py` |
| 4 | Migration | `character_sheets/migrations/` |
| 5 | CharacterIdentityFactory | `character_sheets/factories.py` |
| 6 | record_interaction() + resolve_audience() | `scenes/interaction_services.py` |
| 7 | Clean up message_location() | `flows/service_functions/communication.py` |
| 8 | Wire PoseAction/SayAction/WhisperAction | `actions/definitions/communication.py` |
| 9 | Admin registration | `character_sheets/admin.py` |
| 10 | Full test suite pass | All files |

### Not in this plan
- **Frontend changes** — Scene views querying Interactions instead of SceneMessages
- **SceneMessage model removal** — Deferred to Phase 3 after frontend migration
- **Action-type interactions** (flirt, taunt) — Future Action subclasses that call
  record_interaction(mode=ACTION) with check results
- **Guise switching UX** — Frontend for changing active_guise
- **Disguise mechanics** — Creating temporary personas with is_fake_name=True
