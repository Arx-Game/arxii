"""Constants for the captivity system (#931)."""

from django.db import models


class CaptivityStatus(models.TextChoices):
    """The lifecycle of a single captivity.

    HELD is the only active state — a captive cannot hold two HELD rows at
    once (enforced by a partial unique constraint). The four terminal states
    record *how* the captivity ended, because each forks differently in
    fiction: an escape is a victory the captive earned, a rescue credits
    allies, a ransom moved money, a release was the captor's choice.
    """

    HELD = "held", "Held"
    ESCAPED = "escaped", "Escaped"
    RESCUED = "rescued", "Rescued"
    RANSOMED = "ransomed", "Ransomed"
    RELEASED = "released", "Released"


# The four states in which a captivity is over and the captive walks free.
RESOLVED_STATUSES = frozenset(
    {
        CaptivityStatus.ESCAPED,
        CaptivityStatus.RESCUED,
        CaptivityStatus.RANSOMED,
        CaptivityStatus.RELEASED,
    }
)
