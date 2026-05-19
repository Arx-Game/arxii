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
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType, Consequence
    from world.missions.models import AffordanceBinding, MissionOption

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
