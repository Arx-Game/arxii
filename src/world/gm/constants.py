"""Constants for the GM system."""

from django.db import models


class GMLevel(models.TextChoices):
    """GM trust/permission tiers. Higher levels unlock broader story scope and reward caps."""

    STARTING = "starting", "Starting GM"
    JUNIOR = "junior", "Junior GM"
    GM = "gm", "GM"
    EXPERIENCED = "experienced", "Experienced GM"
    SENIOR = "senior", "Senior GM"


GM_LEVEL_ORDER = [
    GMLevel.STARTING,
    GMLevel.JUNIOR,
    GMLevel.GM,
    GMLevel.EXPERIENCED,
    GMLevel.SENIOR,
]


def gm_level_index(level: str) -> int:
    """Return ``level``'s position in ``GM_LEVEL_ORDER`` (STARTING=0 .. SENIOR=4)."""
    return GM_LEVEL_ORDER.index(level)


class GMApplicationStatus(models.TextChoices):
    """Status for GM applications."""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"


class GMTableStatus(models.TextChoices):
    """Lifecycle status for a GM table."""

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class GMTableViewerRole(models.TextChoices):
    """Requesting user's role relative to a GMTable.

    Returned by GMTableSerializer.get_viewer_role(). Priority: gm > staff >
    member > guest > none.
    """

    GM = "gm", "GM (owner)"
    STAFF = "staff", "Staff"
    MEMBER = "member", "Member"
    GUEST = "guest", "Guest (story participant, not a member)"
    NONE = "none", "None"
