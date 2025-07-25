from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class Event(SharedMemoryModel):
    """Represents an event type that triggers can listen for or emit."""

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier for the event.",
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for the event.",
    )

    def __str__(self) -> str:
        return self.label
