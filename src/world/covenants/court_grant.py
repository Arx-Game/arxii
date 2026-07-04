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

from django.db import transaction

from world.covenants.exceptions import CourtGrantNotMonotonicError

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.covenants.models import CourtGrantConfig, CourtPact, Covenant
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


def court_grant_petition_ease(*, standing: NPCStanding | None, config: CourtGrantConfig) -> int:
    """Check-ease bonus from the master's affection toward the servant (#1718).

    Shared by both grant channels (formal petition in
    ``world.npc_services.effects.raise_court_grant`` and the emergency draw in
    ``world.combat.pull_helpers._resolve_emergency_draw``) so the ease formula
    lives in exactly one place. ``standing`` may be ``None`` for a brand-new
    servant with no NPCStanding row yet (treated as 0 affection).
    """
    affection = standing.affection if standing is not None else 0
    return affection // config.affection_divisor


def record_court_grant_petition_outcome(
    standing: NPCStanding,
    *,
    succeeded: bool,
    check_result: CheckResult,
    character: Character,
    config: CourtGrantConfig,
) -> bool:
    """Record a Court-grant petition outcome; fire escalation on threshold-crossing (#1718).

    Shared by both grant channels (formal petition + emergency draw) so "call
    ``record_petition_outcome``, and on crossing call ``apply_pool_for_tier``"
    lives in exactly one place — the emergency-draw channel previously
    recorded the outcome but never fired escalation, decoupling the master's
    wrath from that channel. Returns whether the failure streak crossed
    ``config.petition_failure_escalation_threshold`` (mirrors
    ``record_petition_outcome``'s own return value).
    """
    from world.checks.consequence_resolution import apply_pool_for_tier  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.npc_services.services import record_petition_outcome  # noqa: PLC0415

    crossed = record_petition_outcome(
        standing,
        succeeded=succeeded,
        escalation_threshold=config.petition_failure_escalation_threshold,
    )
    outcome = check_result.outcome
    if crossed and config.escalation_consequence_pool_id is not None and outcome is not None:
        apply_pool_for_tier(
            pool=config.escalation_consequence_pool,
            outcome_tier=outcome,
            context=ResolutionContext(character=character, target=character),
        )
    return crossed


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


@transaction.atomic
def ensure_court_grant_role(covenant: Covenant) -> NPCRole:
    """Get-or-create the NPCRole carrying covenant's COURT_GRANT petition offer.

    Idempotent — safe to call on every negotiation attempt. Auto-provisions the
    role + its single petition offer + details row the first time any servant
    of this Court tries to negotiate; staff never need to hand-author this per
    master (#1718 design question 4 — NPC-master automation).

    Locks the covenant row via ``select_for_update`` so concurrent negotiation
    attempts for the same covenant can't both pass the ``court_grant_role_id is
    None`` check (mirrors ``activate_permit`` in
    ``world/buildings/services.py``): the second caller blocks until the first
    commits, then re-reads and returns the role the first caller created
    instead of colliding on the unique ``NPCRole.name``. The whole provisioning
    sequence is one atomic unit, so a failure partway through (e.g. between
    creating the role and saving it onto the covenant) rolls back entirely —
    it never leaves an orphaned ``NPCRole`` that would permanently break every
    later call with an ``IntegrityError``.
    """
    from world.covenants.factories import wire_court_grant_petition_content  # noqa: PLC0415
    from world.covenants.models import Covenant  # noqa: PLC0415
    from world.covenants.services import get_court_grant_config  # noqa: PLC0415
    from world.npc_services.constants import OfferKind  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        CourtGrantOfferDetails,
        NPCRole,
        NPCServiceOffer,
    )

    # Lock the covenant row for the duration of the transaction and re-read
    # court_grant_role_id from that lock — not from the caller's possibly
    # stale in-memory `covenant` — so we don't act on state that another
    # concurrent call is in the middle of writing.
    covenant = Covenant.objects.select_for_update().get(pk=covenant.pk)
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
