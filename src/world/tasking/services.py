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
    TargetConsentError,
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

# Points of resolution-check modifier per aptitude band (#2827 phase 4).
APTITUDE_STEP = 5
_APTITUDE_BAND_RANGE = (-1, 2)


def aptitude_band(persona, category: str) -> int:
    """The agent's band for a job family, minted lazily on first read."""
    import random  # noqa: PLC0415

    from world.tasking.models import NpcTaskAptitude  # noqa: PLC0415

    row = NpcTaskAptitude.objects.filter(persona=persona, category=category).first()
    if row is None:
        # S311/NOSONAR: game RNG for NPC flavor, not crypto.
        band = random.randint(*_APTITUDE_BAND_RANGE)  # noqa: S311 # NOSONAR
        row, _ = NpcTaskAptitude.objects.get_or_create(
            persona=persona, category=category, defaults={"band": band}
        )
    return row.band


def _pc_tenure_for_sheet(sheet_id):
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet_id=sheet_id,
        end_date__isnull=True,
    ).first()


def _consent_owner_tenures(target_persona, target_org, target_domain, target_crisis=None) -> list:
    """PC tenures whose espionage consent gates this target (#2833 addendum).

    Persona target: the persona's own player. Org/domain target: the target
    org's (or the domain's owner org's) PC leadership — an NPC-run org has
    no PC leadership tenures and is always-on."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if target_persona is not None:
        tenure = _pc_tenure_for_sheet(target_persona.character_sheet_id)
        return [tenure] if tenure else []
    org = target_org
    if org is None and target_domain is not None:
        org = target_domain.owner_org
    if org is None and target_crisis is not None:
        org = target_crisis.target_org
    if org is None:
        return []
    leaders = OrganizationMembership.objects.filter(
        organization=org,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__can_manage_ranks=True,
    ).select_related("persona")
    tenures = [_pc_tenure_for_sheet(m.persona.character_sheet_id) for m in leaders]
    return [t for t in tenures if t is not None]


def _assert_target_consent(  # noqa: PLR0913 - one kwarg per discriminator leg
    template, issuer, target_persona, *, target_org=None, target_domain=None, target_crisis=None
) -> None:
    """#2833: offensive jobs against a PC (or PC-led org/domain) route through
    the espionage consent category AT ISSUE TIME — the task refuses creation,
    so there is never an offscreen surprise. NPC targets and defensive jobs
    (quash/soothe-only templates) are ungated."""
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415
    from world.tasking.spy_payouts import template_is_offensive  # noqa: PLC0415

    if not template_is_offensive(template):
        return
    owner_tenures = _consent_owner_tenures(target_persona, target_org, target_domain, target_crisis)
    if not owner_tenures:
        return  # NPC target / NPC-led org: always-on
    issuer_tenure = _pc_tenure_for_sheet(issuer.character_sheet_id)
    category = SocialConsentCategory.objects.filter(key="espionage").first()
    for owner_tenure in owner_tenures:
        if consent_blocks_targeting(
            owner_tenure=owner_tenure, category=category, actor_tenure=issuer_tenure
        ):
            raise TargetConsentError


def _is_active_member(persona: Persona, org: Organization) -> bool:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        organization=org,
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).exists()


def create_task(  # noqa: PLR0913 - the five target kwargs are co-equal discriminator legs
    template: TaskTemplate,
    org: Organization,
    issued_by: Persona,
    *,
    target_room=None,
    target_org=None,
    target_domain=None,
    target_persona=None,
    target_crisis=None,
) -> OrgTask:
    """Create an OPEN task instance. Caller (view/action) gates leadership."""
    _assert_target_consent(
        template,
        issued_by,
        target_persona,
        target_org=target_org,
        target_domain=target_domain,
        target_crisis=target_crisis,
    )
    task = OrgTask(
        template=template,
        org=org,
        issued_by=issued_by,
        target_kind=template.target_kind,
        target_room=target_room,
        target_org=target_org,
        target_domain=target_domain,
        target_persona=target_persona,
        target_crisis=target_crisis,
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
    # Dispatchable agents: the handler's own, or the issuing org's roster
    # (#2820 phase 2 — org-held rows; membership is checked below either way).
    owns_personally = npc_asset.promoter_persona_id == handler.pk
    org_held_by_issuer = (
        npc_asset.promoter_org_id is not None and npc_asset.promoter_org_id == task.org_id
    )
    if not (owns_personally or org_held_by_issuer):
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


def _apply_route_payouts(
    route: TaskOutcomeRoute, task: OrgTask, fulfillment: TaskFulfillment
) -> list[str]:
    """Money/clue payouts land on the handler; spy payouts (#2833) apply per
    target kind. Returns extra report lines from the spy payouts."""
    from world.assets.services import draw_clue_from_pool  # noqa: PLC0415
    from world.clues.services import acquire_clue  # noqa: PLC0415
    from world.currency.services import deliver_mission_money  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.tasking.spy_payouts import apply_spy_payouts  # noqa: PLC0415

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
    return apply_spy_payouts(route, task, fulfillment)


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

    agent_persona = fulfillment.npc_asset.asset_persona
    agent_character = agent_persona.character_sheet.character
    check_result = perform_check(
        agent_character,
        task.template.check_type,
        task.template.check_difficulty,
        extra_modifiers=(
            fulfillment.handler_margin
            + APTITUDE_STEP * aptitude_band(agent_persona, task.template.category)
        ),
    )

    route = task.template.outcome_routes.filter(outcome_tier=check_result.outcome).first()
    spy_lines: list[str] = []
    if route is not None:
        spy_lines = _apply_route_payouts(route, task, fulfillment)
    _apply_risk_pool(task, fulfillment, agent_character, check_result)

    now = timezone.now()
    fulfillment.resolved_outcome = check_result.outcome
    fulfillment.report = "\n".join([_write_report(route, task, fulfillment), *spy_lines])
    fulfillment.resolved_at = now
    fulfillment.save(update_fields=["resolved_outcome", "report", "resolved_at"])

    task.status = TaskStatus.COMPLETED if check_result.success_level > 0 else TaskStatus.FAILED
    task.resolved_at = now
    task.save(update_fields=["status", "resolved_at"])
    return fulfillment


def resolve_due_tasks() -> int:
    """Game-clock sweep: resolve every ASSIGNED task whose deadline has passed.

    Also fails out tasks whose PC mission fulfillment was abandoned or
    expired (#2820 phase 5) — the mission walked away, so the job did too.
    """
    due = OrgTask.objects.filter(
        status=TaskStatus.ASSIGNED,
        deadline__lte=timezone.now(),
    )
    count = 0
    for task in due:
        resolve_task(task)
        count += 1
    count += _sweep_dead_pc_fulfillments()
    return count


def _sweep_dead_pc_fulfillments() -> int:
    from world.missions.constants import MissionStatus  # noqa: PLC0415

    dead = TaskFulfillment.objects.filter(
        is_active=True,
        task__status=TaskStatus.ASSIGNED,
        mission_instance__isnull=False,
        mission_instance__status__in=[MissionStatus.ABANDONED, MissionStatus.EXPIRED],
    ).select_related("task")
    count = 0
    now = timezone.now()
    for fulfillment in dead:
        task = fulfillment.task
        fulfillment.report = "The job was left unfinished."
        fulfillment.resolved_at = now
        fulfillment.save(update_fields=["report", "resolved_at"])
        task.status = TaskStatus.FAILED
        task.resolved_at = now
        task.save(update_fields=["status", "resolved_at"])
        count += 1
    return count


@transaction.atomic
def accept_task(task: OrgTask, handler: Persona) -> TaskFulfillment:
    """A member picks up a PC-fulfillable task as a mission (#2820 phase 5).

    Spawns a normal MissionInstance from the template's linked mission
    (`staff_assign_mission`, the same giver-less primitive board takes use);
    the run's terminal route grades into the task's own outcome-route table
    via `resolve_task_for_mission`.
    """
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

    if task.status != TaskStatus.OPEN:
        raise TaskNotOpenError
    if task.template.mission_template_id is None:
        raise TaskResolutionError
    if not _is_active_member(handler, task.org):
        raise HandlerNotMemberError

    character = handler.character_sheet.character
    instance = staff_assign_mission(
        task.template.mission_template,
        character,
        persona=handler,
    )
    fulfillment = TaskFulfillment(
        task=task,
        mission_instance=instance,
        handler=handler,
    )
    fulfillment.full_clean()
    fulfillment.save()
    task.status = TaskStatus.ASSIGNED
    task.save(update_fields=["status"])
    return fulfillment


def resolve_task_for_mission(instance, route=None) -> None:
    """Terminal-completion seam (#2820 phase 5) — mirrors the crisis seam.

    Called from missions' ``_finish_terminal``; a cheap no-op for every run
    that isn't fulfilling an OrgTask. The mission's terminal route tier
    lands on the SAME TaskOutcomeRoute table the NPC path uses — one
    authored payout surface, two execution engines. No risk pool here: the
    PC ran the job themselves; asset exposure is the NPC path's stake.
    """
    fulfillment = (
        TaskFulfillment.objects.filter(mission_instance=instance, is_active=True)
        .select_related("task")
        .first()
    )
    if fulfillment is None:
        return
    task = fulfillment.task
    if task.status != TaskStatus.ASSIGNED:
        return

    outcome_tier = route.outcome_tier if route is not None else None
    task_route = None
    spy_lines: list[str] = []
    if outcome_tier is not None:
        task_route = task.template.outcome_routes.filter(outcome_tier=outcome_tier).first()
    if task_route is not None:
        spy_lines = _apply_route_payouts(task_route, task, fulfillment)

    # A BRANCH terminal (route=None) or a success-tier route completes the
    # task; a failure-tier terminal fails it.
    succeeded = outcome_tier is None or outcome_tier.success_level > 0
    now = timezone.now()
    fulfillment.resolved_outcome = outcome_tier
    if task_route is not None and task_route.report_template:
        fulfillment.report = task_route.report_template.format(
            task=task.template.name,
            target=target_label(task),
            agent=str(fulfillment.handler),
        )
    else:
        fulfillment.report = f"{fulfillment.handler} saw to {task.template.name} personally."
    if spy_lines:
        fulfillment.report = "\n".join([fulfillment.report, *spy_lines])
    fulfillment.resolved_at = now
    fulfillment.save(update_fields=["resolved_outcome", "report", "resolved_at"])
    task.status = TaskStatus.COMPLETED if succeeded else TaskStatus.FAILED
    task.resolved_at = now
    task.save(update_fields=["status", "resolved_at"])
