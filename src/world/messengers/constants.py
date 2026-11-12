"""Choices for the missives subsystem (#3289)."""

from __future__ import annotations

from django.db import models


class AttachmentResolution(models.TextChoices):
    """Where an item or coin riding on a missive stands with its recipient."""

    PENDING = "pending", "Waiting"
    ACCEPTED = "accepted", "Accepted"
    REFUSED = "refused", "Refused"
