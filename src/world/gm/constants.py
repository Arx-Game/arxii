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


class CatalogSuggestionProposalKind(models.TextChoices):
    """What kind of catalog growth a GM is proposing (#2127).

    Tiered by GM trust (Decision 9, ADR-0110): STARTING/JUNIOR may only propose
    NEW_SITUATION/CHECK_FIT/OTHER; GM+ additionally unlocks DIFFICULTY_GUIDE;
    EXPERIENCED+ additionally unlocks POOL_GUIDE -- consequence-pool guidance is
    the single most guarded authoring surface (Decision 3).
    """

    NEW_SITUATION = "new_situation", "New Situation"
    CHECK_FIT = "check_fit", "Check Fit"
    DIFFICULTY_GUIDE = "difficulty_guide", "Difficulty Guide"
    POOL_GUIDE = "pool_guide", "Pool Guide"
    OTHER = "other", "Other"


#: Minimum GMLevel required to submit each CatalogSuggestion.proposal_kind (Decision 9).
#: Read by ``actions.definitions.gm_catalog.SubmitCatalogSuggestionAction`` -- staff
#: always bypass (mirrors every other GM-tool gate in this line).
PROPOSAL_KIND_MIN_LEVEL: dict[str, str] = {
    CatalogSuggestionProposalKind.NEW_SITUATION: GMLevel.STARTING,
    CatalogSuggestionProposalKind.CHECK_FIT: GMLevel.STARTING,
    CatalogSuggestionProposalKind.OTHER: GMLevel.STARTING,
    CatalogSuggestionProposalKind.DIFFICULTY_GUIDE: GMLevel.GM,
    CatalogSuggestionProposalKind.POOL_GUIDE: GMLevel.EXPERIENCED,
}


class TableRequestKind(models.TextChoices):
    """What a table update request proposes to change (#2631).

    Extensible: each kind carries its payload on a 1:1 details model and its
    apply logic in ``services.signoff_table_update_request``. Requests propose
    a concrete change with a yes/no answer — never a prompt for content.
    """

    PROFILE_TEXT = "profile_text", "Profile Text"
    DISTINCTION_CHANGE = "distinction_change", "Distinction Change"


class TableRequestStatus(models.TextChoices):
    """Lifecycle of a table update request (#2631).

    PENDING → APPROVED (distinction kind: authorization created, player still
    accepts/spends) → COMPLETED (change applied). Prose kinds apply at
    approval and go straight to COMPLETED. REJECTED/WITHDRAWN are terminal.
    """

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"
    COMPLETED = "completed", "Completed"


class TableRequestRole(models.TextChoices):
    """The ``role`` filter on table update requests (#2631)."""

    MINE = "mine", "Mine"
    GM = "gm", "GM"
