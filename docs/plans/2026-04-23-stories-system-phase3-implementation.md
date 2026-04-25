# Stories System Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship real-time reactivity for the stories system: six mutation-time hooks that auto-flip beats when gameplay state changes, login catch-up as a safety net, and a general-purpose `world.narrative` app carrying `NarrativeMessage` deliveries (used by stories but broadly reusable for GM/Staff/automated IC messages).

**Architecture:** New `world.narrative` app with a `NarrativeMessage` + `NarrativeMessageDelivery` pair (characters receive messages via the join table — one message fans out to many recipients). Stories layers on top: beat completions and episode resolutions emit narrative messages through the app's service. Stories gains a `reactivity` service module with explicit entry points called by progression, achievements, conditions, and codex on mutation. Internal cascade on `resolve_episode` handles cross-story `STORY_AT_MILESTONE`. Login catch-up at `at_post_puppet` re-evaluates active stories and delivers any queued narrative messages.

**Tech Stack:** Django 4.x, DRF, PostgreSQL, SharedMemoryModel, FactoryBoy, Evennia test runner.

**Design Reference:** `docs/plans/2026-04-20-stories-system-design.md`
**Phase 1 plan (reference):** `docs/plans/2026-04-20-stories-system-phase1-implementation.md`
**Phase 2 plan (reference):** `docs/plans/2026-04-22-stories-system-phase2-implementation.md`

---

## Phase Scope

**In Phase 3 (this plan):**

### `world.narrative` app (new, general-purpose)
- `NarrativeMessage` — the message itself (body, ooc_note, category, sender, optional story/beat/episode FKs, sent_at)
- `NarrativeMessageDelivery` — join table (message FK, recipient CharacterSheet FK, delivered_at, acknowledged_at)
- `send_narrative_message(recipients, body, ...)` service — creates message + deliveries, real-time pushes to puppeted recipients, leaves offline for login delivery
- Login catch-up at `at_post_puppet` — delivers queued messages + marks delivered_at
- Backend only: read endpoint so `sheet.narrative_message_deliveries` is queryable via API. UI (inline-text display, messages-section of sheet) is deferred to frontend phase.

### Stories reactivity (the main Phase 3 feature)
- New `services/reactivity.py` module with explicit re-evaluation entry points:
  - `on_character_level_changed(sheet)` — called by progression
  - `on_achievement_earned(sheet, achievement)` — called by achievements
  - `on_condition_applied(sheet, condition_instance)` — called by conditions
  - `on_condition_expired(sheet, condition_template)` — called by conditions (covers the "story blocker lifted" case)
  - `on_codex_entry_unlocked(sheet, codex_entry)` — called by codex
  - Internal cascade — `resolve_episode` calls `on_story_advanced(story)` which re-evaluates any beats with `STORY_AT_MILESTONE` referencing that story across all scopes
- Cross-app wiring — each of the external systems (progression, achievements, conditions, codex) gets a one-line call to the corresponding reactivity hook at its mutation site
- Story-join snapshot — `StoryProgress` / `GroupStoryProgress` / `GlobalStoryProgress` creation services call `evaluate_auto_beats` once to catch retroactive matches (character already has the achievement when the story is created)
- Login catch-up for stories — re-evaluate active progress's auto-beats at `at_post_puppet` (safety net)
- "ANY member has it" semantics for GROUP/GLOBAL character-state predicates (ACHIEVEMENT_HELD / CONDITION_HELD / CODEX_ENTRY_UNLOCKED / CHARACTER_LEVEL_AT_LEAST) — iterate active members, SUCCESS on first match

### Stories → narrative integration
- Beat completions auto-emit a `NarrativeMessage` with `category=STORY` and `related_beat_completion` set
- Episode resolutions auto-emit a `NarrativeMessage` per participant with `category=STORY` and `related_episode_resolution` set
- Real-time push for online participants via `character.msg()` with a color tag so clients can style it
- No coupling between beat and message models beyond the optional FK — removes the "beat addendum" concept from Phase 2 discussion

### Smaller follow-ups
- Progression-side cache invalidation on `CharacterClassLevel` mutation — progression services call `sheet.invalidate_class_level_cache()` after mutations (follow-up from the Phase 1 review)

**Deferred beyond Phase 3:**
- React frontend — narrative inline display, messages-section of sheet UI, story log reader, player dashboard UI, GM queue UI, staff workload UI
- `MISSION_COMPLETE` predicate (blocked on missions system)
- Covenant leadership model
- Authoring UX polish beyond Django admin
- Era lifecycle tooling
- Dispute / withdrawal state transitions
- Player-facing "browse my narrative messages" endpoint beyond basic read — search, filter, pagination-UX polish are frontend concerns

---

## Conventions for this plan

Same as Phases 1-2 — don't re-explain:
- SharedMemoryModel for all concrete models
- Absolute imports only
- No JSON fields, TextChoices in `constants.py`, no signals
- `world.stories` + `world.narrative` in typed apps list — full type annotations
- `git -C <abs-path>`, never `gh` CLI, never `cd &&`
- `arx test <app> --keepdb` inner loop; fresh-DB run before commit
- Pre-commit hooks run on commit — fix and re-stage; never `--no-verify`
- Typed exceptions with `user_message` for API-facing errors
- Service functions take model instances or pks, never slugs
- **Canonical action-endpoint pattern from `src/world/stories/CLAUDE.md`**: permission classes for "who can call", input serializers for "what's valid", services receive validated data only. Do not regress.
- `Prefetch(..., to_attr=...)` against cached_property; never bare strings
- `try/except RelatedObjectDoesNotExist` over `getattr(obj, "reverse_accessor", None)`
- `match/case` over chained `if x == ...` on the same value

---

## Execution structure — Waves

- **Wave 1** — `world.narrative` app foundation (models, services, tests, admin, basic API read)
- **Wave 2** — Stories reactivity service module + story-join snapshot
- **Wave 3** — External mutation hook wiring (progression, achievements, conditions, codex — scope-creep is fine per user policy; touch each app)
- **Wave 4** — Internal cascade on `resolve_episode`
- **Wave 5** — "ANY member has it" auto-evaluation for GROUP/GLOBAL
- **Wave 6** — Stories → narrative integration (beat completions + episode resolutions emit NarrativeMessages)
- **Wave 7** — Login catch-up (`at_post_puppet` hook, per-progress and per-delivery timestamps)
- **Wave 8** — Progression-side cache invalidation follow-up
- **Wave 9** — End-to-end integration test + docs

---

## Wave 1 — `world.narrative` app foundation

### Task 1.1: Bootstrap `world.narrative` app

**Files:**
- Create: `src/world/narrative/__init__.py`
- Create: `src/world/narrative/apps.py`
- Create: `src/world/narrative/constants.py`
- Create: `src/world/narrative/models.py` (empty for now)
- Create: `src/world/narrative/admin.py` (empty for now)
- Create: `src/world/narrative/tests/__init__.py`
- Modify: `src/server/conf/settings.py` (or wherever `INSTALLED_APPS` is) — register the new app
- Modify: `pyproject.toml` — add `world.narrative` to `[tool.ty.src].include`
- Modify: `tools/check_type_annotations.py` — add `world.narrative` to the typed apps list (per CLAUDE.md, keep these in sync)

**Step 1: `apps.py`**
```python
# src/world/narrative/apps.py
from django.apps import AppConfig


class NarrativeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.narrative"
    label = "narrative"
```

**Step 2: `constants.py`**
```python
# src/world/narrative/constants.py
from django.db import models


class NarrativeCategory(models.TextChoices):
    STORY = "story", "Story update"
    ATMOSPHERE = "atmosphere", "Atmosphere"
    VISIONS = "visions", "Visions"
    HAPPENSTANCE = "happenstance", "Happenstance"
    SYSTEM = "system", "System"
```

**Step 3: Register the app**

Find the settings file (likely `src/server/conf/settings.py` or `server/conf/settings.py`). Add `"world.narrative"` to `INSTALLED_APPS` (after the other `world.*` apps to keep the list tidy).

**Step 4: Register typed-apps entries**

Edit `pyproject.toml`:
```toml
[tool.ty.src]
include = [
    # ... existing entries
    "src/world/narrative",
]
```

Edit `tools/check_type_annotations.py` — find the list of typed apps (mentioned in CLAUDE.md as maintained in that file), add `world.narrative`.

**Step 5: Smoke test the app**

Run: `uv run arx manage migrate` (no migrations yet, should be a no-op).
Run: `uv run arx test world.narrative --keepdb` (no tests yet; should say 0 tests, pass).

**Step 6: Commit**
```
git -C /c/Users/apost/PycharmProjects/arxii add src/world/narrative/ src/server/conf/settings.py pyproject.toml tools/check_type_annotations.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "feat(narrative): bootstrap new world.narrative app

General-purpose app for IC messages delivered to characters — GM/Staff/
system-sourced. Used by stories for beat + episode resolution informs;
also available for atmosphere/visions/happenstance messages unrelated
to stories.

NarrativeCategory TextChoices: STORY, ATMOSPHERE, VISIONS, HAPPENSTANCE,
SYSTEM. Models follow in Task 1.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 1.2: `NarrativeMessage` + `NarrativeMessageDelivery` models

**Files:**
- Modify: `src/world/narrative/models.py`
- Create: `src/world/narrative/factories.py`
- Modify: `src/world/narrative/admin.py`
- Create: `src/world/narrative/tests/test_models.py`

**Models:**
```python
# src/world/narrative/models.py
from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.narrative.constants import NarrativeCategory


class NarrativeMessage(SharedMemoryModel):
    """A single IC message delivered to one or more characters.

    The message itself is immutable after send. Per-recipient state
    (delivered, acknowledged) lives on NarrativeMessageDelivery.
    """

    body = models.TextField(
        help_text="IC content shown to recipients.",
    )
    ooc_note = models.TextField(
        blank=True,
        help_text=(
            "OOC context visible to staff and GMs with access to the "
            "recipient's character — explains why this message was sent, "
            "what it's about, etc. Not shown to players in-character."
        ),
    )
    category = models.CharField(
        max_length=20,
        choices=NarrativeCategory.choices,
    )
    sender_account = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages_sent",
        help_text="Null = automated/system-sourced.",
    )

    # Optional context FKs — populated when a narrative message is produced
    # by the stories system. Consumers of the message can use these to
    # render story-log entries, link to the related story, etc.
    related_story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_beat_completion = models.ForeignKey(
        "stories.BeatCompletion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_episode_resolution = models.ForeignKey(
        "stories.EpisodeResolution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )

    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "-sent_at"]),
            models.Index(fields=["sender_account", "-sent_at"]),
        ]

    def __str__(self) -> str:
        preview = self.body[:40] + ("..." if len(self.body) > 40 else "")
        return f"NarrativeMessage({self.category}) {preview}"


class NarrativeMessageDelivery(SharedMemoryModel):
    """Per-recipient delivery state for a NarrativeMessage.

    One row per (message, character_sheet) pair. A single message can
    fan out to many recipients (e.g., a GM sends a covenant-wide message
    to 5 of 8 members — that's one NarrativeMessage and 5 Delivery rows).
    """

    message = models.ForeignKey(
        NarrativeMessage,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    recipient_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="narrative_message_deliveries",
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the message was pushed to the character's puppeted "
            "session. Null until online delivery or login catch-up delivers it."
        ),
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the player acknowledged having seen the message. "
            "Null until the player marks it read. Used to distinguish 'unread' "
            "in future UI work."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "recipient_character_sheet"],
                name="unique_delivery_per_message_per_recipient",
            )
        ]
        indexes = [
            models.Index(fields=["recipient_character_sheet", "delivered_at"]),
            models.Index(fields=["recipient_character_sheet", "acknowledged_at"]),
        ]

    def __str__(self) -> str:
        state = "delivered" if self.delivered_at else "queued"
        return f"NarrativeMessageDelivery(msg=#{self.message_id}, sheet=#{self.recipient_character_sheet_id}, {state})"
```

**Factories:**
```python
# src/world/narrative/factories.py
import factory
from factory.django import DjangoModelFactory

from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery


class NarrativeMessageFactory(DjangoModelFactory):
    class Meta:
        model = NarrativeMessage

    body = factory.Faker("paragraph")
    ooc_note = ""
    category = NarrativeCategory.STORY
    sender_account = None
    related_story = None
    related_beat_completion = None
    related_episode_resolution = None


class NarrativeMessageDeliveryFactory(DjangoModelFactory):
    class Meta:
        model = NarrativeMessageDelivery

    message = factory.SubFactory(NarrativeMessageFactory)
    recipient_character_sheet = factory.SubFactory(CharacterSheetFactory)
    delivered_at = None
    acknowledged_at = None
```

**Admin:**
```python
# src/world/narrative/admin.py
from django.contrib import admin

from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery


class NarrativeMessageDeliveryInline(admin.TabularInline):
    model = NarrativeMessageDelivery
    extra = 0
    raw_id_fields = ("recipient_character_sheet",)
    readonly_fields = ("delivered_at", "acknowledged_at")


@admin.register(NarrativeMessage)
class NarrativeMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "sender_account", "related_story", "sent_at")
    list_filter = ("category",)
    search_fields = ("body", "ooc_note")
    readonly_fields = ("sent_at",)
    raw_id_fields = (
        "sender_account",
        "related_story",
        "related_beat_completion",
        "related_episode_resolution",
    )
    inlines = [NarrativeMessageDeliveryInline]


@admin.register(NarrativeMessageDelivery)
class NarrativeMessageDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "recipient_character_sheet", "delivered_at", "acknowledged_at")
    list_filter = ("delivered_at", "acknowledged_at")
    raw_id_fields = ("message", "recipient_character_sheet")
    readonly_fields = ("delivered_at", "acknowledged_at")
```

**Tests:**
```python
# src/world/narrative/tests/test_models.py
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from world.narrative.constants import NarrativeCategory
from world.narrative.factories import NarrativeMessageDeliveryFactory, NarrativeMessageFactory


class NarrativeMessageTests(TestCase):
    def test_factory_creates_message(self) -> None:
        msg = NarrativeMessageFactory()
        self.assertIsNotNone(msg.body)
        self.assertEqual(msg.category, NarrativeCategory.STORY)
        self.assertIsNone(msg.sender_account)

    def test_category_choices(self) -> None:
        for category in NarrativeCategory.values:
            msg = NarrativeMessageFactory(category=category)
            self.assertEqual(msg.category, category)

    def test_ooc_note_is_blank_by_default(self) -> None:
        msg = NarrativeMessageFactory()
        self.assertEqual(msg.ooc_note, "")


class NarrativeMessageDeliveryTests(TestCase):
    def test_delivery_starts_unread_and_undelivered(self) -> None:
        delivery = NarrativeMessageDeliveryFactory()
        self.assertIsNone(delivery.delivered_at)
        self.assertIsNone(delivery.acknowledged_at)

    def test_message_can_fan_out_to_multiple_recipients(self) -> None:
        msg = NarrativeMessageFactory()
        d1 = NarrativeMessageDeliveryFactory(message=msg)
        d2 = NarrativeMessageDeliveryFactory(message=msg)
        self.assertEqual(msg.deliveries.count(), 2)
        self.assertNotEqual(d1.recipient_character_sheet, d2.recipient_character_sheet)


class NarrativeMessageDeliveryUniqueTests(TransactionTestCase):
    def test_unique_per_message_per_recipient(self) -> None:
        msg = NarrativeMessageFactory()
        d1 = NarrativeMessageDeliveryFactory(message=msg)
        with self.assertRaises(IntegrityError):
            NarrativeMessageDeliveryFactory(
                message=msg,
                recipient_character_sheet=d1.recipient_character_sheet,
            )
```

**Migration, tests, commit:**
```
uv run arx manage makemigrations narrative
uv run arx manage migrate
uv run arx test world.narrative --keepdb
echo "yes" | uv run arx test world.narrative
```

Commit:
```
feat(narrative): add NarrativeMessage and NarrativeMessageDelivery models

One message can fan out to many characters via NarrativeMessageDelivery
rows (e.g., GM sends a covenant message to 5 of 8 members — one message,
five delivery rows). Message carries IC body, OOC note visible to
staff/GMs, category, optional sender (null for automated), and optional
related_story/beat_completion/episode_resolution FKs for stories
integration.

Delivery tracks per-recipient delivered_at and acknowledged_at
timestamps for online-vs-queued delivery logic and future unread UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 1.3: `send_narrative_message` service

**Files:**
- Create: `src/world/narrative/services.py`
- Create: `src/world/narrative/tests/test_services.py`

**Service:**
```python
# src/world/narrative/services.py
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery

if TYPE_CHECKING:
    from accounts.models import AccountDB
    from world.character_sheets.models import CharacterSheet
    from world.stories.models import (
        BeatCompletion,
        EpisodeResolution,
        Story,
    )


def send_narrative_message(
    *,
    recipients: Iterable["CharacterSheet"],
    body: str,
    category: str,
    sender_account: "AccountDB | None" = None,
    ooc_note: str = "",
    related_story: "Story | None" = None,
    related_beat_completion: "BeatCompletion | None" = None,
    related_episode_resolution: "EpisodeResolution | None" = None,
) -> NarrativeMessage:
    """Create a NarrativeMessage and fan out deliveries to each recipient.

    Real-time push to puppeted recipients via character.msg(); deliveries
    to offline recipients stay unmarked (delivered_at=None) until the
    recipient's next login triggers catch-up delivery.

    Returns the NarrativeMessage instance.
    """
    recipients = list(recipients)
    with transaction.atomic():
        msg = NarrativeMessage.objects.create(
            body=body,
            ooc_note=ooc_note,
            category=category,
            sender_account=sender_account,
            related_story=related_story,
            related_beat_completion=related_beat_completion,
            related_episode_resolution=related_episode_resolution,
        )
        deliveries = [
            NarrativeMessageDelivery(message=msg, recipient_character_sheet=sheet)
            for sheet in recipients
        ]
        NarrativeMessageDelivery.objects.bulk_create(deliveries)

    # Online push — after commit so any listener sees consistent state.
    for delivery in NarrativeMessageDelivery.objects.filter(message=msg).select_related(
        "recipient_character_sheet__character",
    ):
        _push_to_online_recipient(delivery)

    return msg


def _push_to_online_recipient(delivery: NarrativeMessageDelivery) -> None:
    """Push the message to the recipient's puppeted session if online.

    Marks delivered_at=now when the push succeeds. If the character isn't
    currently puppeted, leaves the delivery queued for login catch-up.
    """
    character = delivery.recipient_character_sheet.character
    sessions = list(character.sessions.all())
    if not sessions:
        return  # offline; leave for catch-up
    formatted = _format_message_for_display(delivery.message)
    character.msg(formatted, type="narrative")
    delivery.delivered_at = timezone.now()
    delivery.save(update_fields=["delivered_at"])


def _format_message_for_display(message: NarrativeMessage) -> str:
    """Format a message for in-text display in a connected session.

    Adds a distinct color tag so clients can style it apart from normal
    messages. The frontend roadmap calls for light red for narrative
    messages — Evennia color code |R.

    The OOC note is NOT included in the player-facing text; it's visible
    only through the staff/GM admin and API surfaces.
    """
    return f"|R[NARRATIVE]|n {message.body}"
```

**Tests:**
```python
# src/world/narrative/tests/test_services.py
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.narrative.services import send_narrative_message


class SendNarrativeMessageTests(TestCase):
    def test_creates_message_with_delivery_per_recipient(self) -> None:
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()

        msg = send_narrative_message(
            recipients=[sheet_a, sheet_b],
            body="Dark clouds gather over the city.",
            category=NarrativeCategory.ATMOSPHERE,
        )

        self.assertIsNotNone(msg.pk)
        self.assertEqual(msg.deliveries.count(), 2)
        recipients = {d.recipient_character_sheet for d in msg.deliveries.all()}
        self.assertEqual(recipients, {sheet_a, sheet_b})

    def test_offline_recipient_delivery_remains_queued(self) -> None:
        sheet = CharacterSheetFactory()  # factory does not puppet the character
        msg = send_narrative_message(
            recipients=[sheet],
            body="A whisper on the wind.",
            category=NarrativeCategory.VISIONS,
        )
        delivery = msg.deliveries.get(recipient_character_sheet=sheet)
        self.assertIsNone(delivery.delivered_at)

    def test_empty_recipients_creates_message_with_no_deliveries(self) -> None:
        msg = send_narrative_message(
            recipients=[],
            body="System-level notice without recipients (edge case).",
            category=NarrativeCategory.SYSTEM,
        )
        self.assertEqual(msg.deliveries.count(), 0)

    def test_context_fks_persist(self) -> None:
        sheet = CharacterSheetFactory()
        msg = send_narrative_message(
            recipients=[sheet],
            body="A beat resolved.",
            category=NarrativeCategory.STORY,
        )
        self.assertEqual(msg.category, NarrativeCategory.STORY)
        self.assertIsNone(msg.related_story)
```

Tests for online push are tricky because Evennia character sessions need actual puppeting — defer the online-push happy-path test to Wave 7 integration or cover with a unit test that mocks the sessions accessor.

Commit:
```
feat(narrative): send_narrative_message service with online push

Creates a NarrativeMessage and fans out NarrativeMessageDelivery rows
per recipient in one atomic transaction. After commit, pushes to any
puppeted recipients via character.msg() tagged with a distinct color
(|R for light red, per the frontend roadmap). Offline recipients'
deliveries remain queued with delivered_at=null for login catch-up.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 1.4: Read API for narrative messages

**Files:**
- Create: `src/world/narrative/serializers.py`
- Create: `src/world/narrative/views.py`
- Create: `src/world/narrative/permissions.py`
- Create: `src/world/narrative/filters.py`
- Create: `src/world/narrative/urls.py`
- Modify: root URL conf to include `world.narrative.urls`
- Create: `src/world/narrative/tests/test_views.py`

**Serializers (backend only — no render/UX polish):**
```python
class NarrativeMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = NarrativeMessage
        fields = [
            "id", "body", "category", "sender_account",
            "related_story", "related_beat_completion", "related_episode_resolution",
            "sent_at",
        ]
        read_only_fields = fields


class NarrativeMessageWithOOCSerializer(NarrativeMessageSerializer):
    """Variant that includes ooc_note — for staff/GM contexts."""
    class Meta(NarrativeMessageSerializer.Meta):
        fields = NarrativeMessageSerializer.Meta.fields + ["ooc_note"]


class NarrativeMessageDeliverySerializer(serializers.ModelSerializer):
    message = NarrativeMessageSerializer(read_only=True)

    class Meta:
        model = NarrativeMessageDelivery
        fields = ["id", "message", "delivered_at", "acknowledged_at"]
        read_only_fields = fields
```

**Permissions:**
```python
class IsDeliveryRecipientOrStaff(BasePermission):
    """Recipients read their own deliveries; staff reads any."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.recipient_character_sheet.character.db_account == request.user
```

**Filters:** standard DRF filterset — by category, by related_story, by acknowledged/unacknowledged.

**Views:**
- `MyNarrativeMessagesView` — lists deliveries where the requesting account is the recipient's account. Paginated.
- `MarkNarrativeMessageAcknowledgedView` — POST action that sets `acknowledged_at=now()` on a delivery; permission: recipient only.

Intentionally NOT included in Phase 3:
- Sender endpoint for GM/Staff to compose ad-hoc messages — defer until the messages-section-of-sheet UI lands (frontend phase)
- Search/filter UX polish — frontend phase

Tests cover permission matrix + basic read + acknowledge action.

Commit:
```
feat(narrative-api): read endpoint for recipient's narrative messages

GET /api/narrative/my-messages/ — paginated list of the requesting
account's character's deliveries. POST /api/narrative/deliveries/{id}/
acknowledge/ marks a delivery read. Sender composition UI deferred to
frontend phase.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 2 — Stories reactivity service module + story-join snapshot

### Task 2.1: `stories.services.reactivity` scaffolding

**Files:**
- Create: `src/world/stories/services/reactivity.py`
- Create: `src/world/stories/tests/test_services_reactivity.py`

The module exposes public entry points that external apps (progression, achievements, conditions, codex) will call. Each entry point scopes re-evaluation to the affected character's active stories.

```python
# src/world/stories/services/reactivity.py
"""Reactivity hooks called by external systems on character state change.

External apps (progression, achievements, conditions, codex) call the
appropriate entry point after they mutate character state. The hooks
scope re-evaluation to the affected character's active stories and
flip any now-satisfied beats.

Pattern: each hook iterates the character's active stories across all
three scopes (CHARACTER / GROUP / GLOBAL) and calls evaluate_auto_beats
on each. evaluate_auto_beats handles the scope-dispatch internally.

This module has no direct knowledge of the triggering change — callers
pass the character_sheet and whichever domain model mutated. Hooks
re-evaluate all relevant predicate types even if the trigger was more
specific (cheaper to re-evaluate a handful of beats than to route
per-predicate-type).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.services.beats import evaluate_auto_beats

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def on_character_state_changed(sheet: "CharacterSheet") -> None:
    """Re-evaluate auto-beats across this character's active stories.

    General-purpose entry point — callable from any mutation site that
    could affect a character-state predicate (level, achievement,
    condition, codex). Specific entry points below just delegate here
    for now, but exist for clarity at call sites and to allow future
    per-trigger optimization.
    """
    for progress in _active_progress_for_character(sheet):
        evaluate_auto_beats(progress)


def on_character_level_changed(sheet: "CharacterSheet") -> None:
    """Called after progression updates CharacterClassLevel."""
    # Invalidate cached level first (follow-up from Phase 1 review;
    # progression will do this too once Wave 8 lands, but doing it here
    # is defensive and cheap).
    sheet.invalidate_class_level_cache()
    on_character_state_changed(sheet)


def on_achievement_earned(sheet: "CharacterSheet", achievement) -> None:
    """Called after achievements service grants an achievement."""
    # Invalidate cached achievements if such a cache exists (check
    # CharacterSheet model for cached_achievements_held — invalidate
    # the same way as class_level_cache).
    _invalidate_cache_if_present(sheet, "cached_achievements_held")
    on_character_state_changed(sheet)


def on_condition_applied(sheet: "CharacterSheet", condition_instance) -> None:
    """Called after conditions service attaches a ConditionInstance."""
    _invalidate_cache_if_present(sheet, "cached_active_condition_templates")
    on_character_state_changed(sheet)


def on_condition_expired(sheet: "CharacterSheet", condition_template) -> None:
    """Called when a ConditionInstance expires or is removed.

    Covers the 'story can't progress while crippled' use case: when the
    condition lifts, re-evaluate in case a beat's predicate (including
    future inverse predicates) has flipped.
    """
    _invalidate_cache_if_present(sheet, "cached_active_condition_templates")
    on_character_state_changed(sheet)


def on_codex_entry_unlocked(sheet: "CharacterSheet", codex_entry) -> None:
    """Called after codex service unlocks a CodexEntry for a character."""
    # Codex unlocks are keyed on RosterEntry per Phase 2 design note;
    # the cached_codex_entries_unlocked cached_property (if it exists)
    # is on the RosterEntry, not the sheet. Invalidate defensively.
    _invalidate_cache_if_present(sheet, "cached_codex_entries_unlocked")
    on_character_state_changed(sheet)


def _active_progress_for_character(sheet: "CharacterSheet"):
    """Yield all active progress records the character participates in.

    CHARACTER scope: StoryProgress where character_sheet=sheet.
    GROUP scope: GroupStoryProgress for any GMTable the character is a
        member of (via GMTableMembership).
    GLOBAL scope: GlobalStoryProgress for any story the character has
        a StoryParticipation on.
    """
    from world.stories.models import (  # noqa: PLC0415
        GlobalStoryProgress,
        GroupStoryProgress,
        StoryProgress,
    )

    # CHARACTER
    yield from StoryProgress.objects.filter(
        character_sheet=sheet,
        is_active=True,
    )

    # GROUP — any GMTable the sheet's character is a member of
    yield from GroupStoryProgress.objects.filter(
        gm_table__memberships__persona__character_sheet=sheet,
        gm_table__memberships__is_active=True,
        is_active=True,
    ).distinct()

    # GLOBAL — any participating story
    yield from GlobalStoryProgress.objects.filter(
        story__participants__character=sheet.character,
        story__participants__is_active=True,
        is_active=True,
    ).distinct()


def _invalidate_cache_if_present(sheet, attr_name: str) -> None:
    """Safely delete a cached_property's stored value if present.

    Done via __dict__.pop to avoid raising AttributeError if the
    cached_property hasn't been accessed yet.
    """
    sheet.__dict__.pop(attr_name, None)
```

**Tests:**
- `test_on_character_level_changed_reevaluates_character_scope_beats` — CHARACTER_LEVEL_AT_LEAST beat, sheet on a CHARACTER-scope story, level up satisfies it
- `test_on_achievement_earned_reevaluates_group_scope_beats` — ACHIEVEMENT_HELD on a GROUP-scope story the sheet is a member of
- `test_on_codex_entry_unlocked_reevaluates_global_scope_beats` — CODEX_ENTRY_UNLOCKED on a GLOBAL-scope story the sheet has participation on
- `test_on_condition_expired_reevaluates` — no predicate flips yet in Phase 3 (only CONDITION_HELD exists, not CONDITION_NOT_HELD), but the service should execute without error and not re-flip an already-SUCCESS beat
- `test_hook_is_idempotent` — calling twice does not create duplicate BeatCompletion rows
- `test_no_active_progress_is_a_noop` — sheet on no stories, no error

Commit:
```
feat(stories-reactivity): add reactivity service module with five entry points

on_character_level_changed / on_achievement_earned /
on_condition_applied / on_condition_expired /
on_codex_entry_unlocked — each invalidates the relevant cached_property
on CharacterSheet and re-evaluates auto-beats across the character's
active stories in all three scopes. Delegates to evaluate_auto_beats;
no new predicate logic. Idempotent.

Wiring into external apps (progression, achievements, conditions, codex)
comes in Wave 3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 2.2: Story-join snapshot trigger

**Files:**
- Modify: `src/world/stories/services/progress.py` — add `create_character_progress(story, character_sheet)` helper that creates + immediately evaluates
- Modify: wherever progress records are created in existing services (e.g., the CG finalization hook from Phase 2) — swap to use the new helper
- Create or extend: tests that assert retroactive beats auto-satisfy on creation

Service addition:
```python
def create_character_progress(
    *,
    story: "Story",
    character_sheet: "CharacterSheet",
    current_episode=None,
) -> "StoryProgress":
    """Create a StoryProgress and immediately evaluate auto-beats.

    Catches retroactive matches — e.g., a character already has the
    required achievement when the story is created. Without the
    snapshot, the beat would stay UNSATISFIED until some unrelated
    trigger fires.
    """
    from world.stories.models import StoryProgress  # noqa: PLC0415
    from world.stories.services.beats import evaluate_auto_beats  # noqa: PLC0415

    progress = StoryProgress.objects.create(
        story=story,
        character_sheet=character_sheet,
        current_episode=current_episode,
    )
    evaluate_auto_beats(progress)
    return progress
```

Parallel helpers `create_group_progress(story, gm_table, ...)` and `create_global_progress(story, ...)` for the other two scopes.

Update `finalize_gm_character` in `src/world/character_creation/services.py` to use `create_character_progress` instead of `StoryProgress.objects.create`.

Test: a character already has an achievement → a new story is created with an ACHIEVEMENT_HELD beat referencing that achievement → after `create_character_progress`, the beat is already SUCCESS.

Commit:
```
feat(stories): story-join snapshot — evaluate auto-beats on progress creation

New create_character_progress / create_group_progress /
create_global_progress helpers in services/progress.py. Each creates
the progress row and immediately calls evaluate_auto_beats to catch
retroactive matches (character already has the achievement when the
story is created).

finalize_gm_character updated to use create_character_progress.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 3 — External mutation hook wiring

Each of these tasks wires a single external app into the reactivity module. Scope-creep into other apps is acceptable per project policy. Pattern per task:

1. Find the canonical mutation site in the target app (grep for `.create(character=...)`, `.save()` on the relevant model, etc.)
2. After the mutation, call the relevant reactivity hook — resolve `sheet` from the mutated object if needed
3. Add a test in the target app's test suite that exercises the cross-app hook (create mutation, assert story beat flipped)

### Task 3.1: Progression → stories (level-up hook)

Find the service(s) that create / update `CharacterClassLevel` in `src/world/progression/` or `src/world/classes/`. From Phase 2 review notes, there currently is NO production level-up service — the Wave 8 progression-side cache invalidation follow-up remains pending. If no service exists, this task gets blocked or must build one. Investigate first; if truly no production mutation site exists, skip Task 3.1 with a note and continue (the reactivity hook still exists and test coverage is sufficient — future progression work will call it).

If a service exists, add `on_character_level_changed(sheet)` at the end:
```python
from world.stories.services.reactivity import on_character_level_changed
# ... after mutating CharacterClassLevel
on_character_level_changed(sheet)
```

Commit:
```
feat(progression): wire level-up to stories reactivity

Service-layer level mutations now call stories.services.reactivity.
on_character_level_changed after the CharacterClassLevel save. The
stories system re-evaluates CHARACTER_LEVEL_AT_LEAST beats across the
character's active stories without needing to touch the reactivity
module from progression code.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 3.2: Achievements → stories

Find the service in `src/world/achievements/` that awards an achievement (likely creates an `AchievementEarned` or similar record). Add `on_achievement_earned(sheet, achievement)` at the mutation site.

Cross-app test: earn an achievement, assert the corresponding beat flips.

Commit:
```
feat(achievements): wire achievement earning to stories reactivity
```

---

### Task 3.3: Conditions applied → stories

Find the `ConditionInstance` creation site in `src/world/conditions/services.py`. Add `on_condition_applied(sheet, condition_instance)` after creation.

Commit:
```
feat(conditions): wire condition application to stories reactivity
```

---

### Task 3.4: Conditions expired → stories

Find where `ConditionInstance` is expired / removed (likely a cron or explicit service function). Call `on_condition_expired(sheet, condition_template)` at removal.

Note: no current predicate type uses condition-expiry-as-SUCCESS (CONDITION_HELD is SUCCESS-on-presence). The hook exists so future predicates (e.g., a hypothetical `CONDITION_NOT_HELD` or the "blocker lifted" pattern from the design discussion) have the integration point.

Commit:
```
feat(conditions): wire condition expiry to stories reactivity
```

---

### Task 3.5: Codex unlock → stories

Find the codex service that creates `CharacterCodexKnowledge` (keyed on RosterEntry per Phase 2 note). Add `on_codex_entry_unlocked(sheet, codex_entry)` after creation. Resolve `sheet` from the RosterEntry (tenure.character_sheet or whichever reverse relation applies).

Commit:
```
feat(codex): wire codex unlock to stories reactivity
```

---

## Wave 4 — Internal cascade on `resolve_episode`

### Task 4.1: STORY_AT_MILESTONE cascade

**Files:**
- Modify: `src/world/stories/services/episodes.py` — after `resolve_episode` advances a story, cascade to re-evaluate beats referencing it
- Modify: `src/world/stories/services/reactivity.py` — add `on_story_advanced(story)` entry point
- Modify: tests

```python
# services/reactivity.py
def on_story_advanced(story: "Story") -> None:
    """Re-evaluate any beats referencing this story via STORY_AT_MILESTONE.

    Called internally from resolve_episode after the progression advances.
    Finds every Beat with predicate_type=STORY_AT_MILESTONE and
    referenced_story=story, then walks to each beat's parent
    progress(es) to call evaluate_auto_beats scoped to that progress's
    current episode. (Only beats in the current episode of a progress
    are live candidates — older episodes' beats are historical.)
    """
    from world.stories.constants import BeatPredicateType  # noqa: PLC0415
    from world.stories.models import Beat  # noqa: PLC0415

    candidate_beats = Beat.objects.filter(
        predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
        referenced_story=story,
    ).select_related("episode__chapter__story")

    # For each candidate, find any progress currently on that beat's episode.
    seen_progress = set()
    for beat in candidate_beats:
        beat_story = beat.episode.chapter.story
        for progress in _active_progress_for_story(beat_story):
            if progress.current_episode_id != beat.episode_id:
                continue
            if progress.pk in seen_progress:
                continue
            seen_progress.add(progress.pk)
            evaluate_auto_beats(progress)


def _active_progress_for_story(story):
    """Yield all active progress records for a story, dispatching on scope."""
    from world.stories.constants import StoryScope  # noqa: PLC0415
    match story.scope:
        case StoryScope.CHARACTER:
            yield from story.progress_records.filter(is_active=True)
        case StoryScope.GROUP:
            yield from story.group_progress_records.filter(is_active=True)
        case StoryScope.GLOBAL:
            try:
                yield story.global_progress
            except story.DoesNotExist:  # actually GlobalStoryProgress.DoesNotExist
                pass
```

In `resolve_episode`, at the end, call `on_story_advanced(progress.story)` after the EpisodeResolution is committed and progress is advanced.

Test: Story A has a beat with STORY_AT_MILESTONE referencing Story B at CHAPTER_REACHED=Chapter 2. Both stories active. Story B advances to Chapter 2 via resolve_episode. Assert Story A's beat auto-flipped (without an explicit external trigger).

Commit:
```
feat(stories): internal cascade re-evaluates STORY_AT_MILESTONE beats

resolve_episode now calls on_story_advanced(story) after committing the
EpisodeResolution. The hook scans beats referencing the advanced story
and re-evaluates any progress currently sitting on those beats'
episodes. Closes the "cross-story gate auto-clears" design requirement.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 5 — "ANY member has it" auto-evaluation for GROUP/GLOBAL

### Task 5.1: Expand `_evaluate_predicate` to iterate members for GROUP/GLOBAL

**Files:**
- Modify: `src/world/stories/services/beats.py` — update `_evaluate_predicate` and `_evaluate_predicate_no_sheet` to dispatch on scope
- Modify: tests

Current behavior: `_evaluate_predicate_no_sheet` returns UNSATISFIED for character-state predicates in GROUP/GLOBAL scope. New behavior: iterate the group's active members (GROUP) or the story's StoryParticipation members (GLOBAL) and return SUCCESS on first match.

```python
def _evaluate_predicate_no_sheet(beat: Beat) -> BeatOutcome:
    """For GROUP/GLOBAL scope beats, check if any member satisfies."""
    match beat.predicate_type:
        case BeatPredicateType.ACHIEVEMENT_HELD:
            return _any_member_has_achievement(beat)
        case BeatPredicateType.CONDITION_HELD:
            return _any_member_has_condition(beat)
        case BeatPredicateType.CODEX_ENTRY_UNLOCKED:
            return _any_member_has_codex_entry(beat)
        case BeatPredicateType.CHARACTER_LEVEL_AT_LEAST:
            return _any_member_at_level(beat)
        case _:
            return BeatOutcome.UNSATISFIED


def _any_member_has_achievement(beat) -> BeatOutcome:
    for sheet in _members_for_beat(beat):
        if beat.required_achievement in sheet.cached_achievements_held:
            return BeatOutcome.SUCCESS
    return BeatOutcome.UNSATISFIED


# ... similar for condition, codex, level


def _members_for_beat(beat):
    """Resolve active members of the scope this beat lives under.

    CHARACTER scope: single character_sheet on the story.
    GROUP scope: active GMTableMembership personas' character_sheets.
    GLOBAL scope: StoryParticipation characters (mapped to sheets).
    """
    from world.stories.constants import StoryScope  # noqa: PLC0415
    story = beat.episode.chapter.story
    match story.scope:
        case StoryScope.CHARACTER:
            if story.character_sheet_id:
                yield story.character_sheet
        case StoryScope.GROUP:
            # Walk active progress records, then their GMTable memberships
            for progress in story.group_progress_records.filter(is_active=True):
                for membership in progress.gm_table.memberships.filter(is_active=True):
                    yield membership.persona.character_sheet
        case StoryScope.GLOBAL:
            for participation in story.participants.filter(is_active=True):
                # StoryParticipation.character is ObjectDB; walk to sheet
                sheet = getattr(participation.character, "sheet", None)  # adjust accessor
                if sheet is not None:
                    yield sheet
```

Adjust reverse-accessor walks based on actual field names after reading the existing models.

**Important:** `SUCCESS` is sticky. If a member has the achievement today and leaves the group tomorrow, the beat stays SUCCESS. Only count *current* members when UNSATISFIED — don't un-flip once SUCCESS.

Tests:
- `test_group_scope_achievement_flips_when_any_member_has_it`
- `test_group_scope_achievement_stays_unsatisfied_when_no_member_has_it`
- `test_global_scope_condition_flips_when_any_participant_has_it`
- `test_success_is_sticky_when_member_leaves`

Commit:
```
feat(stories): GROUP/GLOBAL character-state predicates auto-evaluate

ACHIEVEMENT_HELD, CONDITION_HELD, CODEX_ENTRY_UNLOCKED, and
CHARACTER_LEVEL_AT_LEAST now auto-detect for GROUP/GLOBAL scope using
'ANY member has it' semantics — the beat flips SUCCESS when any active
group member (GROUP) or story participant (GLOBAL) satisfies the
criterion. 'ALL members' use cases stay GM-marked for the narrative
checkpoint.

Matches the Phase 3 roadmap decision recorded on stories-phase-2.
SUCCESS is sticky — a member leaving the group doesn't un-flip a beat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 6 — Stories → narrative integration

### Task 6.1: Beat completions emit NarrativeMessages

**Files:**
- Modify: `src/world/stories/services/beats.py` — after creating a BeatCompletion, call `send_narrative_message` with the beat's resolution text
- Modify: `src/world/stories/services/scheduling.py` — same hook on aggregate threshold crossing
- Modify: tests

```python
# Inside _evaluate_and_record_beat, after BeatCompletion.objects.create(...):
from world.narrative.services import send_narrative_message  # noqa: PLC0415
from world.narrative.constants import NarrativeCategory  # noqa: PLC0415

send_narrative_message(
    recipients=_recipients_for_beat(beat, progress),
    body=beat.player_resolution_text or _default_beat_completion_text(beat),
    category=NarrativeCategory.STORY,
    related_story=beat.episode.chapter.story,
    related_beat_completion=completion,
)
```

Where `_recipients_for_beat(beat, progress)` resolves per scope:
- CHARACTER: `[progress.character_sheet]`
- GROUP: all active members of `progress.gm_table`
- GLOBAL: all StoryParticipation members' character_sheets

`_default_beat_completion_text(beat)` returns a minimal fallback like `"A beat has resolved in your story."` when the author didn't fill in `player_resolution_text`. (The field is required per the Phase 1 model but may be empty-string.)

Tests: beat completion creates a narrative message; recipients match the scope.

Commit:
```
feat(stories): beat completions emit NarrativeMessage deliveries

After record_gm_marked_outcome, evaluate_auto_beats (auto-flip), and
record_aggregate_contribution (threshold cross), the stories service
calls send_narrative_message with the beat's player_resolution_text.
Recipients resolve per scope (character / group members / global
participants).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 6.2: Episode resolutions emit NarrativeMessages

**Files:**
- Modify: `src/world/stories/services/episodes.py` — in `resolve_episode`, after EpisodeResolution is created, emit a NarrativeMessage
- Modify: tests

```python
send_narrative_message(
    recipients=_recipients_for_progress(progress),
    body=_render_episode_resolution_text(resolution),
    category=NarrativeCategory.STORY,
    related_story=progress.story,
    related_episode_resolution=resolution,
)
```

`_render_episode_resolution_text(resolution)`: combines the chosen transition's `connection_type` + `connection_summary` into a player-facing line. Example: `"THEREFORE, you advance to 'Chapter 1 Episode 2A: The Revelation'."` If no transition (frontier), use the episode's summary or fallback text.

Commit:
```
feat(stories): episode resolutions emit NarrativeMessage deliveries
```

---

## Wave 7 — Login catch-up

### Task 7.1: Per-progress `last_caught_up_at` timestamp

**Files:**
- Modify: `src/world/stories/models.py` — add `last_caught_up_at` to `StoryProgress`, `GroupStoryProgress`, `GlobalStoryProgress`
- Migration
- Tests

Per-progress field to track when each progress record was last swept for catch-up purposes. Scoped per character for GROUP/GLOBAL (actually — subtle: for GROUP progress, the field is on the progress record, so it's table-wide. Per-character tracking would need a separate model. For Phase 3, use table-wide timestamp on GroupStoryProgress — good enough for the safety-net use case.)

Actually reconsider: **per-delivery tracking already exists on NarrativeMessageDelivery** (delivered_at). If we rely on narrative message delivery to handle catch-up, we don't need a separate last_caught_up_at on progress. The catch-up service just delivers queued messages + re-evaluates auto-beats unconditionally (cheap — handful of beats per story).

Simpler design: skip the last_caught_up_at field. Login catch-up just:
1. Calls `evaluate_auto_beats(progress)` on each active progress (re-evaluates auto-detected beats; catches any missed event)
2. Delivers queued messages for the character via narrative service

Revise: drop Task 7.1 (no new field). Just do 7.2 and 7.3.

---

### Task 7.2: Login hook — re-evaluate active stories

**Files:**
- Modify: Character typeclass in `src/world/` (`src/typeclasses/characters.py` per project structure)
- Modify: the Evennia `at_post_puppet` hook on the Character class
- Create: `src/world/stories/services/login.py` — new module
- Tests

```python
# src/world/stories/services/login.py
"""Login hook — re-evaluates active stories when a character is puppeted.

Called from Character.at_post_puppet. Iterates the character's active
progress records and calls evaluate_auto_beats. Catches any mutations
that happened while the character was offline and for which no
real-time hook fired.
"""

def catch_up_character_stories(character) -> None:
    """Re-evaluate auto-beats across this character's active stories."""
    from world.stories.services.reactivity import (  # noqa: PLC0415
        on_character_state_changed,
    )
    try:
        sheet = character.sheet
    except AttributeError:
        return  # non-playable character or missing sheet — safe skip
    on_character_state_changed(sheet)
```

In the Character typeclass `at_post_puppet` (grep `at_post_puppet` to find it), add a call to `catch_up_character_stories(self)`.

Tests: a character level-ups while offline (simulated by directly creating a CharacterClassLevel without calling the hook), then at_post_puppet is invoked, assert the beat flipped.

Commit:
```
feat(stories): login catch-up re-evaluates active stories

Character.at_post_puppet now calls
stories.services.login.catch_up_character_stories which re-evaluates
auto-beats across the character's active stories. Safety net — catches
any mutation where the real-time hook didn't fire (e.g., direct admin
action, data import, race condition).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 7.3: Login hook — deliver queued narrative messages

**Files:**
- Modify: `src/world/narrative/services.py` — add `deliver_queued_messages(character_sheet)`
- Modify: Character.at_post_puppet — call the narrative delivery service
- Tests

```python
def deliver_queued_messages(character_sheet) -> int:
    """Push all undelivered messages for this character and mark delivered.

    Called at character login. Returns count of messages delivered.
    """
    from django.utils import timezone  # noqa: PLC0415
    queued = NarrativeMessageDelivery.objects.filter(
        recipient_character_sheet=character_sheet,
        delivered_at__isnull=True,
    ).select_related("message")

    count = 0
    now = timezone.now()
    for delivery in queued:
        _push_to_online_recipient(delivery)  # already exists from Task 1.3
        # _push_to_online_recipient marks delivered_at if session exists.
        # If character isn't actually puppeted somehow (edge case), skip.
        count += 1
    return count
```

Tests: character has queued messages, log in, assert delivered_at is set and character.msg was called.

Commit:
```
feat(narrative): login catch-up delivers queued messages
```

---

## Wave 8 — Progression-side cache invalidation follow-up

### Task 8.1: Progression services invalidate class-level cache

**Files:**
- Modify: whichever progression service mutates `CharacterClassLevel` in production (investigate — may not exist yet per Task 3.1 notes)
- Tests

If a production level-up service exists, add `sheet.invalidate_class_level_cache()` after the mutation. Pair this with the reactivity hook from Task 3.1.

If no production service exists, close this task as "no mutation site to wire" and defer to whenever progression work lands.

Commit:
```
refactor(progression): invalidate class-level cache at CharacterClassLevel mutation

Follow-up from Phase 1 review. Progression services that mutate
CharacterClassLevel now call sheet.invalidate_class_level_cache()
after the save. Pair with the reactivity hook from Wave 3.1 so stories
see the updated level.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Wave 9 — End-to-end integration test + docs

### Task 9.1: Phase 3 end-to-end integration test

**File:** `src/world/stories/tests/test_integration_phase3.py`

**Scenario:** a character has active stories across all three scopes. Various mutations fire; auto-beats flip; narrative messages are delivered correctly across online/offline cases.

Steps:
1. Arrange: Crucible (CHARACTER sheet) with a CHARACTER-scope story on her. A covenant (GMTable) with her as a member and a GROUP-scope story. A metaplot (GLOBAL) story she has StoryParticipation on.
2. Beats across all three stories:
   - Character story: ACHIEVEMENT_HELD on "Defender"
   - Group story: ACHIEVEMENT_HELD on "Commander" (ANY member)
   - Global story: STORY_AT_MILESTONE on the character story reaching Chapter 2
3. Act 1: offline — directly create an Achievement grant for Crucible (simulating an offline mutation with no hook). No real-time reactivity fires. Beat outcome in DB should remain UNSATISFIED.
4. Act 2: Character puppeted. `at_post_puppet` runs. Login catch-up runs. Character-scope + group-scope achievement beats flip to SUCCESS. NarrativeMessages created and delivered in real-time since character is now online.
5. Act 3: Character story advances to Chapter 2 via `resolve_episode`. Internal cascade fires. Global-scope STORY_AT_MILESTONE beat auto-flips. Narrative message fans out.
6. Act 4: GM sends an ad-hoc narrative message via admin (direct model creation in the test) with category=ATMOSPHERE. Character receives it in real-time since still puppeted.
7. Act 5: Character logs off. GM sends another message. Delivery created but delivered_at stays null. Character logs back in; login catch-up delivers.
8. Assertions throughout: beat outcomes, BeatCompletion rows, NarrativeMessage rows, NarrativeMessageDelivery rows (delivered vs queued), character.msg calls.

Run all test suites touched by Phase 3 + full regression on fresh DB before committing.

Commit:
```
test(stories): Phase 3 end-to-end integration test

Walks the full Phase 3 scenario across all three scopes: offline
achievement grant without reactivity → login catch-up flips beats →
character story advance cascades to global story → ad-hoc atmosphere
message → offline message queued → next login delivers. Exercises the
complete reactivity + narrative-integration surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

### Task 9.2: Docs updates

**Files:**
- Modify: `docs/roadmap/stories-gm.md` — mark Phase 3 complete; restructure remaining items as Phase 4+
- Modify: `docs/systems/stories.md` — add reactivity + narrative integration sections
- Create: `docs/systems/narrative.md` — new systems doc for the `world.narrative` app
- Modify: `docs/systems/INDEX.md` — add narrative to the system index
- Regenerate: `docs/systems/MODEL_MAP.md`

Phase 4+ roadmap items to keep (deferred beyond Phase 3):
- React frontend — inline narrative message display in main text (light red), messages section of character sheet UI, story log reader, player dashboard UI, GM queue UI, staff workload UI
- MISSION_COMPLETE predicate
- Covenant leadership model
- Authoring UX polish
- Era lifecycle tooling
- Dispute/withdrawal state transitions

Commit:
```
docs(stories, narrative): Phase 3 complete — reactivity + narrative integration

- Roadmap (stories-gm.md) marks Phase 3 complete. Frontend UX for
  narrative messages (inline display, messages section) is explicit in
  Phase 4+.
- Systems index (stories.md) adds reactivity + narrative integration.
- New systems doc (narrative.md) for the world.narrative app.
- MODEL_MAP regenerated with the new narrative models.

Phase 3 ships real-time reactivity: external systems call narrative
services that fan messages out to characters, stories auto-flips beats
on character state changes, and a general-purpose NarrativeMessage
infrastructure supports GM/Staff/automated IC messages across future
use cases (atmosphere, visions, happenstance) beyond stories.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Execution Notes

- Order dependencies: Wave 1 must land before Wave 6 (stories emits narrative messages). Wave 2 must land before Wave 3 (reactivity module must exist before external apps call it). Wave 5 depends on Wave 2. Wave 4 is independent of Waves 3-5. Wave 7 depends on Waves 1 and 2. Wave 8 is independent. Wave 9 last.
- Expected scope creep into progression, achievements, conditions, codex apps (one-liner hook calls). Scope creep into the Character typeclass (at_post_puppet hook).
- Testing cadence: `arx test world.stories world.narrative --keepdb` per task; fresh-DB + full regression before Wave 9 commit.
- If any external service's mutation site doesn't exist yet (most likely progression), document as a hook point for the first future pass.
- Pre-commit hooks on every commit. Never `--no-verify`.
