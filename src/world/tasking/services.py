"""Tasking service functions (#2820 phase 1).

The NPC fulfillment path: an org leader issues an `OrgTask`, a handler
dispatches an owned `NPCAsset` (rolling the dispatch check immediately),
and the game clock resolves the job at deadline with the agent's own check.

Double-check semantics: the handler's dispatch check models briefing
quality — its success level shifts the agent's roll by
`DISPATCH_MARGIN_STEP` points per level, never replacing it. The agent's
resolution check is the tradecraft; its outcome tier selects the payout
route and grades the risk pool (ADR-0092).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.assets.constants import AssetStatus
from world.tasking.constants import DISPATCH_MARGIN_STEP, TaskStatus, TaskTargetKind
from world.tasking.exceptions import (
    AgentUnavailableError,
    ForeignAgentError,
    HandlerNotMemberError,
    NoActiveFulfillmentError,
    TaskNotOpenError,
    TaskResolutionError,
)
from world.tasking.models import OrgTask, TaskFulfillment

if TYPE_CHECKING:
    from world.assets.models import NPCAsset
    from world.checks.types import CheckResult
    from world.scenes.models import Persona
    from world.societies.models import Organization
    from world.tasking.models import TaskOutcomeRoute, TaskTemplate

_DEFAULT_REPORT = "{agent} reports back on {task}: nothing worth passing along."


def _is_active_member(persona: Persona, org: Organization) -> bool:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        organization=org,
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).exists()


def create_task(  # noqa: PLR0913 - the four target kwargs are co-equal discriminator legs
    template: TaskTemplate,
    org: Organization,
    issued_by: Persona,
    *,
    target_room=None,
    target_org=None,
    target_domain=None,
    target_persona=None,
) -> OrgTask:
    """Create an OPEN task instance. Caller (view/action) gates leadership."""
    task = OrgTask(
        template=template,
        org=org,
        issued_by=issued_by,
        target_kind=template.target_kind,
        target_room=target_room,
        target_org=target_org,
        target_domain=target_domain,
        target_persona=target_persona,
    )
    task.full_clean()
    task.save()
    return task


@transaction.atomic
def assign_agent(task: OrgTask, npc_asset: NPCAsset, handler: Persona) -> TaskFulfillment:
    """Dispatch an owned, active agent on an OPEN task.

    Rolls the handler's dispatch check now (with condition/equipment
    modifiers — the handler is a live PC) and stores its margin for the
    agent's resolution roll. Sets the deadline from the template duration.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415

    if task.status != TaskStatus.OPEN:
        raise TaskNotOpenError
    if npc_asset.status != AssetStatus.ACTIVE:
        raise AgentUnavailableError
    if npc_asset.promoter_persona_id != handler.pk:
        raise ForeignAgentError
    if not _is_active_member(handler, task.org):
        raise HandlerNotMemberError

    handler_character = handler.character_sheet.character
    dispatch_result = perform_check_with_modifiers(
        handler_character,
        task.template.check_type,
        target_difficulty=task.template.check_difficulty,
    )
    fulfillment = TaskFulfillment(
        task=task,
        npc_asset=npc_asset,
        handler=handler,
        handler_check_outcome=dispatch_result.outcome,
        handler_margin=dispatch_result.success_level * DISPATCH_MARGIN_STEP,
    )
    fulfillment.full_clean()
    fulfillment.save()

    task.status = TaskStatus.ASSIGNED
    task.deadline = timezone.now() + task.template.duration
    task.save(update_fields=["status", "deadline"])
    return fulfillment


def target_label(task: OrgTask) -> str:
    if task.target_kind == TaskTargetKind.NONE:
        return "the job"
    field = OrgTask.DISCRIMINATOR_MAP[TaskTargetKind(task.target_kind)]
    target = getattr(task, field)
    return str(target) if target is not None else "the job"


def _write_report(
    route: TaskOutcomeRoute | None,
    task: OrgTask,
    fulfillment: TaskFulfillment,
) -> str:
    agent_name = str(fulfillment.npc_asset.asset_persona)
    if route is None or not route.report_template:
        return _DEFAULT_REPORT.format(agent=agent_name, task=task.template.name)
    return route.report_template.format(
        task=task.template.name,
        target=target_label(task),
        agent=agent_name,
    )


def _apply_route_payouts(route: TaskOutcomeRoute, fulfillment: TaskFulfillment) -> None:
    """Money and clue payouts land on the handler (they collected the result)."""
    from world.assets.services import draw_clue_from_pool  # noqa: PLC0415
    from world.clues.services import acquire_clue  # noqa: PLC0415
    from world.currency.services import deliver_mission_money  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    handler_sheet = fulfillment.handler.character_sheet
    if route.money_reward > 0:
        deliver_mission_money(
            recipient_sheet=handler_sheet,
            amount=route.money_reward,
            ref=f"task:{fulfillment.task_id}",
            reason_label="task reward",
        )
    if route.clue_pool_id is not None:
        roster_entry = RosterEntry.objects.filter(character_sheet=handler_sheet).first()
        if roster_entry is not None:
            drawn = draw_clue_from_pool(route.clue_pool, roster_entry)
            if drawn is not None:
                acquire_clue(roster_entry, drawn)


def _apply_risk_pool(
    task: OrgTask,
    fulfillment: TaskFulfillment,
    agent_character,
    check_result: CheckResult,
) -> None:
    """Grade the template's consequence pool with the agent's roll (ADR-0092).

    The pool's ASSET_STATUS effects are the only path by which tasking ever
    compromises or loses an agent; the dispatched asset rides the context so
    the effect scopes to it alone.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        select_consequence_from_result,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    pool = task.template.consequence_pool
    if pool is None:
        return
    pending = select_consequence_from_result(
        agent_character,
        check_result,
        pool.cached_consequences,
    )
    apply_resolution(
        pending,
        ResolutionContext(character=agent_character, npc_asset=fulfillment.npc_asset),
    )


@transaction.atomic
def resolve_task(task: OrgTask) -> TaskFulfillment:
    """Resolve an ASSIGNED task now: agent check -> route payouts + risk pool."""
    from world.checks.services import perform_check  # noqa: PLC0415

    if task.status != TaskStatus.ASSIGNED:
        raise TaskResolutionError
    fulfillment = task.fulfillments.filter(is_active=True, npc_asset__isnull=False).first()
    if fulfillment is None:
        raise NoActiveFulfillmentError

    agent_character = fulfillment.npc_asset.asset_persona.character_sheet.character
    check_result = perform_check(
        agent_character,
        task.template.check_type,
        task.template.check_difficulty,
        extra_modifiers=fulfillment.handler_margin,
    )

    route = task.template.outcome_routes.filter(outcome_tier=check_result.outcome).first()
    if route is not None:
        _apply_route_payouts(route, fulfillment)
    _apply_risk_pool(task, fulfillment, agent_character, check_result)

    now = timezone.now()
    fulfillment.resolved_outcome = check_result.outcome
    fulfillment.report = _write_report(route, task, fulfillment)
    fulfillment.resolved_at = now
    fulfillment.save(update_fields=["resolved_outcome", "report", "resolved_at"])

    task.status = TaskStatus.COMPLETED if check_result.success_level > 0 else TaskStatus.FAILED
    task.resolved_at = now
    task.save(update_fields=["status", "resolved_at"])
    return fulfillment


def resolve_due_tasks() -> int:
    """Game-clock sweep: resolve every ASSIGNED task whose deadline has passed."""
    due = OrgTask.objects.filter(
        status=TaskStatus.ASSIGNED,
        deadline__lte=timezone.now(),
    )
    count = 0
    for task in due:
        resolve_task(task)
        count += 1
    return count
