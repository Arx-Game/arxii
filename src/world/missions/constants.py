"""Shared constants and choices for the Missions system.

TextChoices live here (not as nested model classes) so serializers and the
resolution service can reference them without circular imports.
"""

from django.db import models

# Upper bound for MissionTemplate.percent_replace (a percentage).
MAX_PERCENT_REPLACE = 100


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


class RewardGroupRule(models.TextChoices):
    """How a multi-participant mission's rewards are split (authoring knob).

    This is the *authoring* knob only; the actual reward distribution by
    rule is Phase 5 (reward lines are Phase-5-deferred). ALL_EQUAL — every
    participant gets the same payout; BY_ROLE — payout varies by the
    participant's authored role; BY_PARTICIPATION — payout scales with each
    participant's recorded contribution.
    """

    ALL_EQUAL = "all_equal", "All Equal"
    BY_ROLE = "by_role", "By Role"
    BY_PARTICIPATION = "by_participation", "By Participation"


class OptionKind(models.TextChoices):
    """Whether a :class:`~world.missions.models.MissionOption` branches the
    graph directly or resolves a dice check first.

    An authored option declares its kind explicitly; a CHALLENGE-sourced
    option is always CHECK (every ``ChallengeApproach`` resolves a check or
    auto-succeeds).
    """

    BRANCH = "branch", "Branch"
    CHECK = "check", "Check"


class OptionSource(models.TextChoices):
    """Where a :class:`~world.missions.models.MissionOption` comes from.

    AUTHORED — hand-written by the mission author on this node;
    CHALLENGE — references a ``mechanics.ChallengeTemplate`` whose approaches
    fan out into challenge-contributed options at runtime.
    """

    AUTHORED = "authored", "Authored"
    CHALLENGE = "challenge", "Challenge"


class MissionStatus(models.TextChoices):
    """Lifecycle of a :class:`~world.missions.models.MissionInstance`."""

    ACTIVE = "active", "Active"
    COMPLETE = "complete", "Complete"
    ABANDONED = "abandoned", "Abandoned"
    EXPIRED = "expired", "Expired"


class MissionVisibility(models.TextChoices):
    """Who can see / be offered a :class:`~world.missions.models.MissionTemplate` (#870).

    Visibility IS eligibility (one predicate, no two-predicate split):

    OPEN — everyone; the ``availability_rule`` predicate is not consulted.
    RESTRICTED — eligibility = the ``availability_rule`` predicate; whoever
    passes it sees the template. A RESTRICTED template with an empty rule
    admits no PC at all — the emergent "staff-only / in testing" state and
    the production-safe default for new templates.

    Staff (``is_staff_observer``) always bypass both modes. There is
    deliberately no STAFF_ONLY value — staff-only is the degenerate case of
    "no PC is eligible", not a separate audience tier.
    """

    OPEN = "open", "Open"
    RESTRICTED = "restricted", "Restricted"


class NodeLocationMode(models.TextChoices):
    """Where a :class:`~world.missions.models.MissionNode`'s options are live (#885).

    The node value is the DEFAULT for its options; an option with its own
    ``locations`` rows overrides it. Location is a conjunct of the single
    eligibility rule (visibility predicate ∧ "am I there"), never a second
    visibility layer.

    ANYWHERE — options live in whatever room the character is in (default;
    introspective beats, wrap-ups).
    ANCHOR — options live only in the instance's ``anchor_room`` (recorded
    at grant time) — keeps reusable trigger-pool templates location-flavored
    without authored rooms.
    ROOMS — options live in the node's authored ``locations`` set.
    INSTANCE — options live only in the instanced room this run spawned
    (#886); before anything spawns, they are nowhere.
    """

    ANYWHERE = "anywhere", "Anywhere"
    ANCHOR = "anchor", "Anchor Room"
    ROOMS = "rooms", "Authored Rooms"
    INSTANCE = "instance", "Spawned Instance"


class GiverKind(models.TextChoices):
    """How a :class:`~world.missions.models.MissionGiver` reaches the player.

    NPC-mediated givers migrated to ``NPCRole`` + ``NPCServiceOffer`` per
    #686. ``MissionGiver`` survives for the two trigger-based kinds whose
    dispatch is different from "player talks to an NPC":

    ROOM_TRIGGER — entering ``target`` (a Room) rolls the offer;
    ENVIRONMENTAL_DETAIL — examining ``target`` (an item/detail) emits
    the offer.

    Trigger-based offers will be designed as a follow-up; for now the
    catalog choices restrict to the two surviving kinds so authoring tools
    can't accidentally re-introduce the NPC variant.
    """

    ENVIRONMENTAL_DETAIL = "environmental_detail", "Environmental Detail"
    ROOM_TRIGGER = "room_trigger", "Room Trigger"


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
