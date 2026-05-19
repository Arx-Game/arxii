"""Type declarations for the missions predicate evaluator.

Phase 0 ships the structural rule-tree evaluator plus its leaf-resolver
registry. The rule tree itself is the one sanctioned dynamic-JSON case in
this codebase (it mirrors the shape of
``world.distinctions.models.DistinctionPrerequisite.rule_json``), so the
evaluator accepts a plain ``dict`` as *input*. Everything else stays typed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType, Consequence
    from world.missions.models import (
        AffordanceBinding,
        MissionOption,
        MissionParticipant,
    )

# A leaf resolver tests one slice of the acting character's own durable
# state. It receives the acting character (ObjectDB) plus the leaf's
# authored params (keyword-only) and returns a bool. The registry maps a
# leaf name to one resolver.
LeafResolver = Callable[..., bool]
LeafRegistry = dict[str, LeafResolver]


@runtime_checkable
class PredicateContext(Protocol):
    """Read-only durable-state accessor for the acting character.

    Phase 0 ships the structural evaluator + leaf-resolver registry only.
    A leaf node in the rule tree is resolved by calling ``has_leaf`` with
    the leaf name and the leaf's authored params; the implementation tests
    the *acting character's own durable state* and never inspects a target.
    """

    def has_leaf(self, leaf: str, **params: object) -> bool: ...


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
class ResolvedOption:
    """One surfaced player option produced from an owned descriptor binding.

    Built by ``world.missions.services.bindings_for_character`` for each
    :class:`~world.missions.models.AffordanceBinding` whose affordance the
    challenge accepts AND whose descriptor the acting character owns. Fields
    are flattened off the binding so resolution callers never re-walk the FK
    side. ``owner`` is the acting character (an ``ObjectDB``); Phase 4
    generalizes this to per-participant owners and the default stays the
    acting character.
    """

    binding: AffordanceBinding
    produces: str
    check_type: CheckType | None
    base_risk: int
    ic_framing: str
    rider: Consequence | None
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
class PresentedOption:
    """One player-facing option surfaced at a node for the acting participant.

    Built by ``world.missions.services.resolution.build_option_list``. An
    AFFORDANCE-sourced :class:`~world.missions.models.MissionOption` fans out
    into one ``PresentedOption`` per owned descriptor binding (``binding`` set,
    ``owner`` the acting character); an AUTHORED option produces a single entry
    (``binding`` None) when its visibility predicate passes. Fields are
    flattened off the binding/option so resolution callers never re-walk the
    FK side. Phase 3 is single-participant — ``owner`` is the acting
    participant's character; Phase 4 generalizes to per-participant owners.
    """

    option: MissionOption
    kind: str  # OptionKind value
    check_type: CheckType | None
    base_risk: int
    ic_framing: str
    owner: ObjectDB
    binding: AffordanceBinding | None
