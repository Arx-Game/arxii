from django.db import models


class TriggerScope(models.TextChoices):
    """Dispatch scope for reactive triggers.

    PERSONAL: delivered to the event's subject (character, object).
    ROOM: delivered to the subject's current location.
    """

    PERSONAL = "personal", "Personal"
    ROOM = "room", "Room"
