"""Constants for player channels (#3299)."""

from django.db import models

# PLACEHOLDER tunables: staff/owner may retune.
CHANNEL_HISTORY_CAP = 500
CHANNEL_MESSAGE_MAX_LENGTH = 2000
PUBLIC_CHANNEL_NAME = "Public"


class ChannelKind(models.TextChoices):
    PUBLIC = "public", "Public"
    ORG = "org", "Organization"
    STAFF = "staff", "Staff"


class ChannelNotificationLevel(models.TextChoices):
    ALL = "all", "Every message"
    BADGE = "badge", "Unread count only"
    NONE = "none", "Nothing"
