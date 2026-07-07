from collections.abc import Mapping
import types

from django.db import models


class EraStatus(models.TextChoices):
    UPCOMING = "upcoming", "Upcoming"
    ACTIVE = "active", "Active"
    CONCLUDED = "concluded", "Concluded"


class StoryScope(models.TextChoices):
    UNASSIGNED = "unassigned", "Unassigned"
    CHARACTER = "character", "Personal"
    GROUP = "group", "Group"
    GLOBAL = "global", "Global"


class ImpactTier(models.TextChoices):
    """Story-side canon-impact tier — how far this story touches the shared world (#2003).

    Orthogonal to combat.StakesLevel (GM access scope) and Beat.risk (declared
    magnitude): this is the story-level review axis. TABLE is never reviewed;
    REGIONAL auto-clears for EXPERIENCED+ GMs; WORLD requires staff sign-off
    before staked beats pay (auto-downgrade, never hard-block).
    """

    TABLE = "table", "Table"
    REGIONAL = "regional", "Regional"
    WORLD = "world", "World"


class CanonReviewStatus(models.TextChoices):
    """Lifecycle of a CanonReview request (#2003)."""

    PENDING = "pending", "Pending"
    CLEARED = "cleared", "Cleared"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"


class StoryMaturity(models.TextChoices):
    """Authoring-completeness of a Story / Chapter / Episode node.

    Orthogonal to runtime StoryStatus. Per-node and fully independent — no
    cross-node ordering, parent/child, or DAG-reachability constraint.
    """

    PITCH = "pitch", "Pitch"
    OUTLINE = "outline", "Outline"
    PLOT = "plot", "Plot"


class BeatKind(models.TextChoices):
    """What a beat *is*. Resolution still flows through predicate_type."""

    SITUATION = "situation", "Situation"
    ENCOUNTER = "encounter", "Encounter"
    TASK = "task", "Task"
    REQUIREMENT = "requirement", "Requirement"


class ProgressStatus(models.TextChoices):
    """Finer-grained pointer state. is_active stays True for ACTIVE /
    WAITING_FOR_GM / RESTING; COMPLETED and FORECLOSED set is_active False.

    FORECLOSED is the honest terminal state for a run still in flight when its
    story is concluded: distinct from COMPLETED (the run genuinely reached an
    ending) so an unfinished thread is never falsely reported done, nor left
    orphaned in a live state."""

    ACTIVE = "active", "Active"
    WAITING_FOR_GM = "waiting_for_gm", "Waiting for GM"
    RESTING = "resting", "Resting"
    COMPLETED = "completed", "Completed"
    FORECLOSED = "foreclosed", "Foreclosed (story ended; thread unresolved)"


class BeatPredicateType(models.TextChoices):
    GM_MARKED = "gm_marked", "GM-marked"
    CHARACTER_LEVEL_AT_LEAST = "character_level_at_least", "Character level at least"
    ACHIEVEMENT_HELD = "achievement_held", "Achievement held"
    CONDITION_HELD = "condition_held", "Condition held"
    CODEX_ENTRY_UNLOCKED = "codex_entry_unlocked", "Codex entry unlocked"
    STORY_AT_MILESTONE = "story_at_milestone", "Referenced story at milestone"
    AGGREGATE_THRESHOLD = "aggregate_threshold", "Aggregate threshold reached"
    OUTCOME_TIER = "outcome_tier", "Outcome tier (machine-graded)"
    FACTION_STANDING_AT_LEAST = "faction_standing_at_least", "Faction standing at least"


class StoryMilestoneType(models.TextChoices):
    """Which kind of milestone a STORY_AT_MILESTONE beat checks against."""

    STORY_RESOLVED = "story_resolved", "Story resolved"
    CHAPTER_REACHED = "chapter_reached", "Chapter reached or passed"
    EPISODE_REACHED = "episode_reached", "Episode reached or passed"


class AssistantClaimStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class SessionRequestStatus(models.TextChoices):
    OPEN = "open", "Open — awaiting scheduling"
    SCHEDULED = "scheduled", "Scheduled (Event created)"
    RESOLVED = "resolved", "Resolved (session complete)"
    CANCELLED = "cancelled", "Cancelled"


class BeatOutcome(models.TextChoices):
    UNSATISFIED = "unsatisfied", "Unsatisfied"
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    EXPIRED = "expired", "Expired"
    PENDING_GM_REVIEW = "pending_gm_review", "Pending GM review"


class BeatVisibility(models.TextChoices):
    HINTED = "hinted", "Hinted"
    SECRET = "secret", "Secret"
    VISIBLE = "visible", "Visible"


class TransitionMode(models.TextChoices):
    AUTO = "auto", "Auto"
    GM_CHOICE = "gm_choice", "GM Choice"


class StoryGMOfferStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"


class CrossoverInviteStatus(models.TextChoices):
    """Lifecycle of a CrossoverInvite — Lead-GM consent to link a story (#2002)."""

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    WITHDRAWN = "withdrawn", "Withdrawn"


class StoryEpisodeStatus(models.TextChoices):
    """Coarse status of a story's current episode, exposed via dashboards.

    Callers consume the status code and render their own labels / UI;
    the service does not return human-readable strings.
    """

    ON_HOLD = "on_hold", "On hold (frontier — unauthored next)"
    WAITING_ON_BEATS = "waiting_on_beats", "Waiting on progression beats"
    READY_TO_RESOLVE = "ready_to_resolve", "Ready to resolve (auto-advance possible)"
    READY_TO_SCHEDULE = "ready_to_schedule", "Ready to schedule GM session"
    SCHEDULED = "scheduled", "GM session scheduled"


class StakeSeverity(models.IntegerChoices):
    """How bad losing (or how good winning) a single stake is.

    The calibration bands in RiskCalibration compare against these values:
    total-wagered floor (sum across a beat's stakes) and single-stake ceiling.
    REMOVAL is the character-loss band — a stake at this severity satisfies the
    jeopardy-reachability rule (#1770 chain rule) by itself.
    """

    SETBACK = 1, "Setback"
    COSTLY = 2, "Costly"
    GRAVE = 3, "Grave"
    DIRE = 4, "Dire"
    REMOVAL = 5, "Removal from play"


class StakeSubjectKind(models.TextChoices):
    """What kind of thing a Stake wagers. Typed subject FKs on Stake are
    populated per kind; CUSTOM carries only subject_label + narrative."""

    PERSONAL_JEOPARDY = "personal_jeopardy", "Personal jeopardy"
    NPC_FATE = "npc_fate", "NPC fate"
    LOCATION = "location", "Location"
    FACTION = "faction", "Faction relationship"
    ITEM = "item", "Item"
    CAMPAIGN_TRACK = "campaign_track", "Campaign track"
    CUSTOM = "custom", "Custom (trust-gated)"


class StakeResolutionColumn(models.TextChoices):
    """Which outcome column of the contract a StakeResolution authors."""

    WIN = "win", "Win"
    LOSS = "loss", "Loss"
    WITHDRAWAL = "withdrawal", "Withdrawal"


class StakeRewardSink(models.TextChoices):
    """Where a StakeRewardLine's payout lands (#1770 PR3 — two-sided contract).

    Only sinks with a real, coherent delivery service are offered: MONEY
    (world.currency.services.deliver_mission_money) and RESONANCE
    (world.magic.services.resonance.grant_resonance). Legend is deliberately
    NOT a sink — it stays automatic on top via effective risk (pillar 6).
    """

    MONEY = "money", "Money"
    RESONANCE = "resonance", "Resonance"


class StakeOutcomeMethod(models.TextChoices):
    """How a StakeOutcome was decided (#1770 PR2).

    MACHINE: graded automatically by the completion tail (beat outcome column,
    with data-where-it-exists overrides such as NPC vitals DEAD -> LOSS).
    GM_PICK: a GM chose among the stake's authored columns (constrained pick —
    never free composition).
    """

    MACHINE = "machine", "Machine"
    GM_PICK = "gm_pick", "GM pick"


# Risk ladder for effective-risk shifts (index order matters).
RISK_LADDER: tuple[str, ...] = (
    # RenownRisk values, weakest to strongest.
    "none",
    "low",
    "moderate",
    "high",
    "extreme",
)

# Seed values for RiskCalibration rows (designer-tunable in admin afterwards).
# max_fuse_hops implements the chain rule: how many failure-cascade hops may
# separate this tier from a reachable removal-from-play stake. EXTREME = 0:
# the beat itself must offer removal.
# reward_floor/reward_ceiling band the total declared WIN-column reward value
# (money-equivalent scalars summed across the beat's StakeRewardLine rows,
# #1770 PR3). Starting values — designer-tunable rows, not invariants. LOW's
# floor stays 0 so a zero-reward LOW contract remains ready.
DEFAULT_RISK_CALIBRATIONS: Mapping[str, dict[str, int]] = types.MappingProxyType(
    {
        "low": {
            "severity_floor_total": 1,
            "severity_ceiling": 2,
            "max_fuse_hops": 3,
            "reward_floor": 0,
            "reward_ceiling": 200,
        },
        "moderate": {
            "severity_floor_total": 2,
            "severity_ceiling": 3,
            "max_fuse_hops": 2,
            "reward_floor": 100,
            "reward_ceiling": 600,
        },
        "high": {
            "severity_floor_total": 4,
            "severity_ceiling": 4,
            "max_fuse_hops": 1,
            "reward_floor": 300,
            "reward_ceiling": 1500,
        },
        "extreme": {
            "severity_floor_total": 6,
            "severity_ceiling": 5,
            "max_fuse_hops": 0,
            "reward_floor": 800,
            "reward_ceiling": 4000,
        },
    }
)


class CustodyScope(models.TextChoices):
    """How far a StoryProtectedSubject's custody protection reaches (#2001).

    Ordered weakest->strongest, mirroring RISK_LADDER: APPEAR only guarantees
    the subject can still appear in scenes; HARM additionally blocks
    non-participant harm; REMOVE additionally blocks removal from play
    (death/destruction/disbandment) — the strongest guarantee.
    """

    APPEAR = "appear", "Guaranteed appearance"
    HARM = "harm", "Protected from harm"
    REMOVE = "remove", "Protected from removal"


# Custody scope ladder for comparisons (index order matters, weakest->strongest).
CUSTODY_SCOPE_ORDER: tuple[str, ...] = (
    CustodyScope.APPEAR,
    CustodyScope.HARM,
    CustodyScope.REMOVE,
)


def custody_scope_index(scope: str) -> int:
    """Position of a CustodyScope value on the weakest->strongest ladder."""
    return CUSTODY_SCOPE_ORDER.index(scope)


class CustodyClearanceStatus(models.TextChoices):
    """Lifecycle of a GM clearance request to act against a protected subject.

    Used by Task 3 (clearance requests); defined here alongside CustodyScope
    since both are the custody domain's shared vocabulary.
    """

    PENDING = "pending", "Pending"
    GRANTED = "granted", "Granted"
    DENIED = "denied", "Denied"
    ESCALATED = "escalated", "Escalated"


# How many days a PENDING CustodyClearance may sit before the requester may
# escalate it to staff without waiting for a DENIED response. Designer-tunable
# later (see #2001 Task 3 brief) — a module constant is enough for now; do not
# invent a config model for this single knob.
CUSTODY_ESCALATION_STALE_DAYS = 7
