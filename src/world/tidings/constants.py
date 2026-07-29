"""Constants for the public-reaction tidings feed (#1450)."""

from django.db import models


class FeedItemKind(models.TextChoices):
    """What kind of public event a feed row is — drives icon/label on web and telnet."""

    DEED = "deed", "Deed"
    SCANDAL = "scandal", "Scandal"
    # Fix-on-sight (#2756): pardon/crisis rows were emitted as raw strings that
    # bypassed this enum while PublicFeedItemSerializer.kind validates against
    # its choices — enum membership makes the serializer honest.
    PARDON = "pardon", "Pardon"
    CRISIS = "crisis", "Crisis"
    PROCLAMATION = "proclamation", "Proclamation"
    BIRTHDAY = "birthday", "Birthday"
