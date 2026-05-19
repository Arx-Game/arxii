"""Shared constants and choices for the Missions system (Phase 1).

TextChoices live here (not as nested model classes) so serializers and the
affordance-resolution service can reference them without circular imports.
"""

from django.db import models

# Upper bound for MissionTemplate.percent_replace (a percentage).
MAX_PERCENT_REPLACE = 100


class OptionProduces(models.TextChoices):
    """What an :class:`~world.missions.models.AffordanceBinding` yields.

    A binding either surfaces a narrative BRANCH (no dice — the descriptor
    simply unlocks a path) or a CHECK (resolved by a ``checks.CheckType``
    with an authored base risk).
    """

    BRANCH = "branch", "Branch"
    CHECK = "check", "Check"


# ---------------------------------------------------------------------------
# Phase 2 — mission graph data model choices
# ---------------------------------------------------------------------------


class ArcScope(models.TextChoices):
    """Where a :class:`~world.missions.models.MissionTemplate` is offered.

    GLOBAL — available game-wide; ORG — scoped to an organization's givers;
    GIVER — bound to a single mission-giver.
    """

    GLOBAL = "global", "Global"
    ORG = "org", "Organization"
    GIVER = "giver", "Giver"


class ConflictMode(models.TextChoices):
    """How a multi-participant :class:`~world.missions.models.MissionNode`
    resolves contested option choices.

    COINFLIP — random tiebreak; VOTE — majority of participants; JOINT — a
    combined check governed by ``joint_combine``/``joint_count``.
    """

    COINFLIP = "coinflip", "Coin Flip"
    VOTE = "vote", "Vote"
    JOINT = "joint", "Joint"


class JointCombine(models.TextChoices):
    """How a JOINT-mode node combines participant check results.

    ANY — one success suffices; ALL — every participant must succeed;
    COUNT — at least ``joint_count`` participants must succeed.
    """

    ANY = "any", "Any"
    ALL = "all", "All"
    COUNT = "count", "Count"


class OptionKind(models.TextChoices):
    """Whether a :class:`~world.missions.models.MissionOption` branches the
    graph directly or resolves a dice check first.

    Mirrors :class:`OptionProduces` but is the *node-graph* spelling; an
    affordance-sourced option inherits its kind from the binding's
    ``produces`` while an authored option declares it explicitly.
    """

    BRANCH = "branch", "Branch"
    CHECK = "check", "Check"


class OptionSource(models.TextChoices):
    """Where a :class:`~world.missions.models.MissionOption` comes from.

    AFFORDANCE — surfaced from a character's owned descriptor bindings;
    AUTHORED — hand-written by the mission author on this node.
    """

    AFFORDANCE = "affordance", "Affordance"
    AUTHORED = "authored", "Authored"


class MissionStatus(models.TextChoices):
    """Lifecycle of a :class:`~world.missions.models.MissionInstance`."""

    ACTIVE = "active", "Active"
    COMPLETE = "complete", "Complete"
    ABANDONED = "abandoned", "Abandoned"
    EXPIRED = "expired", "Expired"


class DeedRewardKind(models.TextChoices):
    """When a :class:`~world.missions.models.MissionDeedRewardLine` pays out.

    IMMEDIATE — applied at deed time; POST_CRON — deferred to the rewards
    cron (Phase 5); PROPAGATION — fans out to rumor/crime-watch/beat seams.
    """

    IMMEDIATE = "immediate", "Immediate"
    POST_CRON = "post_cron", "Post Cron"
    PROPAGATION = "propagation", "Propagation"


class DeedRewardSink(models.TextChoices):
    """What ledger a :class:`~world.missions.models.MissionDeedRewardLine`
    pays into."""

    MONEY = "money", "Money"
    LEGEND_POINTS = "legend_points", "Legend Points"
    RESONANCE = "resonance", "Resonance"
    RUMOR = "rumor", "Rumor"
    CRIME_WATCH = "crime_watch", "Crime Watch"
    BEAT = "beat", "Beat"
