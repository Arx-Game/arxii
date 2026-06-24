"""Constants for the public-reaction tidings feed (#1450)."""

from django.db import models


class FeedItemKind(models.TextChoices):
    """What kind of public event a feed row is — drives icon/label on web and telnet."""

    DEED = "deed", "Deed"
    SCANDAL = "scandal", "Scandal"
