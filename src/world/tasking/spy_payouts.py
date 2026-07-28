"""Spy Job Kit payout applications (#2833).

Each payout applies only when the task's target kind matches; mismatched or
empty targets produce a report line, never an exception — an authored route
can carry several payouts and each degrades independently. All functions
return report lines for the handler's eyes.

The residue rule (`incriminate_level`) is the kit's teeth-against-you: dirty
work mints a GM-provenance Secret about the HANDLER plus an investigable hub
trail — operations create the secrets the next investigator digs up.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from world.tasking.constants import TaskTargetKind

if TYPE_CHECKING:
    from world.tasking.models import OrgTask, TaskFulfillment, TaskOutcomeRoute

# PLACEHOLDER calibration (#2833).
MOVEMENTS_REPORT_DAYS = 14
RESIDUE_TRAIL_DIFFICULTY = 25
_CONDITION_TIER_MIN = 0
_CONDITION_TIER_MAX = 5


def apply_spy_payouts(
    route: TaskOutcomeRoute, task: OrgTask, fulfillment: TaskFulfillment
) -> list[str]:
    """Apply every spy payout the route carries; returns report lines."""
    lines: list[str] = []
    if route.movements_report:
        lines.extend(_movements_report(task))
    if route.unmask_target:
        lines.extend(_unmask(task, fulfillment))
    if route.gossip_heat_delta:
        lines.extend(_gossip_heat(task, route.gossip_heat_delta))
    if route.building_condition_delta:
        lines.extend(_building_condition(task, route.building_condition_delta))
    if route.recruit_target:
        lines.extend(_recruit(task))
    if route.incriminate_level:
        lines.extend(_incriminate(task, fulfillment, route.incriminate_level))
    return lines


def _movements_report(task: OrgTask) -> list[str]:
    """Where the mark has been seen — PUBLIC rooms only, mechanical residue
    (scene interaction records), never prose. ADR-0175 holds."""
    from world.scenes.models import Interaction  # noqa: PLC0415

    target = task.target_persona
    if target is None:
        return ["The tail had no one to follow."]
    since = timezone.now() - timedelta(days=MOVEMENTS_REPORT_DAYS)
    rows = (
        Interaction.objects.filter(
            persona=target,
            timestamp__gte=since,
            scene__location__room_profile__is_public=True,
        )
        .select_related("scene__location")
        .order_by("-timestamp")
        .values_list("scene__location__db_key", "timestamp")
    )
    seen: dict[str, str] = {}
    for room_name, when in rows:
        seen.setdefault(room_name or "somewhere", when.strftime("%Y-%m-%d"))
    if not seen:
        return [f"{target.name} has kept out of public view of late."]
    trail = "; ".join(f"{room} ({date})" for room, date in list(seen.items())[:8])
    return [f"{target.name} has been seen at: {trail}."]


def _unmask(task: OrgTask, fulfillment: TaskFulfillment) -> list[str]:
    """Pierce the mark's mask: mint a PERSONA_LINK clue to the handler."""
    from world.clues.constants import ClueResolution, ClueTargetKind  # noqa: PLC0415
    from world.clues.models import Clue  # noqa: PLC0415
    from world.clues.services import acquire_clue, grant_clue_target  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.constants import PersonaType  # noqa: PLC0415

    target = task.target_persona
    if target is None:
        return ["No one to unmask."]
    if target.persona_type == PersonaType.PRIMARY:
        return [f"{target.name} appears to be exactly who they claim."]
    true_face = target.character_sheet.personas.filter(persona_type=PersonaType.PRIMARY).first()
    if true_face is None:
        return [f"{target.name}'s trail goes nowhere."]

    clue, _ = Clue.objects.get_or_create(
        target_kind=ClueTargetKind.PERSONA_LINK,
        target_persona=target,
        target_persona_linked=true_face,
        defaults={
            "name": "The Face Beneath",
            "description": (
                "PLACEHOLDER Threads pulled from a dozen small slips, and the "
                "mask comes away in your hands."
            ),
            "resolution_mode": ClueResolution.AUTOMATIC,
        },
    )
    entry = RosterEntry.objects.filter(character_sheet=fulfillment.handler.character_sheet).first()
    if entry is not None:
        acquire_clue(entry, clue)
        grant_clue_target(clue, entry)
    return [f"The mask slips: you now know who {target.name} really is."]


def _gossip_heat(task: OrgTask, delta: int) -> list[str]:
    """Spread or suppress REAL dirt — the hottest gossip about the mark.

    Never mints secrets: whisper campaigns amplify what exists (or what the
    org planted through other play); quashing cools it.
    """
    from world.secrets.gossip import _maybe_go_public  # noqa: PLC0415
    from world.secrets.models import SecretGossip  # noqa: PLC0415

    target = task.target_persona
    if target is None:
        return ["No one to whisper about."]
    row = (
        SecretGossip.objects.filter(secret__subject_sheet=target.character_sheet)
        .order_by("-heat")
        .first()
    )
    if row is None:
        return [f"There is nothing whispered about {target.name} to work with."]
    row.heat = max(0, row.heat + delta)
    row.save(update_fields=["heat"])
    if delta > 0:
        _maybe_go_public(row)
        return [f"The whispers about {target.name} grow louder."]
    return [f"The whispers about {target.name} die down."]


def _building_condition(task: OrgTask, delta: int) -> list[str]:
    """Sabotage (or discreetly repair) the target room's building."""
    from world.buildings.models import Building  # noqa: PLC0415
    from world.buildings.upkeep_services import set_condition_tier  # noqa: PLC0415

    room = task.target_room
    if room is None or room.area_id is None:
        return ["The job found no works to touch."]
    building = Building.objects.filter(area_id=room.area_id).first()
    if building is None:
        return ["The job found no works to touch."]
    new_tier = max(_CONDITION_TIER_MIN, min(_CONDITION_TIER_MAX, building.condition_tier + delta))
    if new_tier == building.condition_tier:
        return ["The works were already past helping (or harming)."]
    set_condition_tier(building, new_tier)
    verb = "quietly wrecked" if delta < 0 else "discreetly shored up"
    return [f"The works were {verb}."]


def _recruit(task: OrgTask) -> list[str]:
    """Remote cultivation: the org gains a held claim on a target NPC."""
    from world.assets.constants import (  # noqa: PLC0415
        AssetAcquisitionSource,
        AssetRoleContext,
        AssetStatus,
    )
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.roster.models import RosterTenure  # noqa: PLC0415

    target = task.target_persona
    if target is None:
        return ["No one to suborn."]
    is_pc = RosterTenure.objects.filter(
        roster_entry__character_sheet_id=target.character_sheet_id
    ).exists()
    if is_pc:
        return [f"{target.name} is no mere servant — this needs a personal touch."]
    _, created = NPCAsset.objects.get_or_create(
        promoter_org=task.org,
        asset_persona=target,
        status=AssetStatus.ACTIVE,
        defaults={
            "role_context": AssetRoleContext.INFORMANT,
            "acquisition_source": AssetAcquisitionSource.CHARM,
        },
    )
    if not created:
        return [f"{target.name} already answers to the organization."]
    return [f"{target.name} now quietly answers to the organization."]


def _incriminate(task: OrgTask, fulfillment: TaskFulfillment, level: int) -> list[str]:
    """The residue rule: the job leaves a secret about the handler behind."""
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.services import get_ancestor_at_level  # noqa: PLC0415
    from world.clues.services import create_accusation_counter_clue  # noqa: PLC0415
    from world.secrets.constants import SecretProvenance  # noqa: PLC0415
    from world.secrets.services import author_secret  # noqa: PLC0415
    from world.tasking.services import target_label  # noqa: PLC0415

    handler = fulfillment.handler
    secret = author_secret(
        subject_sheet=handler.character_sheet,
        provenance=SecretProvenance.GM_AUTHORED,
        level=min(4, max(1, level)),
        content=(
            f"PLACEHOLDER {handler.name} arranged {task.template.name} "
            f"against {target_label(task)}."
        ),
        consequences=(
            "PLACEHOLDER The work was done — but done sloppily enough that a "
            "patient investigator could pull the thread back to its buyer."
        ),
    )
    # Hub trail: the counter-clue placement pattern, generalized — an
    # investigable RESEARCH clue seeded in the region's social hubs. Skipped
    # when no region is derivable (persona-target jobs with no room anchor).
    if task.target_room is not None and task.target_room.area_id is not None:
        region = get_ancestor_at_level(task.target_room.area, AreaLevel.REGION)
        if region is not None:
            create_accusation_counter_clue(
                secret, region=region, difficulty=RESIDUE_TRAIL_DIFFICULTY
            )
    return []  # residue is never reported to the handler — that's the point


def template_is_offensive(template) -> bool:
    """Whether any route works AGAINST a persona target (#2833 consent gate).

    Quashing gossip (negative heat only) is defensive; everything else
    aimed at a persona is offense. Residue hits the handler, not the mark.
    """
    if template.target_kind != TaskTargetKind.PERSONA:
        return False
    for route in template.outcome_routes.all():
        if route.movements_report or route.unmask_target or route.recruit_target:
            return True
        if route.gossip_heat_delta > 0:
            return True
    return False
