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
_COIN_BAND_THIN_MAX = 10_000
_COIN_BAND_COMFORTABLE_MAX = 100_000


def apply_spy_payouts(
    route: TaskOutcomeRoute, task: OrgTask, fulfillment: TaskFulfillment
) -> list[str]:
    """Apply every spy payout the route carries; returns report lines.

    Residue stays last: it mints the secret AFTER the job's own effects land.
    """
    payouts = [
        (route.movements_report, lambda: _movements_report(task)),
        (route.unmask_target, lambda: _unmask(task, fulfillment)),
        (route.gossip_heat_delta, lambda: _gossip_heat(task, route.gossip_heat_delta)),
        (
            route.building_condition_delta,
            lambda: _building_condition(task, route.building_condition_delta),
        ),
        (route.recruit_target, lambda: _recruit(task)),
        (route.domain_report, lambda: _domain_report(task)),
        (route.domain_unrest_delta, lambda: _domain_unrest(task, route.domain_unrest_delta)),
        (route.organization_report, lambda: _organization_report(task)),
        (route.military_report, lambda: _military_report(task)),
        (
            route.incriminate_level,
            lambda: _incriminate(task, fulfillment, route.incriminate_level),
        ),
    ]
    lines: list[str] = []
    for enabled, payout in payouts:
        if enabled:
            lines.extend(payout())
    return lines


def _domain_report(task: OrgTask) -> list[str]:
    """What a rival spymaster wants to know about a domain — all of it
    mechanical state the domain machinery already tracks."""
    from world.societies.houses.models import DomainCrisis, DomainHolding  # noqa: PLC0415

    domain = task.target_domain
    if domain is None:
        return ["The survey found no domain to walk."]
    holdings = ", ".join(
        DomainHolding.objects.filter(domain=domain)
        .select_related("kind")
        .values_list("kind__name", flat=True)[:8]
    )
    crises = DomainCrisis.objects.filter(domain=domain, resolved_at__isnull=True).count()
    lines = [
        (
            f"{domain.name}: some {domain.population} souls; prosperity "
            f"{domain.prosperity}/100, unrest {domain.unrest}/100."
        )
    ]
    if holdings:
        lines.append(f"Holdings observed: {holdings}.")
    if crises:
        lines.append(f"The domain nurses {crises} open crisis(es).")
    return lines


def _domain_unrest(task: OrgTask, delta: int) -> list[str]:
    """Foment or soothe unrest — plugs straight into the weekly domain tick
    and crisis machinery (agitation today is a crisis next cycle)."""
    domain = task.target_domain
    if domain is None:
        return ["No populace to stir."]
    new_value = max(0, min(100, domain.unrest + delta))
    if new_value == domain.unrest:
        return ["The mood there resists any further push."]
    domain.unrest = new_value
    domain.save(update_fields=["unrest"])
    if delta > 0:
        return [f"Discontent takes root in {domain.name}."]
    return [f"Tempers cool in {domain.name}."]


def _organization_report(task: OrgTask) -> list[str]:
    """Case a rival organization: counts and bands, never exact coin."""
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.currency.models import OrganizationTreasury  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    org = task.target_org
    if org is None:
        return ["No organization to case."]
    members = OrganizationMembership.objects.filter(
        organization=org, left_at__isnull=True, exiled_at__isnull=True
    ).count()
    agents = NPCAsset.objects.filter(promoter_org=org, status=AssetStatus.ACTIVE).count()
    treasury = OrganizationTreasury.objects.filter(organization=org).first()
    band = _coin_band(treasury.balance if treasury else 0)
    lines = [f"{org.name}: {members} sworn member(s); coffers run {band}."]
    if agents:
        lines.append(f"They keep perhaps {agents} agent(s) of their own.")
    if org.parent_org_id is not None:
        lines.append(f"They answer upward to {org.parent_org.name}.")
    wings = org.child_orgs.count()
    if wings:
        lines.append(f"They operate {wings} wing(s) of their own.")
    return lines


_BAND_EMPTY = "empty"
_BAND_THIN = "thin"
_BAND_COMFORTABLE = "comfortable"
_BAND_DEEP = "deep"


def _coin_band(balance: int) -> str:
    """PLACEHOLDER banding — a spy estimates, never audits."""
    if balance <= 0:
        return _BAND_EMPTY
    if balance < _COIN_BAND_THIN_MAX:
        return _BAND_THIN
    if balance < _COIN_BAND_COMFORTABLE_MAX:
        return _BAND_COMFORTABLE
    return _BAND_DEEP


def _military_report(task: OrgTask) -> list[str]:
    """Assay a rival's strength — persistent units and active armies.

    Troop MOVEMENTS wait on positional military state; strength counts are
    what exists to spy on today (#2833 addendum).
    """
    from world.military.models import Army, MilitaryUnit  # noqa: PLC0415

    org = task.target_org
    if org is None:
        return ["No banners to count."]
    units = MilitaryUnit.objects.filter(owner_org=org)
    unit_count = units.count()
    if unit_count == 0:
        return [f"{org.name} fields no soldiery worth the name."]
    army_count = (
        Army.objects.filter(units__owner_org=org, disbanded_at__isnull=True).distinct().count()
    )
    sample = ", ".join(units.values_list("name", flat=True)[:5])
    lines = [f"{org.name} fields {unit_count} unit(s): {sample}."]
    if army_count:
        lines.append(f"{army_count} armied formation(s) stand active.")
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
    """Whether any route works AGAINST its target (#2833 consent gate).

    Quashing gossip and soothing unrest (negative deltas) are defensive;
    reports, recruitment, agitation, and amplification are offense.
    Residue hits the handler, not the mark.
    """
    for route in template.outcome_routes.all():
        if template.target_kind == TaskTargetKind.PERSONA and (
            route.movements_report
            or route.unmask_target
            or route.recruit_target
            or route.gossip_heat_delta > 0
        ):
            return True
        if template.target_kind == TaskTargetKind.DOMAIN and (
            route.domain_report or route.domain_unrest_delta > 0
        ):
            return True
        if template.target_kind == TaskTargetKind.ORG and (
            route.organization_report or route.military_report
        ):
            return True
    return False
