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

import logging
from typing import TYPE_CHECKING

from django.db import transaction

from world.currency.services import deliver_mission_money
from world.missions.constants import DeedRewardKind, DeedRewardSink, RewardGroupRule
from world.missions.integrations import beat_stub, crime_watch, money_stub, rumor_stub
from world.missions.models import MissionDeedRewardLine, MissionRewardQueue
from world.missions.types import ApplyDeedRewardsResult, StubCallRecord

logger = logging.getLogger("world.missions.rewards")

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import (
        MissionDeedRecord,
        MissionInstance,
        MissionOptionRoute,
        MissionOptionRouteCandidate,
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
        resonance=template.resonance,
        item_template=template.item_template,
        followon_offer=template.followon_offer,
        followon_message=template.followon_message,
        followon_expiry_hours=template.followon_expiry_hours,
        ref=template.ref,
    )


def emit_terminal_rewards(
    instance: MissionInstance,
    route: MissionOptionRoute,
    deed: MissionDeedRecord,
) -> list[MissionDeedRewardLine]:
    """Emit one :class:`MissionDeedRewardLine` per (template × recipient).

    Called by the resolution engine after a terminal :class:`MissionDeedRecord`
    has been created (``next_node is None``). Walks the terminal route's
    ``reward_templates`` (a fired random-set candidate's own rewards fire
    separately, on selection — see :func:`emit_candidate_rewards`). Each
    template distributes per its ``contract_holder_only`` toggle and the
    instance's ``template.reward_group_rule``:

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
    return _distribute_reward_templates(instance, list(route.reward_templates.all()), deed)


def emit_candidate_rewards(
    instance: MissionInstance,
    candidate: MissionOptionRouteCandidate,
    deed: MissionDeedRecord,
) -> list[MissionDeedRewardLine]:
    """Emit a fired random-set candidate's own reward bundle (#941).

    Unlike route rewards (terminal-gated), a candidate's reward lines fire when
    the candidate is chosen — a candidate always advances (its ``target_node``
    is required), so it is never the terminal route. Same per-template
    distribution as :func:`emit_terminal_rewards`. No-op when the candidate
    carries no reward templates.
    """
    return _distribute_reward_templates(instance, list(candidate.reward_templates.all()), deed)


def _distribute_reward_templates(
    instance: MissionInstance,
    templates: list[MissionOptionRouteReward],
    deed: MissionDeedRecord,
) -> list[MissionDeedRewardLine]:
    """Turn authored reward templates into persisted lines (shared core).

    Distribution: ``contract_holder_only`` rows → one line to the holder;
    broadcast rows → per ``instance.template.reward_group_rule`` (ALL_EQUAL
    implemented; BY_ROLE / BY_PARTICIPATION stub-sealed). All rows are built
    before any write so a stub-sealed rule aborts cleanly (no partial writes).
    """
    if not templates:
        return []

    participants = _ordered_participants(instance)
    rule = instance.template.reward_group_rule

    rows: list[MissionDeedRewardLine] = []
    holder: MissionParticipant | None = None
    for template in templates:
        if template.contract_holder_only:
            if holder is None:
                holder = _contract_holder(participants)
            rows.append(_line_for(deed, template, holder))
            continue
        if rule == RewardGroupRule.ALL_EQUAL:
            rows.extend(_line_for(deed, template, p) for p in participants)
        else:
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
# PROPAGATION sinks whose real routing isn't built yet (CRIME_WATCH went live with #1765).
_UNBUILT_PROPAGATION_SINKS = frozenset({DeedRewardSink.RUMOR})


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


def _route_crime_watch(
    line: MissionDeedRewardLine, *, room: ObjectDB | None, skip_criminal: bool
) -> None:
    """The live CRIME_WATCH branch (#1765): mint at ``room`` unless dodged/context-less."""
    if skip_criminal:
        logger.info(
            "apply_deed_rewards: consequence dodged — skipping CRIME_WATCH line pk=%d (#1765)",
            line.pk,
        )
        return
    if room is None:
        logger.info(
            "apply_deed_rewards: no room context — skipping CRIME_WATCH line pk=%d (#1765)",
            line.pk,
        )
        return
    crime_watch.flag_crime(line, room=room)


def _deliver_immediate_money(line: MissionDeedRewardLine) -> None:
    """Deliver an IMMEDIATE MONEY line, falling back to the stub when sheet-less."""
    try:
        sheet = line.recipient.sheet_data
    except Exception:  # noqa: BLE001 - sheet-less recipient: keep stub fallback
        sheet = None
    if sheet is not None:
        deliver_mission_money(recipient_sheet=sheet, amount=line.amount, ref=line.ref)
    else:
        money_stub.deliver_money(line)


def _route_unbuilt_propagation(
    line: MissionDeedRewardLine, *, sink: str, skip_unbuilt: bool
) -> None:
    """Route a not-yet-built PROPAGATION sink (RUMOR).

    When ``skip_unbuilt`` is True the line is logged and skipped; otherwise the
    rumor stub is invoked (always raises in 5b.1, rolling back the apply).
    """
    if skip_unbuilt:
        logger.info(
            "apply_deed_rewards: skipping not-yet-built %s line pk=%d (#1765)", sink, line.pk
        )
        return
    rumor_stub.propagate_rumor(line)  # always raises in 5b.1


def _route_line(  # noqa: PLR0913, PLR0911 — one early-return branch per (kind, sink) pair
    deed: MissionDeedRecord,
    line: MissionDeedRewardLine,
    enqueued: list[MissionRewardQueue],
    stub_calls: list[StubCallRecord],
    *,
    skip_unbuilt: bool = False,
    room: ObjectDB | None = None,
    skip_criminal: bool = False,
) -> None:
    """Dispatch one emitted line by its ``(kind, sink)`` pair.

    Mutates ``enqueued``/``stub_calls`` in place so the caller can aggregate
    across all lines without rebuilding tuples per row. The PROPAGATION
    stubs raise ``NotImplementedError`` (rolls back the whole apply); the
    unsupported-combo case raises :class:`MissionRewardRoutingError` (also
    rolls back). Stub-record sinks (money, beat) never raise.

    When ``skip_unbuilt`` is True, the not-yet-built PROPAGATION sinks
    (RUMOR / CRIME_WATCH — the criminal-consequence layer, #1765) are
    logged and skipped instead of raising, so wiring the payout into
    mission-reporting (#1753) can pay the money/beat/queue lines without a
    criminal line crashing the whole report.
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
        _deliver_immediate_money(line)
        stub_calls.append(StubCallRecord(sink=sink, line_id=line.pk))
        return

    if kind == DeedRewardKind.IMMEDIATE and sink == DeedRewardSink.ITEM:
        from world.items.services.narrative_grants import (  # noqa: PLC0415
            grant_touchstone_item_to_character,
        )

        recipient_sheet = line.recipient.sheet_data
        grant_touchstone_item_to_character(
            character_sheet=recipient_sheet, template=line.item_template
        )
        return

    # CRIME_WATCH is live (#1765): mints heat + the society sting at the report
    # location. Skipped when the reporter dodged (mostly-accurate success) or
    # when no room context reached us (non-report callers have no "where").
    if kind == DeedRewardKind.PROPAGATION and sink == DeedRewardSink.CRIME_WATCH:
        _route_crime_watch(line, room=room, skip_criminal=skip_criminal)
        return

    # The not-yet-built RUMOR sink — skipped-and-logged when a caller opts
    # out, else the stub raises (rolls back).
    if kind == DeedRewardKind.PROPAGATION and sink in _UNBUILT_PROPAGATION_SINKS:
        _route_unbuilt_propagation(line, sink=sink, skip_unbuilt=skip_unbuilt)
        return

    if kind == DeedRewardKind.IMMEDIATE and sink == DeedRewardSink.FOLLOW_ON_SUMMONS:
        _route_follow_on_summons(line)
        return

    # Anything else is an author error — the (kind, sink) pair has no
    # routing target. Raise loudly so authoring tools can surface it.
    raise MissionRewardRoutingError(kind=kind, sink=sink, line_pk=line.pk)


def _route_follow_on_summons(line: MissionDeedRewardLine) -> None:
    """Fire a directed-offer summons for a FOLLOW_ON_SUMMONS reward line.

    The automated path: created_by=None (no GM). The summons targets the
    persona the contract holder presented when accepting the mission —
    ``line.deed.instance.accepted_as_persona``. PENDING-uniqueness is
    inherited from OfferSummons — a duplicate PENDING raises
    IntegrityError, which we catch and log as a no-op.
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: PLC0415
    from django.db import IntegrityError, transaction  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.npc_services.constants import SummonsStatus  # noqa: PLC0415
    from world.npc_services.models import OfferSummons  # noqa: PLC0415
    from world.npc_services.summons import create_summons  # noqa: PLC0415

    persona = line.deed.instance.accepted_as_persona
    if persona is None:
        logger.warning(
            "apply_deed_rewards: FOLLOW_ON_SUMMONS line pk=%d has no "
            "accepted_as_persona on its instance — skipping (no target).",
            line.pk,
        )
        return

    # PENDING-uniqueness dedup: if a PENDING summons already exists for this
    # (offer, persona), skip silently — the offer is already pending. This
    # avoids the ValidationError/IntegrityError path entirely and lets
    # create_summons' MISSION-kind gate surface loudly for real authoring errors.
    already_pending = OfferSummons.objects.filter(
        offer=line.followon_offer,
        target_persona=persona,
        status=SummonsStatus.PENDING,
    ).exists()
    if already_pending:
        logger.info(
            "apply_deed_rewards: follow-on summons already PENDING for "
            "offer pk=%d, persona pk=%d — skipping (dedup).",
            line.followon_offer_id,
            persona.pk,
        )
        return

    expires_at = None
    if line.followon_expiry_hours is not None:
        expires_at = timezone.now() + timedelta(hours=line.followon_expiry_hours)

    # Wrap in a savepoint so a race-condition IntegrityError (another process
    # created the PENDING summons between our check and create_summons' save)
    # doesn't poison the outer apply_deed_rewards transaction.
    sid = transaction.savepoint()
    try:
        create_summons(
            offer=line.followon_offer,
            target_persona=persona,
            message=line.followon_message,
            expires_at=expires_at,
            created_by=None,
        )
    except (IntegrityError, DjangoValidationError):
        transaction.savepoint_rollback(sid)
        logger.info(
            "apply_deed_rewards: follow-on summons race-lost PENDING for "
            "offer pk=%d, persona pk=%d — skipping (dedup).",
            line.followon_offer_id,
            persona.pk,
        )


def apply_deed_rewards(
    deed: MissionDeedRecord,
    *,
    skip_unbuilt: bool = False,
    room: ObjectDB | None = None,
    skip_criminal: bool = False,
) -> ApplyDeedRewardsResult:
    """Route every emitted :class:`MissionDeedRewardLine` on ``deed`` downstream.

    Phase 5b.1's job: take the lines that
    :func:`emit_terminal_rewards` already persisted at the terminal route
    and dispatch each one to its target by ``(kind, sink)``.

      * ``(IMMEDIATE, MONEY)``   → real payout via
        :func:`world.currency.services.deliver_mission_money` into the
        recipient's ``CharacterPurse`` (falls back to the money_stub only for
        a sheet-less recipient).
      * ``(IMMEDIATE, ITEM)`` → real payout via
        :func:`world.items.services.narrative_grants.grant_touchstone_item_to_character`:
        mints an ``ItemInstance`` of ``line.item_template`` held by the
        recipient's ``CharacterSheet`` — the touchstone/reagent narrative
        grant path (#707).
      * ``(POST_CRON, LEGEND_POINTS)`` / ``(POST_CRON, RESONANCE)`` →
        idempotent ``update_or_create`` of a :class:`MissionRewardQueue`
        row keyed by ``line`` (the cron in Phase 5b.2 will flip
        ``applied`` once payout succeeds).
      * ``(PROPAGATION, CRIME_WATCH)`` → real criminal consequences via
        :func:`world.missions.integrations.crime_watch.flag_crime` (#1765):
        pursuit heat + the society sting at ``room``. Skipped when
        ``skip_criminal`` (a successful mostly-accurate dodge) or when no
        ``room`` context was supplied.
      * ``(PROPAGATION, RUMOR)`` → :class:`NotImplementedError` (DESIGN
        §13.3; whole apply rolls back).
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
    chain-reactor) is left to whoever calls this function. The production
    caller is mission reporting's ``_apply_style_payout``
    (world.missions.services.report, #1769).

    Args:
        deed: The deed whose ``reward_lines`` should be routed downstream.

    Returns:
        A typed :class:`ApplyDeedRewardsResult` carrying the queue rows
        upserted, the stub-call summary records, and a (currently always
        empty) errors list reserved for future aggregated-failure mode.

    Raises:
        NotImplementedError: A PROPAGATION/RUMOR line was present (rolls
            back the whole apply).
        MissionRewardRoutingError: An unsupported ``(kind, sink)`` combo
            was emitted (rolls back the whole apply).
    """
    lines = list(deed.reward_lines.all().order_by("pk"))

    enqueued: list[MissionRewardQueue] = []
    stub_calls: list[StubCallRecord] = []

    with transaction.atomic():
        for line in lines:
            _route_line(
                deed,
                line,
                enqueued,
                stub_calls,
                skip_unbuilt=skip_unbuilt,
                room=room,
                skip_criminal=skip_criminal,
            )

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
