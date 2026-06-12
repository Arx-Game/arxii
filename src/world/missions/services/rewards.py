"""Terminal-route reward emission (Phase 5b.0) — pure service functions.

Phase 3 emitted a :class:`MissionDeedRecord` at every resolved option but no
:class:`MissionDeedRewardLine` rows at terminal routes — there was no
authored-reward source. Phase 5b.0 closes that gap:

  * :class:`MissionOptionRouteReward` is the authored source: one row per
    template-author-declared reward attached to a terminal route.
  * :func:`emit_terminal_rewards` is the engine seam: it walks
    ``route.reward_templates`` and creates one
    :class:`MissionDeedRewardLine` per (template × recipient), where the
    recipient set is determined by
    ``instance.template.reward_group_rule`` (broadcast rows) or the
    instance's contract holder (contract_holder_only rows).

ALL_EQUAL is the only multi-participant distribution rule implemented in
Phase 5b.0. BY_ROLE and BY_PARTICIPATION are stub-sealed: this module raises
:class:`NotImplementedError` against either, so a mission authored against
an unbuilt distribution rule surfaces early rather than silently degrading
to ALL_EQUAL. Per-participant role and contribution tracking (the data
those rules depend on) is Phase-6+ work — see
``docs/plans/2026-05-18-missions-design.md`` §11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.currency.services import deliver_mission_money
from world.missions.constants import DeedRewardKind, DeedRewardSink, RewardGroupRule
from world.missions.integrations import beat_stub, crime_watch_stub, money_stub, rumor_stub
from world.missions.models import MissionDeedRewardLine, MissionRewardQueue
from world.missions.types import ApplyDeedRewardsResult, StubCallRecord

if TYPE_CHECKING:
    from world.missions.models import (
        MissionDeedRecord,
        MissionInstance,
        MissionOptionRoute,
        MissionOptionRouteReward,
        MissionParticipant,
    )


class MissionRewardRoutingError(Exception):
    """Author-error: a :class:`MissionDeedRewardLine` declared an unsupported
    ``(kind, sink)`` combination.

    Follows the project's typed-exception convention so views and callers
    surface a safe message rather than raw ``str(exc)``. The error message
    embedded into the exception names the offending pair so authoring
    tooling can point straight at the bad row.
    """

    _SAFE_MESSAGE = (
        "This mission has a reward configured with an unsupported kind/sink combination."
    )

    def __init__(self, kind: str, sink: str, line_pk: int | None = None) -> None:
        self.kind = kind
        self.sink = sink
        self.line_pk = line_pk
        detail = f"Unsupported reward routing: kind={kind!r} sink={sink!r} line={line_pk!r}"
        super().__init__(detail)

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGE


# DESIGN: Phase 6+ — requires participant role/contribution tracking
# (see docs/plans/2026-05-18-missions-design.md §11).
_ERR_UNIMPLEMENTED_RULE = (
    "reward_group_rule={rule!r} is not implemented in Phase 5b.0; "
    "missions authored against it must wait for Phase 6+ which adds the "
    "participant role/contribution tracking BY_ROLE/BY_PARTICIPATION require."
)
_ERR_NON_TERMINAL_ROUTE = (
    "emit_terminal_rewards called with a non-terminal route "
    "(target_node_id={target_node_id!r}); callers must only emit rewards at "
    "terminal routes."
)
_ERR_MISSING_CONTRACT_HOLDER = (
    "MissionInstance {instance_pk} has no contract-holding participant; "
    "cannot emit a contract_holder_only reward line."
)


def _ordered_participants(instance: MissionInstance) -> list[MissionParticipant]:
    """All participants of ``instance``, deterministically ordered by pk.

    Single query (``select_related("character")`` keeps the recipient FK walk
    identity-mapped — no per-row character lookup); the resulting list is
    reused across every broadcast reward template, so multi-row authoring
    does not multiply queries by templates.
    """
    return list(instance.participants.select_related("character").order_by("pk"))


def _contract_holder(participants: list[MissionParticipant]) -> MissionParticipant:
    """The instance's contract holder.

    Raises ``ValueError`` when no holder is present — an active mission
    instance must always have one; silently dropping a contract_holder_only
    reward would mask the broken invariant.
    """
    holder = next((p for p in participants if p.is_contract_holder), None)
    if holder is None:
        # Caller passes the instance in for context; we recover it from any
        # participant if available, else from the first row's instance_id.
        instance_pk = participants[0].instance_id if participants else None
        raise ValueError(_ERR_MISSING_CONTRACT_HOLDER.format(instance_pk=instance_pk))
    return holder


def _line_for(
    deed: MissionDeedRecord,
    template: MissionOptionRouteReward,
    recipient: MissionParticipant,
) -> MissionDeedRewardLine:
    """One MissionDeedRewardLine from a template + recipient pair (UNSAVED).

    The row is returned UNSAVED so callers can ``bulk_create`` them in one
    INSERT and abort the whole emission atomically if any template
    triggers the BY_ROLE / BY_PARTICIPATION stub-seal.
    """
    return MissionDeedRewardLine(
        deed=deed,
        recipient=recipient.character,
        kind=template.kind,
        sink=template.sink,
        amount=template.amount,
        ref=template.ref,
    )


def emit_terminal_rewards(
    instance: MissionInstance,
    route: MissionOptionRoute,
    deed: MissionDeedRecord,
) -> list[MissionDeedRewardLine]:
    """Emit one :class:`MissionDeedRewardLine` per (template × recipient).

    Called by the resolution engine after a terminal :class:`MissionDeedRecord`
    has been created (``next_node is None``). Walks ``route.reward_templates``
    and distributes per the template's ``contract_holder_only`` toggle and
    the instance's ``template.reward_group_rule``:

      * ``contract_holder_only=True`` rows → exactly one line, recipient =
        the instance's contract-holding participant's character (regardless
        of the deed actor).
      * ``contract_holder_only=False`` rows distributed per
        ``MissionTemplate.reward_group_rule``:
        - ``ALL_EQUAL`` → one line per participant, same amount.
        - ``BY_ROLE`` / ``BY_PARTICIPATION`` → :class:`NotImplementedError`
          (stub-sealed; Phase 6+ — requires participant role/contribution
          tracking).

    The entire emission is wrapped in a transaction: if any template
    triggers the stub-seal, NO lines are persisted (no partial writes).

    Args:
        instance: The mission run whose terminal route emitted ``deed``.
        route: The terminal :class:`MissionOptionRoute` that was traversed.
            MUST have ``target_node_id is None`` — caller bug to pass
            anything else.
        deed: The just-created terminal :class:`MissionDeedRecord` (the
            ``deed`` FK on every emitted line).

    Returns:
        The list of created :class:`MissionDeedRewardLine` rows (with PKs
        set) — useful for tests and downstream Phase 5b.1 routing.

    Raises:
        ValueError: ``route`` is non-terminal, or a contract_holder_only
            template is authored on an instance with no contract holder.
        NotImplementedError: ``instance.template.reward_group_rule`` is one
            of BY_ROLE / BY_PARTICIPATION (Phase 6+).
    """
    if route.target_node_id is not None:
        raise ValueError(_ERR_NON_TERMINAL_ROUTE.format(target_node_id=route.target_node_id))

    templates = list(route.reward_templates.all())
    if not templates:
        return []

    participants = _ordered_participants(instance)
    rule = instance.template.reward_group_rule

    # Build all rows BEFORE any DB write — so a stub-sealed rule aborts the
    # whole emission cleanly (no partial writes), even when the route also
    # carries contract_holder_only rows that would otherwise succeed.
    rows: list[MissionDeedRewardLine] = []
    holder: MissionParticipant | None = None
    for template in templates:
        if template.contract_holder_only:
            if holder is None:
                holder = _contract_holder(participants)
            rows.append(_line_for(deed, template, holder))
            continue
        # Broadcast row — distribute by reward_group_rule.
        if rule == RewardGroupRule.ALL_EQUAL:
            rows.extend(_line_for(deed, template, p) for p in participants)
        else:
            # RewardGroupRule.BY_ROLE / BY_PARTICIPATION — stub-sealed.
            raise NotImplementedError(_ERR_UNIMPLEMENTED_RULE.format(rule=rule))

    with transaction.atomic():
        return MissionDeedRewardLine.objects.bulk_create(rows)


# ---------------------------------------------------------------------------
# Phase 5b.1 — apply_deed_rewards routing
# ---------------------------------------------------------------------------
#
# The routing matrix below decides what each (kind, sink) line does when the
# engine asks ``apply_deed_rewards(deed)`` to deliver its emitted reward
# lines. See docstring on :func:`apply_deed_rewards` for the full table.

# Sinks that go onto the deferred-payout queue.
_QUEUE_SINKS = frozenset({DeedRewardSink.LEGEND_POINTS, DeedRewardSink.RESONANCE})


def _enqueue(deed: MissionDeedRecord, line: MissionDeedRewardLine) -> MissionRewardQueue:
    """Idempotently create (or refresh) the queue row for ``line``.

    ``UniqueConstraint(line)`` guarantees one queue row per line; using
    ``update_or_create`` on the line FK is the natural idempotent shape.
    Re-application leaves ``applied``/``applied_at`` whatever the prior
    state was (the cron is responsible for those columns) and only touches
    the mirrored ``kind``/``sink`` columns + the deed FK.
    """
    row, _created = MissionRewardQueue.objects.update_or_create(
        line=line,
        defaults={
            "deed": deed,
            "kind": line.kind,
            "sink": line.sink,
        },
    )
    return row


def _route_line(
    deed: MissionDeedRecord,
    line: MissionDeedRewardLine,
    enqueued: list[MissionRewardQueue],
    stub_calls: list[StubCallRecord],
) -> None:
    """Dispatch one emitted line by its ``(kind, sink)`` pair.

    Mutates ``enqueued``/``stub_calls`` in place so the caller can aggregate
    across all lines without rebuilding tuples per row. The PROPAGATION
    stubs raise ``NotImplementedError`` (rolls back the whole apply); the
    unsupported-combo case raises :class:`MissionRewardRoutingError` (also
    rolls back). Stub-record sinks (money, beat) never raise.
    """
    kind = line.kind
    sink = line.sink

    # BEAT may ride on any kind — Phase 5b.3 will replace the stub with
    # real Beat-completion wiring.
    if sink == DeedRewardSink.BEAT:
        beat_stub.propagate_beat(line)
        stub_calls.append(StubCallRecord(sink=sink, line_id=line.pk))
        return

    if kind == DeedRewardKind.POST_CRON and sink in _QUEUE_SINKS:
        enqueued.append(_enqueue(deed, line))
        return

    if kind == DeedRewardKind.IMMEDIATE and sink == DeedRewardSink.MONEY:
        try:
            sheet = line.recipient.sheet_data
        except Exception:  # noqa: BLE001 - sheet-less recipient: keep stub fallback
            sheet = None
        if sheet is not None:
            deliver_mission_money(recipient_sheet=sheet, amount=line.amount, ref=line.ref)
        else:
            money_stub.deliver_money(line)
        stub_calls.append(StubCallRecord(sink=sink, line_id=line.pk))
        return

    if kind == DeedRewardKind.PROPAGATION and sink == DeedRewardSink.RUMOR:
        rumor_stub.propagate_rumor(line)
        return  # rumor_stub always raises in 5b.1

    if kind == DeedRewardKind.PROPAGATION and sink == DeedRewardSink.CRIME_WATCH:
        crime_watch_stub.flag_crime(line)
        return  # crime_watch_stub always raises in 5b.1

    # Anything else is an author error — the (kind, sink) pair has no
    # routing target. Raise loudly so authoring tools can surface it.
    raise MissionRewardRoutingError(kind=kind, sink=sink, line_pk=line.pk)


def apply_deed_rewards(deed: MissionDeedRecord) -> ApplyDeedRewardsResult:
    """Route every emitted :class:`MissionDeedRewardLine` on ``deed`` downstream.

    Phase 5b.1's job: take the lines that
    :func:`emit_terminal_rewards` already persisted at the terminal route
    and dispatch each one to its target by ``(kind, sink)``.

      * ``(IMMEDIATE, MONEY)``   → records a call on
        :mod:`world.missions.integrations.money_stub` (no DB writes; the
        real ledger is Phase 6+).
      * ``(POST_CRON, LEGEND_POINTS)`` / ``(POST_CRON, RESONANCE)`` →
        idempotent ``update_or_create`` of a :class:`MissionRewardQueue`
        row keyed by ``line`` (the cron in Phase 5b.2 will flip
        ``applied`` once payout succeeds).
      * ``(PROPAGATION, RUMOR)`` / ``(PROPAGATION, CRIME_WATCH)`` →
        :class:`NotImplementedError` (DESIGN §13.3; whole apply rolls
        back).
      * ``(*, BEAT)`` → records a call on
        :mod:`world.missions.integrations.beat_stub`; Phase 5b.3 will
        replace the stub with real :class:`BeatCompletion` wiring.
      * Any other ``(kind, sink)`` combination →
        :class:`MissionRewardRoutingError` (author error; whole apply
        rolls back).

    The entire dispatch is wrapped in :func:`transaction.atomic`, so a
    stub-seal failure (rumor / crime-watch) or an unsupported combo aborts
    the whole apply — no partial queue rows persist. Stub-record sinks
    (money, beat) record their calls in-memory; those records are NOT
    rolled back by the transaction (they're program state, not DB state)
    but the queue rows ARE.

    **NOT auto-called by ``emit_terminal_rewards``.** Phase 5b.1 only
    introduces the routing seam; deciding when to apply (e.g. at engine
    terminal-deed time vs at a journal-flush boundary vs from the Phase-6
    chain-reactor) is left to whoever calls this function. In 5b.1 the
    only caller is the test suite.

    Args:
        deed: The deed whose ``reward_lines`` should be routed downstream.

    Returns:
        A typed :class:`ApplyDeedRewardsResult` carrying the queue rows
        upserted, the stub-call summary records, and a (currently always
        empty) errors list reserved for future aggregated-failure mode.

    Raises:
        NotImplementedError: A PROPAGATION/RUMOR or PROPAGATION/CRIME_WATCH
            line was present (rolls back the whole apply).
        MissionRewardRoutingError: An unsupported ``(kind, sink)`` combo
            was emitted (rolls back the whole apply).
    """
    lines = list(deed.reward_lines.all().order_by("pk"))

    enqueued: list[MissionRewardQueue] = []
    stub_calls: list[StubCallRecord] = []

    with transaction.atomic():
        for line in lines:
            _route_line(deed, line, enqueued, stub_calls)

    return ApplyDeedRewardsResult(
        enqueued=tuple(enqueued),
        stub_calls=tuple(stub_calls),
        errors=(),
    )


__all__ = (
    "MissionRewardRoutingError",
    "apply_deed_rewards",
    "emit_terminal_rewards",
)
