"""Narration for windup telegraphs, wrecks and fizzles."""

from __future__ import annotations

from django.db.models import Q

from world.combat import services as _svc
from world.combat.constants import (
    WINDUP_GENERIC_TELEGRAPH,
    WINDUP_NO_TARGET_LABEL,
    WINDUP_TARGET_CLAUSE,
    ParticipantStatus,
)
from world.combat.models import CombatEncounter, CombatParticipant, PendingOpponentAttack


def _find_windup_caller(encounter: CombatEncounter) -> CombatParticipant | None:
    """First ACTIVE participant flagged to auto-call enemy wind-ups (#2637 design 6).

    A participant qualifies when their character holds an active
    (``left_at__isnull=True``), engaged ``CharacterCovenantRole`` whose
    ``covenant_role`` (or that role's ``parent_role`` — the riding rule
    mirrors ``CovenantRole.blend_weight_for``) has ``calls_out_windups=True``.
    Deterministic by participant pk. Two queries total (participants, then one
    batched membership query), never a query per candidate.
    """
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("character_sheet__character")
        .order_by("pk")
    )
    if not participants:
        return None

    sheet_ids = [p.character_sheet_id for p in participants]
    flagged_sheet_ids = set(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=sheet_ids,
            engaged=True,
            left_at__isnull=True,
        )
        .filter(
            Q(covenant_role__calls_out_windups=True)
            | Q(covenant_role__parent_role__calls_out_windups=True)
        )
        .values_list("character_sheet_id", flat=True)
    )
    for participant in participants:
        if participant.character_sheet_id in flagged_sheet_ids:
            return participant
    return None


def _broadcast_windup_telegraph(pending: PendingOpponentAttack, *, caller_name: str | None) -> None:
    """Announce a newly-declared wind-up, always naming its target (#2637 design 2, 6; #3572)."""
    target_name = (
        str(pending.target.character_sheet.character)
        if pending.target is not None
        else WINDUP_NO_TARGET_LABEL
    )
    template = pending.threat_entry.windup_telegraph or WINDUP_GENERIC_TELEGRAPH
    if "{target}" not in template:
        template = template + WINDUP_TARGET_CLAUSE
    narration = template.format(opponent=pending.opponent.name, target=target_name)
    if caller_name:
        narration = f"{narration} - {caller_name} calls it!"
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_windup_wreck(pending: PendingOpponentAttack, attacker_name: str) -> None:
    """Announce a PC hit staggering a winding-up opponent (#2637 design 4)."""
    narration = f"{attacker_name}'s strike staggers {pending.opponent.name}'s wind-up!"
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)


def _broadcast_windup_fizzled(pending: PendingOpponentAttack, *, reason: str = "") -> None:
    """Announce a wind-up that never lands (#2637 design 3)."""
    if reason:
        narration = f"{pending.opponent.name}'s wind-up {reason} and comes to nothing!"
    else:
        narration = (
            f"{pending.opponent.name}'s wind-up is broken entirely — the perfect chain cancels it!"
        )
    _svc._broadcast_commitment_line(pending.encounter, narration)  # noqa: SLF001 (test patch seam)
