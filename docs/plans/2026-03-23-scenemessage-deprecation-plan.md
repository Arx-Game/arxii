# SceneMessage Deprecation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace SceneMessage with Interaction for all RP recording and display, add
real-time WebSocket push for active scene participants, and add InteractionReaction
as a bridge engagement model.

**Architecture:** Phase 1 (this plan) covers backend: InteractionReaction model,
push_interaction() WebSocket delivery, wiring into record_interaction(), and reaction
API. Phase 2 (frontend, separate plan) covers switching the React components to use
the Interaction API and WebSocket handler. Phase 3 (cleanup) removes SceneMessage.

**Tech Stack:** Django/DRF, SharedMemoryModel, PostgreSQL, Evennia WebSocket (msg()),
FactoryBoy

**Design doc:** `docs/plans/2026-03-23-scenemessage-deprecation-design.md`

**Key conventions:**
- SharedMemoryModel for all models
- Type annotations on all functions in typed apps
- Absolute imports only, TextChoices in constants.py
- Prefetch with to_attr, no queries in loops
- `db_constraint=False` for FKs to partitioned Interaction table
- Run tests: `echo "yes" | arx test world.scenes`
- Full suite: `uv run arx test`
- Run lint: `ruff check <file>`

---

## Task 1: InteractionReaction Model

**Files:**
- Modify: `src/world/scenes/models.py`
- Modify: `src/world/scenes/constants.py` (if needed)

Add after InteractionFavorite:

```python
class InteractionReaction(SharedMemoryModel):
    """Emoji reaction on an interaction.

    Bridge model — will be replaced by the proper kudos/voting/favorite
    engagement system. Simple emoji toggle for now.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="reactions",
        db_constraint=False,
        help_text="The interaction being reacted to",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction for composite FK "
        "with partitioned table",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="interaction_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "account", "emoji"],
                name="unique_interaction_reaction",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account} reacted {self.emoji} to interaction {self.interaction_id}"

    def clean(self) -> None:
        super().clean()
        if (
            self.interaction_id
            and self.timestamp
            and hasattr(self, "interaction")
            and self.interaction.timestamp != self.timestamp
        ):
            msg = "timestamp must match interaction.timestamp"
            raise ValidationError({"timestamp": msg})
```

Add `cached_reactions` property to Interaction model (same getter/setter pattern as
cached_audience, cached_favorites):

```python
@property
def cached_reactions(self) -> list[InteractionReaction]:
    try:
        return self._cached_reactions
    except AttributeError:
        return list(self.reactions.all())

@cached_reactions.setter
def cached_reactions(self, value: list[InteractionReaction]) -> None:
    self._cached_reactions = value
```

Generate migration: `arx manage makemigrations scenes`
Apply: `arx manage migrate`

Tests: creation, unique constraint, clean() validation.

Commit: `feat(scenes): add InteractionReaction model`

---

## Task 2: InteractionReaction Factory and Admin

**Files:**
- Modify: `src/world/scenes/factories.py`
- Modify: `src/world/scenes/admin.py`

Factory:
```python
class InteractionReactionFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = InteractionReaction

    interaction = factory.SubFactory(InteractionFactory)
    timestamp = factory.LazyAttribute(lambda o: o.interaction.timestamp)
    account = factory.SubFactory(AccountFactory)
    emoji = "👍"
```

Admin:
```python
@admin.register(InteractionReaction)
class InteractionReactionAdmin(admin.ModelAdmin):
    list_display = ["interaction", "account", "emoji", "created_at"]
    list_filter = ["emoji"]
```

Commit: `feat(scenes): add InteractionReaction factory and admin`

---

## Task 3: InteractionReaction Serializer and ViewSet

**Files:**
- Modify: `src/world/scenes/interaction_serializers.py`
- Modify: `src/world/scenes/interaction_views.py`
- Modify: `src/world/scenes/urls.py`

Serializer:
```python
class InteractionReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionReaction
        fields = ["id", "interaction", "emoji", "created_at"]
        read_only_fields = ["created_at"]
```

Add reaction data to InteractionListSerializer:
```python
reactions = serializers.SerializerMethodField()

def get_reactions(self, obj: Interaction) -> list[dict]:
    """Aggregate emoji counts with reacted-by-current-user flag."""
    try:
        reaction_list = obj.cached_reactions
    except AttributeError:
        reaction_list = list(obj.reactions.all())

    # Count by emoji
    counts: dict[str, int] = {}
    user_reacted: set[str] = set()
    request = self.context.get("request")
    user_id = request.user.pk if request and request.user.is_authenticated else None

    for reaction in reaction_list:
        emoji = reaction.emoji
        counts[emoji] = counts.get(emoji, 0) + 1
        if reaction.account_id == user_id:
            user_reacted.add(emoji)

    return [
        {"emoji": emoji, "count": count, "reacted": emoji in user_reacted}
        for emoji, count in counts.items()
    ]
```

ViewSet — toggle pattern (same as SceneMessageReactionViewSet):
```python
class InteractionReactionViewSet(viewsets.ModelViewSet):
    serializer_class = InteractionReactionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "delete"]

    def get_queryset(self):
        return InteractionReaction.objects.filter(account=self.request.user)

    def create(self, request, *args, **kwargs):
        """Toggle: delete if exists, create if not."""
        interaction_id = request.data.get("interaction")
        emoji = request.data.get("emoji")
        existing = InteractionReaction.objects.filter(
            interaction_id=interaction_id,
            account=request.user,
            emoji=emoji,
        ).first()
        if existing:
            existing.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        # Need to get the interaction's timestamp for the denormalized FK
        interaction = Interaction.objects.filter(pk=interaction_id).first()
        if interaction is None:
            return Response(
                {"detail": "Interaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        InteractionReaction.objects.create(
            interaction=interaction,
            timestamp=interaction.timestamp,
            account=request.user,
            emoji=emoji,
        )
        return Response(status=status.HTTP_201_CREATED)
```

Register in urls.py:
```python
router.register(r"interaction-reactions", InteractionReactionViewSet, basename="interactionreaction")
```

Update InteractionViewSet.get_queryset() prefetch to include reactions:
```python
Prefetch(
    "reactions",
    queryset=InteractionReaction.objects.all(),
    to_attr="cached_reactions",
),
```

Add `"reactions"` to InteractionListSerializer.Meta.fields.

Tests: toggle reaction, reaction counts in serializer, reacted flag.

Commit: `feat(scenes): add InteractionReaction API with toggle and aggregation`

---

## Task 4: push_interaction() Service Function

**Files:**
- Modify: `src/world/scenes/interaction_services.py`

Add a new function that sends structured interaction data through Evennia's
WebSocket to all connected clients in the room:

```python
def push_interaction(interaction: Interaction) -> None:
    """Push a structured interaction payload to connected clients via WebSocket.

    Uses Evennia's msg() which routes through the WebSocket to connected
    web clients. The payload type 'interaction' becomes a new WS_MESSAGE_TYPE
    on the frontend.
    """
    persona = interaction.persona
    location = persona.character.location
    if location is None:
        return

    payload = {
        "id": interaction.pk,
        "persona": {
            "id": persona.pk,
            "name": persona.name,
            "thumbnail_url": persona.thumbnail_url or "",
        },
        "content": interaction.content,
        "mode": interaction.mode,
        "timestamp": interaction.timestamp.isoformat(),
        "scene_id": interaction.scene_id,
    }

    for obj in location.contents:
        try:
            obj.msg(interaction=((), payload))
        except (AttributeError, TypeError):
            continue
```

Note: `obj.msg(interaction=((), payload))` is Evennia's pattern for sending
typed messages. The first element of the tuple is args (empty), second is
kwargs (the payload). The key `interaction` becomes the message type that
the frontend WebSocket handler will match against.

Tests: mock obj.msg and verify payload structure, verify skip on no location.

Commit: `feat(scenes): add push_interaction() WebSocket delivery`

---

## Task 5: Wire push_interaction into record_interaction

**Files:**
- Modify: `src/world/scenes/interaction_services.py`
- Modify: `src/world/scenes/tests/test_interaction_services.py`

In `record_interaction()`, after `create_interaction()` returns a non-None result,
call `push_interaction()`:

```python
def record_interaction(...) -> Interaction | None:
    ...
    interaction = create_interaction(...)
    if interaction is not None:
        push_interaction(interaction)
    return interaction
```

Same for `record_whisper_interaction()`:
```python
def record_whisper_interaction(...) -> Interaction | None:
    ...
    interaction = create_interaction(...)
    if interaction is not None:
        push_interaction(interaction)
    return interaction
```

Update existing tests to account for the push call (mock it or verify it's called).

Commit: `feat(scenes): wire push_interaction into record_interaction`

---

## Task 6: Update Partition SQL for InteractionReaction

**Files:**
- Modify: `src/world/scenes/sql/partition_interaction_forward.sql`
- Modify: `src/world/scenes/sql/partition_interaction_reverse.sql`

Add composite FK constraint for InteractionReaction in the forward SQL:

```sql
ALTER TABLE scenes_interactionreaction
    ADD CONSTRAINT interactionreaction_interaction_fk
    FOREIGN KEY (interaction_id, "timestamp")
    REFERENCES scenes_interaction (id, "timestamp")
    ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX interactionreaction_ts_brin
    ON scenes_interactionreaction USING brin ("timestamp");
```

Add corresponding DROP in reverse SQL.

Note: The partition migration (0003) reads from these SQL files. Since the
InteractionReaction table is created by a newer migration (Task 1), the
partition migration runs first and won't find the table. The composite FK
constraint needs to go in a SEPARATE migration that runs AFTER both the
partition migration and the InteractionReaction creation.

Create a new migration: `src/world/scenes/migrations/0005_interactionreaction_partition_fk.py`
(or whatever the next number is) with RunSQL that adds the composite FK.

Commit: `feat(scenes): add partition composite FK for InteractionReaction`

---

## Task 7: Full Test Suite Pass

Run: `uv run arx test`
Fix any failures.
Run: `ruff check src/world/scenes/`

Commit: `fix(scenes): test and lint fixes for SceneMessage deprecation phase 1`

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | InteractionReaction model | `scenes/models.py` |
| 2 | Factory + admin | `scenes/factories.py`, `scenes/admin.py` |
| 3 | Serializer + ViewSet + URL | `interaction_serializers.py`, `interaction_views.py`, `urls.py` |
| 4 | push_interaction() | `interaction_services.py` |
| 5 | Wire into record_interaction | `interaction_services.py` |
| 6 | Partition FK | SQL files, new migration |
| 7 | Full test pass | All files |

### What's NOT in this plan (Phase 2 — frontend)
- WebSocket INTERACTION message type handler
- Interaction display component (replaces SceneMessages)
- SceneDetailPage dual mode (WebSocket for active, REST for history)
- Scene query functions for Interaction API
- Deduplication of raw TEXT vs structured INTERACTION

### What's NOT in this plan (Phase 3 — cleanup)
- Remove SceneMessage model
- Remove SceneMessageViewSet, serializer, factory
- Remove SceneMessageReaction model
- Remove old SceneMessages.tsx component
