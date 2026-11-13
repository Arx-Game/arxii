"""Choices for the missives subsystem (#3289)."""

from __future__ import annotations

from django.db import models


class AttachmentResolution(models.TextChoices):
    """Where an item or coin riding on a missive stands with its recipient."""

    PENDING = "pending", "Waiting"
    ACCEPTED = "accepted", "Accepted"
    REFUSED = "refused", "Refused"


class MissiveDirection(models.TextChoices):
    """Which side of a missive the reading character is on (REST list, #3289)."""

    RECEIVED = "received", "Received"
    SENT = "sent", "Sent"


class AttachmentKind(models.TextChoices):
    """What rides on a missive attachment, as the REST list names it (#3289)."""

    ITEM = "item", "Item"
    COIN = "coin", "Coin"
