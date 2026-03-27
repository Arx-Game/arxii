# Events System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the `world/events` app — scheduled RP gatherings with calendar, invitations, room modifications, and Scene integration.

**Architecture:** New Django app `world/events` with Event, EventHost, EventInvitation, and EventModification (stub) models. Events are the scheduling/planning layer; Scenes handle RP recording. Event lifecycle (DRAFT → SCHEDULED → ACTIVE → COMPLETED/CANCELLED) with room description overlay while active. Scene gets a nullable FK back to Event.

**Tech Stack:** Django + SharedMemoryModel, DRF ViewSets, django-filter, FactoryBoy, existing game_clock TimePhase enum, existing Persona/Organization/Society models.

**Design doc:** `docs/plans/2026-03-27-events-system-design.md`

---

### Task 1: App Scaffolding

**Files:**
- Create: `src/world/events/__init__.py`
- Create: `src/world/events/apps.py`
- Create: `src/world/events/constants.py`
- Create: `src/world/events/tests/__init__.py`
- Modify: `src/server/conf/settings.py` (add to INSTALLED_APPS)
- Modify: `src/web/urls.py` (add URL include)

**Step 1: Create app directory and files**

```bash
mkdir -p src/world/events/tests
touch src/world/events/__init__.py
touch src/world/events/tests/__init__.py
```

**Step 2: Create apps.py**

```python
# src/world/events/apps.py
from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.events"
    verbose_name = "Events"
```

**Step 3: Create constants.py**

```python
# src/world/events/constants.py
from django.db import models


class EventStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class InvitationTargetType(models.TextChoices):
    PERSONA = "persona", "Persona"
    ORGANIZATION = "organization", "Organization"
    SOCIETY = "society", "Society"
```

**Step 4: Register in settings.py**

Add `"world.events.apps.EventsConfig",` to INSTALLED_APPS in `src/server/conf/settings.py`, near the other world apps.

**Step 5: Create empty urls.py**

```python
# src/world/events/urls.py
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

app_name = "events"
urlpatterns = router.urls
```

**Step 6: Register URL include**

Add to `src/web/urls.py`:
```python
path("api/events/", include("world.events.urls")),
```

**Step 7: Verify app loads**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: "Ran 0 tests" (no tests yet, but app loads without import errors)

**Step 8: Commit**

```
feat(events): scaffold world/events app with constants
```

---

### Task 2: Models

**Files:**
- Create: `src/world/events/models.py`

**Step 1: Create models.py with all four models**

```python
# src/world/events/models.py
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.events.constants import EventStatus, InvitationTargetType
from world.game_clock.constants import TimePhase


class Event(SharedMemoryModel):
    """A scheduled RP gathering — ball, meeting, ritual, training session.

    Events handle scheduling, access control, and room state. Scenes handle
    RP recording. An Event spawns a Scene when RP begins.
    """

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.PROTECT,
        related_name="events",
        help_text="The room where this event takes place",
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.DRAFT,
        db_index=True,
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Public events are visible on the calendar to everyone",
    )

    # Scheduling — real time is primary, IC time derived then adjustable
    scheduled_real_time = models.DateTimeField(
        help_text="The OOC date/time players schedule for",
    )
    scheduled_ic_time = models.DateTimeField(
        help_text="IC datetime — derived from game clock, then adjustable",
    )
    time_phase = models.CharField(
        max_length=10,
        choices=TimePhase.choices,
        default=TimePhase.DAY,
        help_text="Time-of-day phase for the event (scene time freezes here)",
    )

    # Lifecycle
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_real_time"]
        indexes = [
            models.Index(fields=["status", "scheduled_real_time"]),
            models.Index(fields=["location", "scheduled_real_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    @property
    def is_active(self) -> bool:
        return self.status == EventStatus.ACTIVE

    @property
    def is_upcoming(self) -> bool:
        return self.status == EventStatus.SCHEDULED


class EventHost(SharedMemoryModel):
    """A host persona for an event. Multiple hosts supported."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="hosts",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        on_delete=models.SET_NULL,
        related_name="hosted_events",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="The primary host is the 'face' of the event on listings",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "persona"],
                name="unique_event_host",
            ),
        ]

    def __str__(self) -> str:
        persona_name = self.persona.name if self.persona else "(deleted)"
        return f"{persona_name} hosting {self.event.name}"


class EventInvitation(SharedMemoryModel):
    """An invitation to an event — can target a persona, organization, or society."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    target_type = models.CharField(
        max_length=20,
        choices=InvitationTargetType.choices,
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    target_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    target_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations",
    )
    can_bring_guests = models.BooleanField(default=False)
    invited_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invitations_sent",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "target_type", "target_persona"],
                condition=models.Q(target_type="persona"),
                name="unique_persona_invitation",
            ),
            models.UniqueConstraint(
                fields=["event", "target_type", "target_organization"],
                condition=models.Q(target_type="organization"),
                name="unique_organization_invitation",
            ),
            models.UniqueConstraint(
                fields=["event", "target_type", "target_society"],
                condition=models.Q(target_type="society"),
                name="unique_society_invitation",
            ),
        ]

    def __str__(self) -> str:
        if self.target_type == InvitationTargetType.PERSONA:
            target = self.target_persona.name if self.target_persona else "(deleted)"
        elif self.target_type == InvitationTargetType.ORGANIZATION:
            target = self.target_organization.name if self.target_organization else "(deleted)"
        else:
            target = self.target_society.name if self.target_society else "(deleted)"
        return f"Invitation to {self.event.name}: {target}"


class EventModification(SharedMemoryModel):
    """Room modifications applied while an event is ACTIVE.

    Stub model — only room_description_overlay is functional for MVP.
    Full design of additional modification types requires a dedicated
    brainstorming session before expanding this schema.
    """

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="modification",
    )
    room_description_overlay = models.TextField(
        blank=True,
        help_text="Text that augments the room description while event is active",
    )

    def __str__(self) -> str:
        return f"Modifications for {self.event.name}"
```

**Step 2: Generate migration**

Run: `uv run arx manage makemigrations events`
Expected: Migration file created in `src/world/events/migrations/`

**Step 3: Apply migration**

Run: `uv run arx manage migrate events`
Expected: Migration applied successfully

**Step 4: Verify models load**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: "Ran 0 tests" (models load without errors)

**Step 5: Commit**

```
feat(events): add Event, EventHost, EventInvitation, EventModification models
```

---

### Task 3: Add Event FK to Scene

**Files:**
- Modify: `src/world/scenes/models.py` (add event FK to Scene)

**Step 1: Add the FK field**

Add to the Scene model, after the `summary_status` field:

```python
event = models.ForeignKey(
    "events.Event",
    null=True,
    blank=True,
    on_delete=models.SET_NULL,
    related_name="scene",
    help_text="The scheduled event that spawned this scene, if any",
)
```

**Step 2: Generate migration**

Run: `uv run arx manage makemigrations scenes`
Expected: Migration adding `event` field to Scene

**Step 3: Apply migration**

Run: `uv run arx manage migrate scenes`
Expected: Migration applied

**Step 4: Run existing scene tests to verify no breakage**

Run: `echo "yes" | uv run arx test world.scenes --keepdb`
Expected: All existing tests pass

**Step 5: Commit**

```
feat(events): add optional event FK to Scene model
```

---

### Task 4: Factories

**Files:**
- Create: `src/world/events/factories.py`

**Step 1: Create factories**

```python
# src/world/events/factories.py
import factory
from django.utils import timezone
from factory import django as factory_django

from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.game_clock.constants import TimePhase


class EventFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = Event

    name = factory.Sequence(lambda n: f"Test Event {n}")
    description = factory.Faker("sentence")
    location = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    status = EventStatus.SCHEDULED
    is_public = True
    scheduled_real_time = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(days=1)
    )
    scheduled_ic_time = factory.LazyFunction(
        lambda: timezone.now() + timezone.timedelta(days=3)
    )
    time_phase = TimePhase.DAY


class EventHostFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventHost

    event = factory.SubFactory(EventFactory)
    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    is_primary = True


class EventInvitationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventInvitation

    event = factory.SubFactory(EventFactory)
    target_type = InvitationTargetType.PERSONA
    target_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    invited_by = factory.SubFactory("world.scenes.factories.PersonaFactory")


class EventModificationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = EventModification

    event = factory.SubFactory(EventFactory)
    room_description_overlay = "The hall has been decorated with silver banners."
```

**Step 2: Check if RoomProfileFactory exists**

We may need to create a `RoomProfileFactory`. Check `src/evennia_extensions/factories.py` — if `RoomProfileFactory` doesn't exist, add it there:

```python
class RoomProfileFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = RoomProfile

    objectdb = factory.SubFactory(ObjectDBFactory, db_typeclass_path="typeclasses.rooms.Room")
```

**Step 3: Verify factories work by running a quick smoke test**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: "Ran 0 tests" (factories import cleanly)

**Step 4: Commit**

```
feat(events): add test factories for Event models
```

---

### Task 5: Model Tests

**Files:**
- Create: `src/world/events/tests/test_models.py`

**Step 1: Write model tests**

```python
# src/world/events/tests/test_models.py
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.events.constants import EventStatus, InvitationTargetType
from world.events.factories import (
    EventFactory,
    EventHostFactory,
    EventInvitationFactory,
    EventModificationFactory,
)
from world.events.models import Event, EventHost, EventInvitation
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, SocietyFactory


class EventModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.event = EventFactory(name="Grand Ball", status=EventStatus.SCHEDULED)

    def test_str(self) -> None:
        self.assertEqual(str(self.event), "Grand Ball (Scheduled)")

    def test_is_active_when_active(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        self.assertTrue(event.is_active)

    def test_is_active_when_scheduled(self) -> None:
        self.assertFalse(self.event.is_active)

    def test_is_upcoming_when_scheduled(self) -> None:
        self.assertTrue(self.event.is_upcoming)

    def test_is_upcoming_when_completed(self) -> None:
        event = EventFactory(status=EventStatus.COMPLETED)
        self.assertFalse(event.is_upcoming)

    def test_default_status_is_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        self.assertEqual(event.status, EventStatus.DRAFT)

    def test_ordering_by_scheduled_real_time(self) -> None:
        now = timezone.now()
        event_later = EventFactory(scheduled_real_time=now + timezone.timedelta(hours=12))
        event_sooner = EventFactory(scheduled_real_time=now + timezone.timedelta(hours=1))
        events = list(Event.objects.filter(id__in=[event_later.id, event_sooner.id]))
        self.assertEqual(events[0].id, event_sooner.id)
        self.assertEqual(events[1].id, event_later.id)


class EventHostModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.event = EventFactory()
        cls.host = EventHostFactory(event=cls.event)

    def test_str(self) -> None:
        self.assertIn("hosting", str(self.host))
        self.assertIn(self.event.name, str(self.host))

    def test_unique_event_persona(self) -> None:
        with self.assertRaises(IntegrityError):
            EventHostFactory(event=self.host.event, persona=self.host.persona)

    def test_persona_set_null_on_delete(self) -> None:
        host = EventHostFactory()
        persona_id = host.persona.id
        host.persona.delete()
        host.refresh_from_db()
        self.assertIsNone(host.persona)


class EventInvitationModelTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.event = EventFactory()

    def test_str_persona_invitation(self) -> None:
        persona = PersonaFactory()
        invitation = EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
        )
        self.assertIn(persona.name, str(invitation))

    def test_str_organization_invitation(self) -> None:
        org = OrganizationFactory()
        invitation = EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.ORGANIZATION,
            target_persona=None,
            target_organization=org,
        )
        self.assertIn(org.name, str(invitation))

    def test_str_society_invitation(self) -> None:
        society = SocietyFactory()
        invitation = EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.SOCIETY,
            target_persona=None,
            target_society=society,
        )
        self.assertIn(society.name, str(invitation))

    def test_unique_persona_invitation_per_event(self) -> None:
        persona = PersonaFactory()
        EventInvitationFactory(
            event=self.event,
            target_type=InvitationTargetType.PERSONA,
            target_persona=persona,
        )
        with self.assertRaises(IntegrityError):
            EventInvitationFactory(
                event=self.event,
                target_type=InvitationTargetType.PERSONA,
                target_persona=persona,
            )

    def test_target_persona_set_null_on_delete(self) -> None:
        invitation = EventInvitationFactory(event=self.event)
        invitation.target_persona.delete()
        invitation.refresh_from_db()
        self.assertIsNone(invitation.target_persona)


class EventModificationModelTest(TestCase):
    def test_str(self) -> None:
        mod = EventModificationFactory()
        self.assertIn("Modifications for", str(mod))

    def test_one_to_one_with_event(self) -> None:
        mod = EventModificationFactory()
        with self.assertRaises(IntegrityError):
            EventModificationFactory(event=mod.event)
```

**Step 2: Run tests**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: All tests pass

**Step 3: Commit**

```
test(events): add model tests for Event, EventHost, EventInvitation, EventModification
```

---

### Task 6: Services

**Files:**
- Create: `src/world/events/services.py`

**Step 1: Create services**

```python
# src/world/events/services.py
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from world.events.constants import EventStatus, InvitationTargetType
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.game_clock.constants import TimePhase
from world.game_clock.services import get_ic_now
from world.scenes.models import Persona

# Minimum gap between events at the same location (real hours)
LOCATION_GAP_HOURS = 6


def derive_ic_time_from_real(real_time: "datetime") -> "datetime | None":
    """Derive an IC datetime from a real datetime using the game clock.

    Returns None if no game clock is configured.
    """
    from world.game_clock.models import GameClock

    clock = GameClock.get_active()
    if clock is None or clock.paused or clock.time_ratio == 0:
        return None
    ic_elapsed = timedelta(
        seconds=(real_time - clock.anchor_real_time).total_seconds() * clock.time_ratio
    )
    return clock.anchor_ic_time + ic_elapsed


def validate_location_gap(
    location_id: int,
    scheduled_real_time: "datetime",
    exclude_event_id: int | None = None,
) -> bool:
    """Check that no other event at this location is within LOCATION_GAP_HOURS.

    Returns True if the time slot is available.
    """
    window_start = scheduled_real_time - timedelta(hours=LOCATION_GAP_HOURS)
    window_end = scheduled_real_time + timedelta(hours=LOCATION_GAP_HOURS)
    qs = Event.objects.filter(
        location_id=location_id,
        scheduled_real_time__gte=window_start,
        scheduled_real_time__lte=window_end,
    ).exclude(status=EventStatus.CANCELLED)
    if exclude_event_id:
        qs = qs.exclude(id=exclude_event_id)
    return not qs.exists()


def create_event(
    *,
    name: str,
    location_id: int,
    scheduled_real_time: "datetime",
    host_persona: Persona,
    description: str = "",
    is_public: bool = True,
    scheduled_ic_time: "datetime | None" = None,
    time_phase: str = TimePhase.DAY,
    status: str = EventStatus.DRAFT,
) -> Event:
    """Create an event with a primary host.

    If scheduled_ic_time is not provided, it is derived from the game clock.
    Validates the location gap constraint before creating.

    Raises:
        ValueError: If the location time slot is unavailable.
    """
    if not validate_location_gap(location_id, scheduled_real_time):
        raise ValueError(
            f"Another event is scheduled within {LOCATION_GAP_HOURS} hours "
            f"at this location."
        )

    if scheduled_ic_time is None:
        scheduled_ic_time = derive_ic_time_from_real(scheduled_real_time)
        if scheduled_ic_time is None:
            scheduled_ic_time = scheduled_real_time  # fallback if no clock

    event = Event.objects.create(
        name=name,
        description=description,
        location_id=location_id,
        status=status,
        is_public=is_public,
        scheduled_real_time=scheduled_real_time,
        scheduled_ic_time=scheduled_ic_time,
        time_phase=time_phase,
    )
    EventHost.objects.create(event=event, persona=host_persona, is_primary=True)
    return event


def schedule_event(event: Event) -> Event:
    """Transition an event from DRAFT to SCHEDULED.

    Raises:
        ValueError: If the event is not in DRAFT status.
    """
    if event.status != EventStatus.DRAFT:
        raise ValueError(f"Cannot schedule event in '{event.status}' status.")
    event.status = EventStatus.SCHEDULED
    event.save(update_fields=["status", "updated_at"])
    return event


def start_event(event: Event) -> Event:
    """Transition an event from SCHEDULED to ACTIVE.

    Raises:
        ValueError: If the event is not in SCHEDULED status.
    """
    if event.status != EventStatus.SCHEDULED:
        raise ValueError(f"Cannot start event in '{event.status}' status.")
    event.status = EventStatus.ACTIVE
    event.started_at = timezone.now()
    event.save(update_fields=["status", "started_at", "updated_at"])
    return event


def complete_event(event: Event) -> Event:
    """Transition an event from ACTIVE to COMPLETED.

    Raises:
        ValueError: If the event is not in ACTIVE status.
    """
    if event.status != EventStatus.ACTIVE:
        raise ValueError(f"Cannot complete event in '{event.status}' status.")
    event.status = EventStatus.COMPLETED
    event.ended_at = timezone.now()
    event.save(update_fields=["status", "ended_at", "updated_at"])
    return event


def cancel_event(event: Event) -> Event:
    """Cancel an event from any non-completed status.

    Raises:
        ValueError: If the event is already completed.
    """
    if event.status == EventStatus.COMPLETED:
        raise ValueError("Cannot cancel a completed event.")
    event.status = EventStatus.CANCELLED
    event.ended_at = timezone.now()
    event.save(update_fields=["status", "ended_at", "updated_at"])
    return event


def add_host(event: Event, persona: Persona, *, is_primary: bool = False) -> EventHost:
    """Add a host to an event."""
    return EventHost.objects.create(event=event, persona=persona, is_primary=is_primary)


def invite_persona(
    event: Event,
    target_persona: Persona,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite a persona to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.PERSONA,
        target_persona=target_persona,
        invited_by=invited_by,
    )


def invite_organization(
    event: Event,
    organization_id: int,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite an organization to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.ORGANIZATION,
        target_organization_id=organization_id,
        invited_by=invited_by,
    )


def invite_society(
    event: Event,
    society_id: int,
    *,
    invited_by: Persona | None = None,
) -> EventInvitation:
    """Invite a society to an event."""
    return EventInvitation.objects.create(
        event=event,
        target_type=InvitationTargetType.SOCIETY,
        target_society_id=society_id,
        invited_by=invited_by,
    )


def set_room_description_overlay(event: Event, overlay_text: str) -> EventModification:
    """Set or update the room description overlay for an event."""
    mod, _ = EventModification.objects.update_or_create(
        event=event,
        defaults={"room_description_overlay": overlay_text},
    )
    return mod


def get_visible_events(
    persona: Persona | None = None,
    *,
    include_public: bool = True,
) -> "QuerySet[Event]":
    """Return events visible to a persona.

    Public events are always included (if include_public=True).
    Private events are included if the persona is a host or invitee
    (directly or via organization/society membership).
    """
    qs = Event.objects.exclude(status=EventStatus.CANCELLED)

    if persona is None:
        return qs.filter(is_public=True) if include_public else qs.none()

    public_q = Q(is_public=True) if include_public else Q()
    host_q = Q(hosts__persona=persona)
    direct_invite_q = Q(
        invitations__target_type=InvitationTargetType.PERSONA,
        invitations__target_persona=persona,
    )
    # Organization/society membership checks would go here in future PRs
    # For now, only direct persona invitations and host status grant access

    return qs.filter(public_q | host_q | direct_invite_q).distinct()
```

**Step 2: Commit**

```
feat(events): add service functions for event lifecycle and invitations
```

---

### Task 7: Service Tests

**Files:**
- Create: `src/world/events/tests/test_services.py`

**Step 1: Write service tests**

```python
# src/world/events/tests/test_services.py
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.events.constants import EventStatus, InvitationTargetType
from world.events.factories import EventFactory, EventHostFactory
from world.events.models import Event, EventHost, EventInvitation, EventModification
from world.events.services import (
    add_host,
    cancel_event,
    complete_event,
    create_event,
    get_visible_events,
    invite_organization,
    invite_persona,
    invite_society,
    schedule_event,
    set_room_description_overlay,
    start_event,
    validate_location_gap,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, SocietyFactory


class ValidateLocationGapTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.event = EventFactory()

    def test_available_slot(self) -> None:
        far_future = self.event.scheduled_real_time + timedelta(hours=12)
        result = validate_location_gap(self.event.location_id, far_future)
        self.assertTrue(result)

    def test_blocked_slot(self) -> None:
        nearby = self.event.scheduled_real_time + timedelta(hours=2)
        result = validate_location_gap(self.event.location_id, nearby)
        self.assertFalse(result)

    def test_cancelled_events_ignored(self) -> None:
        cancelled = EventFactory(
            location=self.event.location,
            status=EventStatus.CANCELLED,
            scheduled_real_time=self.event.scheduled_real_time,
        )
        nearby = cancelled.scheduled_real_time + timedelta(hours=1)
        # Only the non-cancelled self.event matters
        result = validate_location_gap(
            self.event.location_id, nearby, exclude_event_id=None
        )
        # Still blocked by self.event
        self.assertFalse(result)

    def test_exclude_self(self) -> None:
        same_time = self.event.scheduled_real_time
        result = validate_location_gap(
            self.event.location_id, same_time, exclude_event_id=self.event.id
        )
        self.assertTrue(result)


class CreateEventTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.location = cls.persona.character.room_profile  # may need adjustment

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        self.room_profile = RoomProfileFactory()

    def test_creates_event_with_primary_host(self) -> None:
        event = create_event(
            name="Test Gathering",
            location_id=self.room_profile.pk,
            scheduled_real_time=timezone.now() + timedelta(days=1),
            host_persona=PersonaFactory(),
        )
        self.assertEqual(event.name, "Test Gathering")
        self.assertEqual(event.status, EventStatus.DRAFT)
        self.assertTrue(event.hosts.filter(is_primary=True).exists())

    def test_rejects_conflicting_time_slot(self) -> None:
        existing = EventFactory(location=self.room_profile)
        with self.assertRaises(ValueError):
            create_event(
                name="Conflicting Event",
                location_id=self.room_profile.pk,
                scheduled_real_time=existing.scheduled_real_time + timedelta(hours=1),
                host_persona=PersonaFactory(),
            )


class EventLifecycleTest(TestCase):
    def test_schedule_from_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        schedule_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.SCHEDULED)

    def test_schedule_from_non_draft_raises(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        with self.assertRaises(ValueError):
            schedule_event(event)

    def test_start_from_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        start_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.ACTIVE)
        self.assertIsNotNone(event.started_at)

    def test_start_from_non_scheduled_raises(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        with self.assertRaises(ValueError):
            start_event(event)

    def test_complete_from_active(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        complete_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.COMPLETED)
        self.assertIsNotNone(event.ended_at)

    def test_complete_from_non_active_raises(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        with self.assertRaises(ValueError):
            complete_event(event)

    def test_cancel_from_draft(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        cancel_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_cancel_from_scheduled(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        cancel_event(event)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_cancel_completed_raises(self) -> None:
        event = EventFactory(status=EventStatus.COMPLETED)
        with self.assertRaises(ValueError):
            cancel_event(event)


class InvitationTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.event = EventFactory()
        cls.host_persona = PersonaFactory()

    def test_invite_persona(self) -> None:
        target = PersonaFactory()
        invitation = invite_persona(
            self.event, target, invited_by=self.host_persona
        )
        self.assertEqual(invitation.target_type, InvitationTargetType.PERSONA)
        self.assertEqual(invitation.target_persona, target)
        self.assertEqual(invitation.invited_by, self.host_persona)

    def test_invite_organization(self) -> None:
        org = OrganizationFactory()
        invitation = invite_organization(
            self.event, org.id, invited_by=self.host_persona
        )
        self.assertEqual(invitation.target_type, InvitationTargetType.ORGANIZATION)
        self.assertEqual(invitation.target_organization, org)

    def test_invite_society(self) -> None:
        society = SocietyFactory()
        invitation = invite_society(
            self.event, society.id, invited_by=self.host_persona
        )
        self.assertEqual(invitation.target_type, InvitationTargetType.SOCIETY)
        self.assertEqual(invitation.target_society, society)


class RoomDescriptionOverlayTest(TestCase):
    def test_set_overlay_creates_modification(self) -> None:
        event = EventFactory()
        mod = set_room_description_overlay(event, "Decorated with flowers.")
        self.assertEqual(mod.room_description_overlay, "Decorated with flowers.")

    def test_set_overlay_updates_existing(self) -> None:
        event = EventFactory()
        set_room_description_overlay(event, "First version.")
        mod = set_room_description_overlay(event, "Updated version.")
        self.assertEqual(mod.room_description_overlay, "Updated version.")
        self.assertEqual(EventModification.objects.filter(event=event).count(), 1)


class GetVisibleEventsTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.persona = PersonaFactory()
        cls.public_event = EventFactory(is_public=True)
        cls.private_event = EventFactory(is_public=False)
        cls.private_hosted = EventFactory(is_public=False)
        EventHostFactory(event=cls.private_hosted, persona=cls.persona)
        cls.private_invited = EventFactory(is_public=False)
        EventInvitationFactory(
            event=cls.private_invited,
            target_type=InvitationTargetType.PERSONA,
            target_persona=cls.persona,
        )
        cls.cancelled = EventFactory(
            is_public=True, status=EventStatus.CANCELLED
        )

    def test_anonymous_sees_only_public(self) -> None:
        events = get_visible_events(persona=None)
        self.assertIn(self.public_event, events)
        self.assertNotIn(self.private_event, events)
        self.assertNotIn(self.cancelled, events)

    def test_persona_sees_public_and_hosted(self) -> None:
        events = get_visible_events(persona=self.persona)
        self.assertIn(self.public_event, events)
        self.assertIn(self.private_hosted, events)

    def test_persona_sees_invited_events(self) -> None:
        events = get_visible_events(persona=self.persona)
        self.assertIn(self.private_invited, events)

    def test_persona_does_not_see_unrelated_private(self) -> None:
        events = get_visible_events(persona=self.persona)
        self.assertNotIn(self.private_event, events)

    def test_cancelled_excluded(self) -> None:
        events = get_visible_events(persona=self.persona)
        self.assertNotIn(self.cancelled, events)
```

**Step 2: Run tests**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: All tests pass

**Step 3: Commit**

```
test(events): add service tests for lifecycle, invitations, visibility
```

---

### Task 8: Serializers

**Files:**
- Create: `src/world/events/serializers.py`

**Step 1: Create serializers**

```python
# src/world/events/serializers.py
from rest_framework import serializers

from world.events.models import Event, EventHost, EventInvitation, EventModification


class EventHostSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True, default=None)

    class Meta:
        model = EventHost
        fields = ["id", "persona", "persona_name", "is_primary", "added_at"]
        read_only_fields = ["id", "persona_name", "added_at"]


class EventInvitationSerializer(serializers.ModelSerializer):
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = EventInvitation
        fields = [
            "id",
            "target_type",
            "target_persona",
            "target_organization",
            "target_society",
            "target_name",
            "can_bring_guests",
            "invited_at",
        ]
        read_only_fields = ["id", "target_name", "invited_at"]

    def get_target_name(self, obj: EventInvitation) -> str | None:
        if obj.target_persona:
            return obj.target_persona.name
        if obj.target_organization:
            return obj.target_organization.name
        if obj.target_society:
            return obj.target_society.name
        return None


class EventModificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventModification
        fields = ["room_description_overlay"]


class EventListSerializer(serializers.ModelSerializer):
    primary_host_name = serializers.SerializerMethodField()
    location_name = serializers.CharField(
        source="location.objectdb.db_key", read_only=True
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "description",
            "location",
            "location_name",
            "status",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
            "primary_host_name",
        ]
        read_only_fields = fields

    def get_primary_host_name(self, obj: Event) -> str | None:
        for host in getattr(obj, "hosts_cached", []):
            if host.is_primary and host.persona:
                return host.persona.name
        return None


class EventDetailSerializer(serializers.ModelSerializer):
    hosts = EventHostSerializer(source="hosts_cached", many=True, read_only=True)
    invitations = EventInvitationSerializer(
        source="invitations_cached", many=True, read_only=True
    )
    modification = EventModificationSerializer(read_only=True, allow_null=True)
    location_name = serializers.CharField(
        source="location.objectdb.db_key", read_only=True
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "description",
            "location",
            "location_name",
            "status",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
            "started_at",
            "ended_at",
            "created_at",
            "updated_at",
            "hosts",
            "invitations",
            "modification",
        ]
        read_only_fields = fields


class EventCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating events. Host is derived from the request."""

    class Meta:
        model = Event
        fields = [
            "name",
            "description",
            "location",
            "is_public",
            "scheduled_real_time",
            "scheduled_ic_time",
            "time_phase",
        ]

    def validate_scheduled_real_time(self, value: "datetime") -> "datetime":
        from django.utils import timezone

        if value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value
```

**Step 2: Add cached_property to Event model for Prefetch support**

Add to `Event` model in `src/world/events/models.py`:

```python
from functools import cached_property

# Inside Event class, after __str__:
@cached_property
def hosts_cached(self) -> list["EventHost"]:
    return list(self.hosts.select_related("persona"))

@cached_property
def invitations_cached(self) -> list["EventInvitation"]:
    return list(
        self.invitations.select_related(
            "target_persona", "target_organization", "target_society"
        )
    )
```

**Step 3: Commit**

```
feat(events): add DRF serializers for Event CRUD and detail views
```

---

### Task 9: Filters and Permissions

**Files:**
- Create: `src/world/events/filters.py`
- Create: `src/world/events/permissions.py`

**Step 1: Create filters**

```python
# src/world/events/filters.py
import django_filters
from django.db.models import QuerySet

from world.events.constants import EventStatus
from world.events.models import Event


class EventFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    is_public = django_filters.BooleanFilter(field_name="is_public")
    location = django_filters.NumberFilter(field_name="location_id")
    host = django_filters.NumberFilter(method="filter_host")
    upcoming = django_filters.BooleanFilter(method="filter_upcoming")

    class Meta:
        model = Event
        fields = ["status", "is_public", "location", "host", "upcoming"]

    def filter_host(
        self, queryset: QuerySet[Event], name: str, value: int
    ) -> QuerySet[Event]:
        return queryset.filter(hosts__persona_id=value).distinct()

    def filter_upcoming(
        self, queryset: QuerySet[Event], name: str, value: bool
    ) -> QuerySet[Event]:
        if value:
            return queryset.filter(status=EventStatus.SCHEDULED)
        return queryset
```

**Step 2: Create permissions**

```python
# src/world/events/permissions.py
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsEventHostOrStaff(BasePermission):
    """Allow access to event hosts or staff."""

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_staff:
            return True
        # Check if request user has a persona that is a host of this event
        return obj.hosts.filter(
            persona__character__roster_entry__tenures__player_data__account=request.user,
            persona__character__roster_entry__tenures__end_date__isnull=True,
        ).exists()
```

**Step 3: Commit**

```
feat(events): add filters and permissions for Event API
```

---

### Task 10: Views

**Files:**
- Create: `src/world/events/views.py`
- Modify: `src/world/events/urls.py` (register viewsets)

**Step 1: Create views**

```python
# src/world/events/views.py
from django.db.models import Prefetch, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from world.events.filters import EventFilter
from world.events.models import Event, EventHost, EventInvitation
from world.events.permissions import IsEventHostOrStaff
from world.events.serializers import (
    EventCreateSerializer,
    EventDetailSerializer,
    EventHostSerializer,
    EventInvitationSerializer,
    EventListSerializer,
)
from world.events.services import (
    cancel_event,
    complete_event,
    create_event,
    schedule_event,
    start_event,
)


class EventViewSet(ModelViewSet):
    """ViewSet for listing, creating, and managing events."""

    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = EventFilter
    search_fields = ["name", "description"]

    def get_permissions(self) -> list:
        if self.action in ("list", "retrieve"):
            return [IsAuthenticatedOrReadOnly()]
        if self.action in ("update", "partial_update", "destroy", "schedule", "start", "complete", "cancel"):
            return [IsAuthenticated(), IsEventHostOrStaff()]
        return [IsAuthenticated()]

    def get_serializer_class(self):  # type: ignore[override]
        if self.action == "list":
            return EventListSerializer
        if self.action == "create":
            return EventCreateSerializer
        return EventDetailSerializer

    def get_queryset(self) -> QuerySet[Event]:
        return Event.objects.select_related(
            "location__objectdb",
        ).prefetch_related(
            Prefetch(
                "hosts",
                queryset=EventHost.objects.select_related("persona"),
                to_attr="hosts_cached",
            ),
            Prefetch(
                "invitations",
                queryset=EventInvitation.objects.select_related(
                    "target_persona", "target_organization", "target_society",
                ),
                to_attr="invitations_cached",
            ),
            "modification",
        )

    def perform_create(self, serializer: EventCreateSerializer) -> None:
        """Create event via service function, deriving host from request user."""
        from world.scenes.models import Persona

        # Get the user's active persona
        active_persona = Persona.objects.filter(
            character__roster_entry__tenures__player_data__account=self.request.user,
            character__roster_entry__tenures__end_date__isnull=True,
            character_identity__active_persona__isnull=False,
            persona_type="primary",
        ).first()

        if not active_persona:
            raise serializers.ValidationError(
                "You must have an active character with a persona to create events."
            )

        data = serializer.validated_data
        event = create_event(
            name=data["name"],
            description=data.get("description", ""),
            location_id=data["location"].pk,
            scheduled_real_time=data["scheduled_real_time"],
            host_persona=active_persona,
            is_public=data.get("is_public", True),
            scheduled_ic_time=data.get("scheduled_ic_time"),
            time_phase=data.get("time_phase", "day"),
        )
        serializer.instance = event

    @action(detail=True, methods=["post"])
    def schedule(self, request: Request, pk: int = None) -> Response:
        event = self.get_object()
        try:
            schedule_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(event).data)

    @action(detail=True, methods=["post"])
    def start(self, request: Request, pk: int = None) -> Response:
        event = self.get_object()
        try:
            start_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(event).data)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: int = None) -> Response:
        event = self.get_object()
        try:
            complete_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(event).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: int = None) -> Response:
        event = self.get_object()
        try:
            cancel_event(event)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EventDetailSerializer(event).data)
```

**Step 2: Update urls.py**

```python
# src/world/events/urls.py
from rest_framework.routers import DefaultRouter

from world.events.views import EventViewSet

router = DefaultRouter()
router.register("", EventViewSet, basename="event")

app_name = "events"
urlpatterns = router.urls
```

**Step 3: Commit**

```
feat(events): add EventViewSet with lifecycle actions and URL routing
```

---

### Task 11: View Tests

**Files:**
- Create: `src/world/events/tests/test_views.py`

**Step 1: Write view tests**

```python
# src/world/events/tests/test_views.py
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.events.constants import EventStatus
from world.events.factories import EventFactory, EventHostFactory
from world.events.models import Event
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory


class EventViewSetTestCase(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_list_returns_public_events(self) -> None:
        EventFactory(is_public=True)
        EventFactory(is_public=False)
        response = self.client.get("/api/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Both may appear if no visibility filtering on list (MVP)
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_retrieve_event_detail(self) -> None:
        event = EventFactory()
        EventHostFactory(event=event)
        response = self.client.get(f"/api/events/{event.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], event.name)

    def test_schedule_action(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        host = EventHostFactory(event=event)
        # Set up account to own the host persona's character
        tenure = RosterTenureFactory(
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.SCHEDULED)

    def test_schedule_wrong_status_returns_400(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        host = EventHostFactory(event=event)
        tenure = RosterTenureFactory(
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_start_action(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        host = EventHostFactory(event=event)
        tenure = RosterTenureFactory(
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.ACTIVE)

    def test_complete_action(self) -> None:
        event = EventFactory(status=EventStatus.ACTIVE)
        host = EventHostFactory(event=event)
        tenure = RosterTenureFactory(
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/complete/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.COMPLETED)

    def test_cancel_action(self) -> None:
        event = EventFactory(status=EventStatus.SCHEDULED)
        host = EventHostFactory(event=event)
        tenure = RosterTenureFactory(
            roster_entry__character=host.persona.character,
            player_data__account=self.account,
        )
        response = self.client.post(f"/api/events/{event.id}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_non_host_cannot_schedule(self) -> None:
        event = EventFactory(status=EventStatus.DRAFT)
        EventHostFactory(event=event)  # host is someone else
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_schedule_any_event(self) -> None:
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        event = EventFactory(status=EventStatus.DRAFT)
        EventHostFactory(event=event)
        response = self.client.post(f"/api/events/{event.id}/schedule/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_status(self) -> None:
        EventFactory(status=EventStatus.SCHEDULED)
        EventFactory(status=EventStatus.COMPLETED)
        response = self.client.get("/api/events/", {"status": "scheduled"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for event_data in response.data["results"]:
            self.assertEqual(event_data["status"], "scheduled")

    def test_search_by_name(self) -> None:
        EventFactory(name="Grand Ball")
        EventFactory(name="Secret Meeting")
        response = self.client.get("/api/events/", {"search": "Ball"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Grand Ball")
```

**Step 2: Run all event tests**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: All tests pass

**Step 3: Commit**

```
test(events): add API view tests for EventViewSet lifecycle and permissions
```

---

### Task 12: Admin

**Files:**
- Create: `src/world/events/admin.py`

**Step 1: Create admin configuration**

```python
# src/world/events/admin.py
from django.contrib import admin

from world.events.models import Event, EventHost, EventInvitation, EventModification


class EventHostInline(admin.TabularInline):
    model = EventHost
    extra = 1
    raw_id_fields = ["persona"]


class EventInvitationInline(admin.TabularInline):
    model = EventInvitation
    extra = 0
    raw_id_fields = ["target_persona", "target_organization", "target_society", "invited_by"]


class EventModificationInline(admin.StackedInline):
    model = EventModification
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "is_public", "scheduled_real_time", "location"]
    list_filter = ["status", "is_public", "time_phase"]
    search_fields = ["name", "description"]
    raw_id_fields = ["location"]
    inlines = [EventHostInline, EventInvitationInline, EventModificationInline]
    readonly_fields = ["created_at", "updated_at"]
```

**Step 2: Commit**

```
feat(events): add Django admin for Event management
```

---

### Task 13: Lint, Format, Final Verification

**Step 1: Run ruff check on all new files**

Run: `ruff check src/world/events/`

**Step 2: Fix any lint issues**

Run: `ruff check src/world/events/ --fix`

**Step 3: Run ruff format**

Run: `ruff format src/world/events/`

**Step 4: Run all event tests one final time**

Run: `echo "yes" | uv run arx test world.events --keepdb`
Expected: All tests pass

**Step 5: Run scene tests to verify FK addition didn't break anything**

Run: `echo "yes" | uv run arx test world.scenes --keepdb`
Expected: All existing tests still pass

**Step 6: Commit any formatting fixes**

```
style(events): lint and format world/events app
```

---

### Task 14: Update Roadmap Status

**Files:**
- Modify: `docs/roadmap/events.md` (update status)
- Modify: `docs/roadmap/ROADMAP.md` (update status)

**Step 1: Update events.md status from "not-started" to "in-progress"**

**Step 2: Update ROADMAP.md table row for Events from "not-started" to "in-progress"**

**Step 3: Commit**

```
docs: update Events roadmap status to in-progress
```
