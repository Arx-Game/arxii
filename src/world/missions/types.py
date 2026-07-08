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
class JournalInvite:
    """A pending mission invite addressed to the viewer's persona (#2049).

    Surfaced on the journal so the web can show incoming invites with
    accept/decline without a separate endpoint. Persona-scoped (not
    per-instance) — mirrors the telnet ``_append_pending_invites`` query
    (commands/missions.py). ``template_name`` is the invited-to mission's
    template name for display.
    """

    invite_id: int
    instance_id: int
    template_name: str


@dataclass(frozen=True)
class JournalSummons:
    """A pending summons directed at the viewer's persona (#2050).

    Persona-scoped (not per-instance). Mirrors the telnet
    ``_append_pending_summonses`` query (commands/missions.py).
    """

    summons_id: int
    role_name: str
    message: str
    expires_at: str | None


@dataclass(frozen=True)
class JournalEntry:
    """One mission run as seen by one character.

    Built by ``world.missions.services.journal.journal_for(character)`` —
    one entry per :class:`~world.missions.models.MissionParticipant` row
    the character owns. Deterministically ordered by ``instance_id``.

    The compass fields (#885) answer "where do I go to continue this":
    ``compass_rooms`` is the publicly-knowable places the current beat can
    happen — node-level locations always; per-option override rooms only
    when the option is UNGATED (empty visibility rule). A gated option's
    location is never leaked by the journal; if the author wants it known,
    they write it into the node's flavor text. ``compass_anywhere`` is True
    when at least one live-relevant option follows you (ANYWHERE).
    """

    instance_id: int
    template_name: str
    status: str  # MissionStatus value
    current_node_key: str | None
    is_contract_holder: bool
    deeds: tuple[JournalDeed, ...]
    summary: str = ""
    epilogue: str = ""  # populated only once the run is COMPLETE
    current_node_flavor: str = ""
    compass_rooms: tuple[str, ...] = ()
    compass_anywhere: bool = False
    pending_invites: tuple[JournalInvite, ...] = ()
    pending_summons: tuple[JournalSummons, ...] = ()
    participant_count: int = 1
    target_project_name: str | None = None
    target_project_progress: int | None = None
    target_project_threshold: int | None = None
    target_project_granted: int = 0
    source_beat_story_title: str | None = None
    source_beat_hint: str | None = None
    tale: str | None = None  # the participant's authored epilogue, if any (#2047)
    can_tell_tale: bool = False  # run is terminal and tale hasn't been written (#2047)


@dataclass(frozen=True)
class BeatOption:
    """One actionable option on the current beat, as the player sees it (#885).

    Flattened off :class:`PresentedOption` for the player API — pks and
    labels only, no ORM objects. ``approach_id`` is set for fanned-out
    CHALLENGE entries (it must be echoed back on resolve).
    """

    option_id: int
    approach_id: int | None
    label: str
    kind: str  # OptionKind value
    check_type_name: str | None
    base_risk: int


@dataclass(frozen=True)
class BeatView:
    """The current beat of one run, as the acting character sees it (#885).

    ``options`` carries only the LIVE options (location conjunct ∧
    visibility predicate already applied) — visibility=eligibility, never
    a greyed-out entry. Empty options with an active node means "nothing
    you can do HERE" (the journal compass says where to go).
    """

    instance_id: int
    template_name: str
    node_key: str
    flavor_text: str
    options: tuple[BeatOption, ...]


@dataclass(frozen=True)
class ResolvedBeat:
    """Typed result of resolving one beat option (#885).

    ``story_text`` is the actor-facing narrative (also delivered as a
    STORY NarrativeMessage); ``next_beat`` is None when the run completed
    (``epilogue`` is then populated from the template bookend).
    """

    instance_id: int
    outcome_name: str | None
    story_text: str
    is_terminal: bool
    next_beat: BeatView | None
    epilogue: str


@dataclass(frozen=True)
class GroupBallotState:
    """One participant's pick/vote in the group-vote window (#1036)."""

    character_id: int
    character_name: str
    picked_option_id: int | None
    voted_option_id: int | None


@dataclass(frozen=True)
class GroupBeatView:
    """The group-decision beat — surfaced options + the party's ballots (#1036).

    ``options`` is the UNION group option list (every participant's live
    options, owner-tagged). ``phase`` is ``"pick"`` until every participant
    has picked, then ``"vote"``. ``expires_at`` is the ISO deadline (None
    until the first pick opens the window).
    """

    instance_id: int
    node_key: str
    flavor_text: str
    conflict_mode: str
    phase: str
    options: tuple[BeatOption, ...]
    ballots: tuple[GroupBallotState, ...]
    expires_at: str | None


@dataclass(frozen=True)
class GroupBeatResult:
    """A group pick/vote/beat response (#1036).

    Exactly one side is set: ``group_beat`` while the party is still
    collecting picks/votes, or ``resolved`` once the node resolved (all voted
    or the window timed out).
    """

    group_beat: GroupBeatView | None
    resolved: ResolvedBeat | None


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
class ProjectSkipRecord:
    """A PROJECT reward line that was soft-skipped at payout (#2045).

    The project was non-ACTIVE or the FK had gone null (SET_NULL) by report
    time. The player already did the work; no-silent-drop is satisfied by
    the explicit notice text carried here.
    """

    line_id: int
    amount: int
    project_name: str | None
    reason: str


@dataclass(frozen=True)
class ApplyDeedRewardsResult:
    """Typed return of :func:`world.missions.services.rewards.apply_deed_rewards`.

    ``enqueued`` carries the persisted :class:`MissionRewardQueue` rows
    created/refreshed by the call; ``stub_calls`` summarises each stub-seam
    invocation; ``errors`` is reserved for aggregated stub failures and is
    always empty in Phase 5b.1 (the function raises on the first stub
    failure today). ``project_skips`` carries PROJECT lines that were
    soft-skipped because the bound project was non-ACTIVE or null (#2045).
    """

    enqueued: tuple[MissionRewardQueue, ...] = ()
    stub_calls: tuple[StubCallRecord, ...] = ()
    errors: tuple[StubError, ...] = ()
    project_skips: tuple[ProjectSkipRecord, ...] = ()


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


@dataclass(frozen=True)
class SupportMove:
    """One support move offered to a helper at a node (#2046).

    Built by ``world.missions.services.support.support_moves_for``. Fanned
    from the helper's own capabilities (via the capability oracle) and/or
    a predicate-tree leg, matched against the node's live CHECK options.
    ``rumored`` moves are offered as tease-only entries (the whole party
    sees them regardless of qualification).
    """

    source_id: int
    source_kind: str  # "pattern" or "gem"
    label: str
    capability_name: str | None
    check_type_name: str
    difficulty: int
    easing: int
    flavor: str
    rumored: bool
    rumor_text: str


@dataclass(frozen=True)
class SupportDeclarationView:
    """One participant's declared support at a node, for journal/beat display."""

    character_id: int
    character_name: str
    label: str
    outcome_name: str | None
    easing_banked: int
