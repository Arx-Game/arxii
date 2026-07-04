"""Court grant negotiation: ceiling computation + monotonic raise (#1718).

Two channels read this ceiling: the formal petition (OfferKind.COURT_GRANT,
world/npc_services/effects.py) and the emergency thread-bond draw
(world/combat/pull_helpers.py). Both convert already-earned trust
(NPCStanding.affection with the master + completed Court missions) into a
ceiling on CourtPact.granted_pull_cap; raise_court_pact_grant enforces that the
grant can only ever go up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.covenants.exceptions import CourtGrantNotMonotonicError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CourtPact, Covenant
    from world.npc_services.models import NPCRole, NPCStanding


def completed_court_mission_count(
    *,
    character_sheet: CharacterSheet,
    covenant: Covenant,
) -> int:
    """Count of this servant's COMPLETE MissionInstance rows for covenant's org.

    Mirrors has_active_court_mission's org-match (world/covenants/court_missions.py)
    but counts COMPLETE instead of filtering ACTIVE. Lazy-imports world.missions to
    avoid a covenants -> missions import cycle (same reason has_active_court_mission
    lazy-imports it).
    """
    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInstance  # noqa: PLC0415

    return MissionInstance.objects.filter(
        participants__character=character_sheet.character,
        status=MissionStatus.COMPLETE,
        source_offer__role__faction_affiliation_id=covenant.organization_id,
    ).count()


def _master_standing(*, covenant: Covenant, servant_sheet: CharacterSheet) -> NPCStanding | None:
    """Return the (servant -> master) NPCStanding row, or None if never created."""
    from world.npc_services.models import NPCStanding  # noqa: PLC0415

    if covenant.leader_id is None:
        return None
    master_persona = covenant.leader.primary_persona
    servant_persona = servant_sheet.primary_persona
    return NPCStanding.objects.filter(
        persona=servant_persona,
        npc_persona=master_persona,
    ).first()


def court_grant_ceiling(*, covenant: Covenant, servant_sheet: CharacterSheet) -> int:
    """Max grant the master is currently willing to formalize for this servant.

    ceiling = base_headroom + (affection // affection_divisor)
            + (completed_court_mission_count // mission_divisor)
            - outstanding_debt(...)
    floored at 0. Reads the master's NPCStanding.affection toward the servant
    (0 if no row exists yet — a brand-new servant has earned nothing).
    """
    from world.covenants.services import get_court_grant_config  # noqa: PLC0415
    from world.npc_services.services import outstanding_debt  # noqa: PLC0415

    config = get_court_grant_config()
    standing = _master_standing(covenant=covenant, servant_sheet=servant_sheet)
    affection = standing.affection if standing is not None else 0
    missions = completed_court_mission_count(character_sheet=servant_sheet, covenant=covenant)

    ceiling = (
        config.base_headroom
        + affection // config.affection_divisor
        + missions // config.mission_divisor
    )
    if standing is not None:
        debt = outstanding_debt(
            standing,
            current_affection=affection,
            current_missions_completed=missions,
            affection_divisor=config.debt_repay_affection_divisor,
            mission_divisor=config.debt_repay_mission_divisor,
        )
        ceiling -= debt
    return max(0, ceiling)


def raise_court_pact_grant(*, pact: CourtPact, new_cap: int) -> CourtPact:
    """Raise pact.granted_pull_cap to new_cap. Never lowers it (#1718).

    Raises CourtGrantNotMonotonicError if new_cap < pact.granted_pull_cap.
    A new_cap equal to the current cap is a harmless no-op (not an error) —
    only an actual decrease is rejected.
    """
    if new_cap < pact.granted_pull_cap:
        raise CourtGrantNotMonotonicError
    if new_cap == pact.granted_pull_cap:
        return pact
    pact.granted_pull_cap = new_cap
    pact.save(update_fields=["granted_pull_cap"])
    return pact


def ensure_court_grant_role(covenant: Covenant) -> NPCRole:
    """Get-or-create the NPCRole carrying covenant's COURT_GRANT petition offer.

    Idempotent — safe to call on every negotiation attempt. Auto-provisions the
    role + its single petition offer + details row the first time any servant
    of this Court tries to negotiate; staff never need to hand-author this per
    master (#1718 design question 4 — NPC-master automation).
    """
    from world.covenants.factories import wire_court_grant_petition_content  # noqa: PLC0415
    from world.covenants.services import get_court_grant_config  # noqa: PLC0415
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        CourtGrantOfferDetails,
        NPCRole,
        NPCServiceOffer,
    )

    if covenant.court_grant_role_id is not None:
        return covenant.court_grant_role

    check_type = wire_court_grant_petition_content()
    config = get_court_grant_config()

    role = NPCRole.objects.create(
        name=f"{covenant.name} — Court Master's Grant",
        faction_affiliation=covenant.organization,
    )
    offer = NPCServiceOffer.objects.create(
        role=role,
        kind=OfferKind.COURT_GRANT,
        label="Petition for greater strength",
        is_final=True,
        check_type=check_type,
        check_difficulty=config.petition_base_difficulty,
    )
    CourtGrantOfferDetails.objects.create(offer=offer, covenant=covenant)

    covenant.court_grant_role = role
    covenant.save(update_fields=["court_grant_role"])
    return role
