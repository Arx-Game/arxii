"""Choice enums for the tasking app (#2820 phase 1)."""

from django.db import models


class TaskCategory(models.TextChoices):
    """Broad job family a TaskTemplate belongs to.

    Categories group templates for authoring and board filtering; effect
    behavior is carried entirely by the template's routes and pools, so a
    new category is a data label, not a code branch.
    """

    SPYCRAFT = "spycraft", "Spycraft"
    CRIME = "crime", "Crime"
    DOMAIN = "domain", "Domain"
    MILITARY = "military", "Military"
    GENERAL = "general", "General"


class TaskStatus(models.TextChoices):
    """Lifecycle of an OrgTask. Every task ends — there is no ongoing state.

    Standing "stay here until recalled" postings are NPCAssignment rows,
    not tasks (see #2820 spec: postings persist, tasks resolve).
    """

    OPEN = "open", "Open"
    ASSIGNED = "assigned", "Assigned"
    RESOLVING = "resolving", "Resolving"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    EXPIRED = "expired", "Expired"


class TaskTargetKind(models.TextChoices):
    """Discriminator: what kind of thing a task is pointed at."""

    NONE = "none", "None"
    ROOM = "room", "Room"
    ORG = "org", "Organization"
    DOMAIN = "domain", "Domain"
    PERSONA = "persona", "Persona"


# Points of check modifier the agent's resolution roll gains (or loses) per
# success level of the handler's dispatch check. The handler's briefing
# quality shifts the agent's odds without ever replacing the agent's roll.
DISPATCH_MARGIN_STEP = 5
