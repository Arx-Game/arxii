from django.db import models


class Event(models.Model):
    """Represents an event type that triggers can listen for or emit."""

    key = models.CharField(
        max_length=50,
        primary_key=True,
        help_text="Unique identifier for the event.",
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable label for the event.",
    )

    def __str__(self) -> str:
        return self.label
