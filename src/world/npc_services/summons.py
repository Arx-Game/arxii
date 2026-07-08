"""Directed-offer summonses — a master's wish aimed at a specific servant (#2050).

A :class:`~world.npc_services.models.OfferSummons` is a targeted offer with an
explicit accept/decline moment. Accepting delegates to the existing offer rails
(``resolve_offer`` → ``issue_mission``); declining or letting it lapse is an
explicit, recorded act the master remembers: affection drops, a refusal streak
climbs, and past the threshold the master's escalation pool fires.

Generic per ADR-0010/ADR-0085 — any ``NPCRole`` can direct an offer at a
persona. The Court layer contributes its escalation config on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.covenants.constants import CovenantType
from world.npc_services.constants import (
    SUMMONS_REFUSAL_AFFECTION_DELTA,
    SummonsStatus,
)
from world.npc_services.models import NPCRole, NPCServiceOffer, NPCStanding, OfferSummons
from world.npc_services.services import (
    OfferNotEligibleError,
    ResolveOfferError,
    adjust_npc_affection,
    resolve_offer,
    start_interaction,
)

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB as Character
    from gm.models import GMProfile
    from scenes.models import Persona


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummonsResult:
    """Result of responding to a summons."""

    success: bool
    message: str
    risk_tier: int | None = None
    stake_summaries: tuple[str, ...] = ()
    instance_pk: int | None = None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@transaction.atomic
def create_summons(
    offer: NPCServiceOffer,
    target_persona: Persona,
    *,
    message: str = "",
    expires_at: datetime | None = None,
    created_by: GMProfile | None = None,
) -> OfferSummons:
    """Create a directed-offer summons targeting a specific persona (#2050).

    Validation only — permissions live at the view layer (``IsGMOrStaff``).
    The offer must be MISSION-kind (v1 scope).
    """
    summons = OfferSummons(
        offer=offer,
        target_persona=target_persona,
        message=message,
        expires_at=expires_at,
        created_by=created_by,
    )
    summons.full_clean()
    summons.save()
    return summons


# ---------------------------------------------------------------------------
# Respond — accept or decline
# ---------------------------------------------------------------------------


@transaction.atomic
def respond_to_summons(
    summons: OfferSummons,
    character: Character,
    *,
    accept: bool,
    acknowledge_risk: bool = False,
) -> SummonsResult:
    """Accept or decline a summons (#2050).

    Accept: builds an ephemeral :class:`InteractionSession` internally (role
    from ``summons.offer.role``, persona = target) and delegates to
    ``resolve_offer`` → ``issue_mission``. The risk-ack gate and eligibility
    re-check stay intact — a failed accept leaves the summons PENDING.

    Decline: sets DECLINED + calls :func:`record_summons_refusal`.
    """
    if summons.status != SummonsStatus.PENDING:
        return SummonsResult(
            success=False,
            message=f"This summons is already {summons.status}.",
        )

    if accept:
        return _accept_summons(summons, character, acknowledge_risk=acknowledge_risk)
    return _decline_summons(summons)


def _accept_summons(
    summons: OfferSummons,
    character: Character,
    *,
    acknowledge_risk: bool,
) -> SummonsResult:
    """Accept path: build session, delegate to resolve_offer, handle risk gate."""
    from world.missions.services.offer_handler import (  # noqa: PLC0415
        MissionRiskUnacknowledgedError,
        acknowledge_mission_risk,
    )

    offer = summons.offer
    role = offer.role

    # Build the ephemeral interaction session internally — mirrors
    # StartNPCInteractionAction's construction.  The NPC persona is None for
    # class-1 functionaries (the common case for GM-voiced Court masters).
    session = start_interaction(
        role=role,
        persona=summons.target_persona,
        character=character,
        npc_persona=None,
    )

    try:
        result = resolve_offer(session, offer)
    except MissionRiskUnacknowledgedError as exc:
        if not acknowledge_risk:
            # Two-phase risk-ack: the summons stays PENDING; the wager text
            # returns to the player for an informed-consent prompt.
            return SummonsResult(
                success=False,
                message=_risk_prompt_message(exc),
                risk_tier=exc.risk_tier,
                stake_summaries=exc.stake_summaries,
            )
        acknowledge_mission_risk(offer, summons.target_persona)
        try:
            result = resolve_offer(session, offer)
        except ResolveOfferError as retry_exc:
            # Eligibility failure on retry — summons stays PENDING.
            return SummonsResult(success=False, message=retry_exc.user_message)
    except OfferNotEligibleError as exc:
        # Eligibility failure — summons stays PENDING with the error's message.
        return SummonsResult(success=False, message=exc.user_message)
    except ResolveOfferError as exc:
        return SummonsResult(success=False, message=exc.user_message)

    # Success: mark ACCEPTED, reset the refusal streak, stamp resolved_at.
    now = timezone.now()
    summons.status = SummonsStatus.ACCEPTED
    summons.resolved_at = now
    summons.save(update_fields=["status", "resolved_at"])

    _reset_refusal_streak(summons.target_persona, role)

    instance_pk = result.payload.get("instance_pk") if result.payload else None
    return SummonsResult(
        success=True,
        message=result.message,
        instance_pk=instance_pk,
    )


def _decline_summons(summons: OfferSummons) -> SummonsResult:
    """Decline path: set DECLINED + record refusal."""
    now = timezone.now()
    summons.status = SummonsStatus.DECLINED
    summons.resolved_at = now
    summons.save(update_fields=["status", "resolved_at"])

    record_summons_refusal(summons.target_persona, role=summons.offer.role)

    return SummonsResult(
        success=True,
        message="You decline the summons.",
    )


def _risk_prompt_message(exc) -> str:  # type: ignore[no-untyped-def]
    """Build the player-facing risk prompt (mirrors the action layer)."""
    lines = ["This summons is dangerous; you must acknowledge the risk before accepting."]
    if exc.stake_summaries:
        lines.append("Stakes:")
        lines.extend(f"  - {s}" for s in exc.stake_summaries)
    lines.append("Re-run with 'hire accept <summons-id> confirm' to acknowledge.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Refusal recording + escalation
# ---------------------------------------------------------------------------


@transaction.atomic
def record_summons_refusal(target_persona: Persona, *, role: NPCRole) -> bool:
    """Record a summons refusal: drop affection, bump streak, maybe fire escalation.

    Returns True if the escalation threshold was crossed (pool fired).

    Affection drop uses :func:`adjust_npc_affection` (atomic F()-based update).
    The streak increments on the same standing row. When the role is
    court-backed (``covenant.court_grant_role`` or ``faction_affiliation``)
    and the streak crosses the config threshold, the escalation pool fires
    via :func:`apply_pool_deterministically` and the streak resets.
    Non-court roles: affection shift only, v1.
    """
    from world.checks.consequence_resolution import apply_pool_deterministically  # noqa: PLC0415
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    # Resolve the NPC persona for the standing row.  For class-1 functionaries
    # (no named persona), the standing row is keyed on the role's functionary
    # persona if one exists, else we skip the standing/refusal path — there's
    # no durable relationship to cool.
    npc_persona = _resolve_npc_persona_for_role(role)
    if npc_persona is None:
        return False

    # Drop affection (creates the standing row at 0 if absent).
    adjust_npc_affection(target_persona, npc_persona, delta=SUMMONS_REFUSAL_AFFECTION_DELTA)

    # Reload the standing row to get the current streak value.
    standing = NPCStanding.objects.filter(
        persona=target_persona,
        npc_persona=npc_persona,
    ).first()
    if standing is None:
        return False

    standing.consecutive_refused_summons += 1
    standing.save(update_fields=["consecutive_refused_summons"])

    # Check if the role is court-backed and the threshold is crossed.
    court_config = _court_config_for_role(role)
    if court_config is None:
        return False

    threshold = court_config.summons_refusal_escalation_threshold
    if standing.consecutive_refused_summons < threshold:
        return False

    # Fire the escalation pool.
    pool = court_config.summons_refusal_escalation_pool or court_config.escalation_consequence_pool
    if pool is None:
        return False

    character = target_persona.character_sheet.character
    context = ResolutionContext(character=character, target=character)
    apply_pool_deterministically(pool=pool, context=context)

    # Reset the streak after firing.
    standing.consecutive_refused_summons = 0
    standing.save(update_fields=["consecutive_refused_summons"])
    return True


def _reset_refusal_streak(target_persona: Persona, role: NPCRole) -> None:
    """Reset the refusal streak on acceptance (the success leg)."""
    npc_persona = _resolve_npc_persona_for_role(role)
    if npc_persona is None:
        return
    updated = NPCStanding.objects.filter(
        persona=target_persona,
        npc_persona=npc_persona,
        consecutive_refused_summons__gt=0,
    ).update(consecutive_refused_summons=0)
    if updated:
        # Flush the cached SharedMemoryModel instance.
        NPCStanding.objects.filter(
            persona=target_persona,
            npc_persona=npc_persona,
        ).first()


def _resolve_npc_persona_for_role(role: NPCRole) -> Persona | None:
    """Resolve the NPC persona for a role, for standing-key purposes.

    For Court roles, the covenant's leader is the NPC.  A role is
    court-backed when it is the covenant's ``court_grant_role`` OR when it
    fronts the covenant's organization (``faction_affiliation``).
    """
    covenant = _covenant_for_role(role)
    if covenant is not None and covenant.leader_id is not None:
        return covenant.leader.primary_persona
    return None


def _covenant_for_role(role: NPCRole):
    """Return the Covenant whose court_grant_role or org this role belongs to."""
    from world.covenants.models import Covenant  # noqa: PLC0415

    # Direct: the covenant's court_grant_role is this role.
    covenant = Covenant.objects.filter(court_grant_role=role).first()
    if covenant is not None:
        return covenant
    # Indirect: the role fronts the covenant's organization.
    if role.faction_affiliation_id is not None:
        covenant = Covenant.objects.filter(
            organization_id=role.faction_affiliation_id,
            covenant_type=CovenantType.COURT,
        ).first()
        if covenant is not None:
            return covenant
    return None


def _court_config_for_role(role: NPCRole):
    """Return the CourtGrantConfig if this role is court-backed, else None."""
    covenant = _covenant_for_role(role)
    if covenant is None:
        return None
    from world.covenants.services import get_court_grant_config  # noqa: PLC0415

    return get_court_grant_config()


# ---------------------------------------------------------------------------
# Expire — cron sweep
# ---------------------------------------------------------------------------


@transaction.atomic
def expire_summonses() -> int:
    """Cron sweep: past-due PENDING → EXPIRED + refusal hook (#2050).

    Returns the count of newly expired summonses. Each expiry counts as a
    refusal (affection drop + streak bump). Uses ``select_for_update`` so the
    sweep racing a respond call resolves to exactly one terminal status.
    """
    now = timezone.now()
    pending = OfferSummons.objects.select_for_update().filter(
        status=SummonsStatus.PENDING, expires_at__lte=now
    )
    expired_count = 0
    for summons in pending:
        summons.status = SummonsStatus.EXPIRED
        summons.resolved_at = now
        summons.save(update_fields=["status", "resolved_at"])
        record_summons_refusal(summons.target_persona, role=summons.offer.role)
        expired_count += 1
    return expired_count
