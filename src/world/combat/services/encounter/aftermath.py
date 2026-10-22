"""Aftermath rules and opponent aftermath pools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.constants import EncounterOutcome, OpponentStatus, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    EncounterAftermathRule,
)
from world.combat.services.declarations.social_check import _record_combat_consequence
from world.conditions.services import spend_contributing_conditions

if TYPE_CHECKING:
    from world.scenes.models import Interaction


def _apply_aftermath_rules(
    encounter: CombatEncounter,
    outcome: EncounterOutcome,
    interaction: Interaction | None,
) -> None:
    """Per-PC graded aftermath via the authored (outcome, risk) cell (#876 §3).

    Mirrors _resolve_flee's pipeline: modifiers → select_consequence (theater
    included) → apply_resolution → record_consequence_outcome anchored to the
    encounter OUTCOME interaction. Legend, when authored, rides LEGEND_AWARD
    consequences in the pool — context.participants carries the PC's persona.

    context.interaction also carries the same OUTCOME interaction (#2987):
    LEGEND_AWARD reads it to open a WITNESS reaction window when the deed
    lands public and crime-tagged, so bystanders in the encounter's scene get
    a report/intervene/ignore choice on the same event this aftermath fires
    from.
    """
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_resolution,
        resolve_pool_consequences,
        select_consequence,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    rule = (
        EncounterAftermathRule.objects.filter(outcome=outcome, risk_level=encounter.risk_level)
        .select_related("check_type", "consequence_pool")
        .first()
    )
    if rule is None or rule.consequence_pool_id is None:
        return

    affected_status = (
        ParticipantStatus.FLED if outcome == EncounterOutcome.FLED else ParticipantStatus.ACTIVE
    )
    affected = list(
        CombatParticipant.objects.filter(
            encounter=encounter, status=affected_status
        ).select_related("character_sheet__character")
    )
    consequences = resolve_pool_consequences(rule.consequence_pool)

    for participant in affected:
        sheet = participant.character_sheet
        character = sheet.character
        breakdown = _svc.collect_check_modifiers(sheet, rule.check_type, scene=encounter.scene)
        pending = select_consequence(
            character,
            rule.check_type,
            rule.base_difficulty,
            consequences,
            extra_modifiers=breakdown.extra_modifiers_total,
        )
        spend_contributing_conditions(breakdown)
        try:
            participants_ctx = [sheet.primary_persona]
        except Persona.DoesNotExist:
            participants_ctx = None
        apply_resolution(
            pending,
            ResolutionContext(
                character=character,
                scene=encounter.scene,
                participants=participants_ctx,
                interaction=interaction,
            ),
        )
        _record_combat_consequence(
            sheet,
            rule.check_type,
            rule.consequence_pool,
            pending,
            breakdown,
            interaction=interaction,
            summary=f"encounter aftermath ({outcome.label})",
        )


def _apply_opponent_aftermath_pools(encounter: CombatEncounter, outcome: EncounterOutcome) -> None:
    """Fire each overcome opponent's authored aftermath pool on PC victory (#876 §4, #4091).

    "Overcome" covers both a DEFEATED enemy and a WON_OVER one (charmed, turned
    or calmed into standing down rather than beaten down — Decision 10): the
    same per-opponent pool pays out either way. Deterministic (story-consequence
    semantics, like beat pools). Context follows the beats GLOBAL idiom: the
    opponent's ObjectDB when set, else an unsaved stub that is only
    identity-safe for non-character effects.
    """
    if outcome != EncounterOutcome.VICTORY:
        return

    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.checks.consequence_resolution import (  # noqa: PLC0415
        apply_pool_deterministically,
    )
    from world.checks.types import ResolutionContext  # noqa: PLC0415

    qs = CombatOpponent.objects.filter(
        encounter=encounter,
        status__in=[OpponentStatus.DEFEATED, OpponentStatus.WON_OVER],
        aftermath_pool__isnull=False,
    ).select_related("aftermath_pool", "objectdb")
    for opponent in qs:
        character = opponent.objectdb or ObjectDB()  # unsaved stub — non-character effects only
        apply_pool_deterministically(
            pool=opponent.aftermath_pool,
            context=ResolutionContext(character=character, scene=encounter.scene),
        )
