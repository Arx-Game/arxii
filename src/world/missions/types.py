"""Type declarations for mission-specific dataclasses.

Predicate-engine types (``ResolverContext``, ``LeafResolver``,
``LeafRegistry``, ``PredicateContext``) live in
``world.predicates.types`` — they were extracted from this module when
the engine became a shared utility (consumed by missions + npc_services
+ future systems).

This file now only carries types specific to mission deeds / rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.mechanics.models import ChallengeApproach
    from world.missions.models import (
        MissionOption,
        MissionParticipant,
        MissionRewardQueue,
    )


@dataclass(frozen=True)
class DeedRewardLine:
    """One structured reward line emitted when a mission deed is recorded.

    This is the *in-memory / return* shape produced by the Phase 3 engine
    and consumed by the Phase 5 payout cron. Its persisted counterpart is
    :class:`~world.missions.models.MissionDeedRewardLine` (one row per line).
    Deliberately NOT a bare ``dict`` — ``kind``/``sink`` correspond to the
    ``DeedRewardKind``/``DeedRewardSink`` TextChoices and ``payload`` is a
    typed, hashable structure (an immutable tuple of key/value pairs), never
    free-form JSON.
    """

    kind: str  # DeedRewardKind value
    sink: str  # DeedRewardSink value
    payload: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ChallengeOption:
    """One challenge-contributed option surfaced at a node for a character.

    Built by
    ``world.missions.services.challenge_options.challenge_options_for_character``
    for each ``mechanics.ChallengeApproach`` of a node's attached challenges
    that the acting character qualifies for — they hold the approach's
    ``Application.capability`` (decided by the Phase-0 ``has_capability``
    resolver) — or that is ``is_default`` (offered to everyone). Fields are
    flattened off the approach/challenge so resolution callers never re-walk
    the FK side.

    The challenge↔missions integration is *data-source* (findings doc Q2): a
    challenge is consumed as authored data, never run as an engine. Of the
    ``ChallengeTemplate`` fields only ``severity`` rides along — it is
    ``difficulty`` here (design §8.4 Q4). ``auto_succeeds`` mirrors the
    approach flag; an auto-success option skips the roll at resolution time.
    """

    approach: ChallengeApproach
    check_type: CheckType
    auto_succeeds: bool
    difficulty: int
    owner: ObjectDB


@dataclass(frozen=True)
class GroupChoice:
    """The resolution decision for a multi-participant :class:`MissionNode`.

    Produced by ``world.missions.services.multiplayer.select_group_choice``
    from the per-participant ``picks`` and the node's ``conflict_mode``.

    * COINFLIP / VOTE — a *single* winning option is chosen and one acting
      participant is selected (``option`` and ``actor`` set; ``attempts``
      empty). The Phase-3 ``resolve_option`` then performs that one option as
      ``actor`` (moral consequence follows the actor).
    * JOINT — there is NO single winner. ``attempts`` carries the full set of
      (participant, option) pairs; every participant runs their own pick and
      the orchestrator combines the per-participant outcomes per the node's
      ``joint_combine`` / ``joint_count``. ``option`` and ``actor`` are None.

    Not a bare dict — ``attempts`` is an immutable tuple of typed pairs.
    """

    is_joint: bool
    option: MissionOption | None = None
    actor: MissionParticipant | None = None
    attempts: tuple[tuple[MissionParticipant, MissionOption], ...] = ()


@dataclass(frozen=True)
class JournalDeed:
    """One recorded deed within a journal entry — the player-facing slice.

    Mirrors a :class:`~world.missions.models.MissionDeedRecord` row, but
    flattened/frozen so the journal API is pure data (no ORM round-trips
    when callers walk the list). ``outcome_name`` is the tier name (or
    ``None`` for a BRANCH deed); ``option_id`` lets callers cross-reference
    the authored graph if they want.
    """

    node_key: str
    option_id: int
    outcome_name: str | None
    applied_at: datetime


@dataclass(frozen=True)
class JournalEntry:
    """One mission run as seen by one character.

    Built by ``world.missions.services.journal.journal_for(character)`` —
    one entry per :class:`~world.missions.models.MissionParticipant` row
    the character owns. Deterministically ordered by ``instance_id``.
    """

    instance_id: int
    template_name: str
    status: str  # MissionStatus value
    current_node_key: str | None
    is_contract_holder: bool
    deeds: tuple[JournalDeed, ...]


@dataclass(frozen=True)
class StubCallRecord:
    """A summary of one stub-seam invocation during ``apply_deed_rewards``.

    Phase 5b.1 emits these for telemetry/tests so callers can verify that
    money / beat stubs fired without re-querying the in-memory stub logs.
    """

    sink: str  # DeedRewardSink value
    line_id: int


@dataclass(frozen=True)
class StubError:
    """A recorded stub-seam failure (Phase 5b.1).

    Reserved for the future where ``apply_deed_rewards`` may aggregate
    multiple failures instead of raising on the first. For now the function
    raises and this list is always empty — but the field is part of the
    typed result so callers can pattern-match without conditional shape.
    """

    sink: str  # DeedRewardSink value
    line_id: int
    message: str


@dataclass(frozen=True)
class ApplyDeedRewardsResult:
    """Typed return of :func:`world.missions.services.rewards.apply_deed_rewards`.

    ``enqueued`` carries the persisted :class:`MissionRewardQueue` rows
    created/refreshed by the call; ``stub_calls`` summarises each stub-seam
    invocation; ``errors`` is reserved for aggregated stub failures and is
    always empty in Phase 5b.1 (the function raises on the first stub
    failure today).
    """

    enqueued: tuple[MissionRewardQueue, ...] = ()
    stub_calls: tuple[StubCallRecord, ...] = ()
    errors: tuple[StubError, ...] = ()


@dataclass(frozen=True)
class RewardBatchResult:
    """Typed return of :func:`world.missions.services.cron.apply_mission_reward_batch`.

    ``applied`` carries the queue rows that were granted downstream and
    flipped to ``applied=True`` during this batch; ``failed`` carries the
    rows whose helper raised (each row's ``failure_reason`` was populated
    in the row itself and the row stayed at ``applied=False``).

    In Phase 5b.2 ``applied`` is always empty because both LP and Resonance
    grant helpers are stub-sealed pending payload enrichment (see DESIGN
    §13.3). The dataclass shape is final so 5b.3+ (which fills in real
    grant helpers) does not need to change the public return type.
    """

    applied: tuple[MissionRewardQueue, ...] = ()
    failed: tuple[MissionRewardQueue, ...] = ()


@dataclass(frozen=True)
class MissionBeatTriggerRecord:
    """One recorded mission→Beat trigger emitted by ``_finish_terminal``.

    Phase 5b.3 stub-record carrier for the stories-missions seam. When a
    :class:`~world.missions.models.MissionInstance` with ``source_beat`` set
    reaches a terminal route, ``world.missions.services.beat.on_mission_complete_for_beat``
    appends one of these to its module-level log; tests assert the trigger
    was recorded. The actual "complete the Beat" engine is deferred — see
    the service module's docstring for the three deferred design questions.

    Mirrors the shape of :class:`BeatStubCall` (the reward-line BEAT sink's
    stub-record) so future engine work can converge them with no shape
    change. ``triggered_at`` is the wall-clock moment of the call (DB writes
    in 5b.3 are zero; this is a pure in-memory marker).
    """

    instance_pk: int
    beat_pk: int
    triggered_at: datetime


@dataclass(frozen=True)
class PresentedOption:
    """One player-facing option surfaced at a node for the acting participant.

    Built by ``world.missions.services.resolution.build_option_list``. A
    CHALLENGE-sourced :class:`~world.missions.models.MissionOption` fans out
    into one ``PresentedOption`` per qualifying ``ChallengeApproach``
    (``approach`` set); an AUTHORED option produces a single entry
    (``approach`` None) when its visibility predicate passes. Fields are
    flattened off the approach/option so resolution callers never re-walk
    the FK side. ``owner`` is the acting participant's character (Phase 4
    generalizes to per-participant owners in the multi-participant union).
    """

    option: MissionOption
    kind: str  # OptionKind value
    check_type: CheckType | None
    base_risk: int
    ic_framing: str
    owner: ObjectDB
    approach: ChallengeApproach | None = None
