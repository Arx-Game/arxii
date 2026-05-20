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

from world.missions.constants import RewardGroupRule
from world.missions.models import MissionDeedRewardLine

if TYPE_CHECKING:
    from world.missions.models import (
        MissionDeedRecord,
        MissionInstance,
        MissionOptionRoute,
        MissionOptionRouteReward,
        MissionParticipant,
    )

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
