"""Sent-flying markers, triggers and landings."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.constants import SENT_FLYING_IMPACT_FRACTION, ParticipantStatus
from world.combat.models import CombatEncounter, CombatOpponentAction, CombatParticipant
from world.combat.services.npc.narration import _dual_dispatch_combat_narration
from world.combat.services.npc.windup_narration import _find_windup_caller
from world.combat.services.sent_flying.sent_flying_catch import _try_catch_sent_flying

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionTemplate


# ---------------------------------------------------------------------------
# Sent Flying (#2638) — the plummet-pattern's first "in-flight" consequence.
#
# A sends_flying ThreatPoolEntry's attack that lands damage > 0 applies the
# seeded "Sent Flying" marker condition (a produced, reactable moment — see
# world.combat.sent_flying_content) and is IMMEDIATELY answerable by the same
# armed-INTERPOSE reaction economy _try_interpose reads. Left unanswered, the
# marker resolves explicitly at the end of resolve_round: a plummet if the
# victim's room supports one, else a hard-landing impact debit.
# ---------------------------------------------------------------------------


def _broadcast_sent_flying_launch(participant: CombatParticipant) -> None:
    """Announce a Sent Flying marker landing (#2638) — the produced moment."""
    name = str(participant.character_sheet.character)
    narration = f"{name} is sent FLYING by the blow!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _sent_flying_windup_caller(
    encounter: CombatEncounter, npc_action: CombatOpponentAction
) -> str | None:
    """The wind-up caller's name if *npc_action* matured from a called-out wind-up.

    ``PendingOpponentAttack`` (which carries ``called_out``) is deleted at
    maturation, so ``matured_from_called_out_windup`` is the only surviving
    record. v1 approximation: re-derives the CURRENT flagged auto-caller via
    ``_find_windup_caller`` rather than persisting the specific caller who
    called THIS wind-up out — at most one call-out fires per round per
    encounter (#2637 design 6), so this is accurate whenever the flagged role
    hasn't changed hands mid-round, which is the overwhelmingly common case.
    """
    if not npc_action.matured_from_called_out_windup:
        return None
    caller = _find_windup_caller(encounter)
    return str(caller.character_sheet.character) if caller is not None else None


def _broadcast_sent_flying_catch(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    catcher: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Announce a mid-air catch (#2638), naming the catcher + the caller if any."""
    victim_name = str(participant.character_sheet.character)
    narration = f"{catcher} catches {victim_name} out of the air!"
    caller_name = _sent_flying_windup_caller(participant.encounter, npc_action)
    if caller_name:
        narration = f"{narration} {caller_name}'s call-out made the difference!"
    _dual_dispatch_combat_narration(participant.encounter, narration)


def _clear_sent_flying_marker(
    participant: CombatParticipant,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    template: ConditionTemplate,
) -> None:
    """Remove the Sent Flying condition + reset its damage carrier (#2638)."""
    from world.conditions.services import remove_condition  # noqa: PLC0415

    remove_condition(character, template)
    participant.sent_flying_damage = 0
    participant.save(update_fields=["sent_flying_damage"])


def _trigger_sent_flying(
    participant: CombatParticipant,
    npc_action: CombatOpponentAction,
    damage: int,
) -> None:
    """Apply the Sent Flying marker and consult the reaction seam (#2638).

    Fires when a ``sends_flying`` ThreatPoolEntry's attack lands damage > 0 on
    a PC participant (called from ``_resolve_npc_action_on_target``). Applies
    the seeded marker, stamps the triggering damage onto
    ``CombatParticipant.sent_flying_damage`` (the v1 carrier — see that
    field's help text), dual-dispatches the produced-moment narration, then
    IMMEDIATELY consults :func:`_try_catch_sent_flying`. A landed catch clears
    the marker and celebrates; otherwise the marker is left in place, silent,
    for :func:`_resolve_sent_flying_markers` at end of round.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    character = participant.character_sheet.character
    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        # Unseeded content (mirrors _ensure_interpose_challenges' warn-and-skip
        # shape) — a dev/test environment that never ran ensure_sent_flying_content.
        return

    apply_condition(character, template)
    participant.sent_flying_damage = damage
    participant.save(update_fields=["sent_flying_damage"])
    _broadcast_sent_flying_launch(participant)

    catcher = _try_catch_sent_flying(participant)
    if catcher is None:
        return
    _clear_sent_flying_marker(participant, character, template)
    _broadcast_sent_flying_catch(participant, npc_action, catcher)


def _resolve_one_sent_flying_landing(
    participant: CombatParticipant,
    template: ConditionTemplate,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> None:
    """Land one unanswered Sent Flying marker: plummet chain, or a hard impact (#2638).

    Reuses the plummet system's own fall-eligibility seam
    (``maybe_emit_fall`` — emits ``EventName.FELL`` only when the destination
    Position is CHASM) rather than reimplementing it: if the victim's room has
    a CHASM position, they are launched over the edge into it and
    ``maybe_emit_fall`` hands off to the existing multi-round descent +
    CATCH_THE_FALLER machinery — zero new machinery, per the design.
    Otherwise this is a hard, unassisted landing: a second Physical debit of
    ``floor(sent_flying_damage * SENT_FLYING_IMPACT_FRACTION)`` through the
    STANDARD combat damage path (``apply_damage_to_participant`` +
    ``process_damage_consequences`` — the same two-call shape
    ``_resolve_npc_action_on_target`` uses for every other NPC hit), resolved
    at its full computed value with NO extra narration beyond whatever that
    standard path already produces — the celebrate/silence boundary: an
    unanswered landing is unremarked. The marker + its damage carrier are
    cleared either way.
    """
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        maybe_emit_fall,
    )
    from world.combat.sent_flying_content import (  # noqa: PLC0415
        SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME,
    )
    from world.conditions.models import DamageType  # noqa: PLC0415
    from world.vitals.services import process_damage_consequences  # noqa: PLC0415

    damage = participant.sent_flying_damage
    _clear_sent_flying_marker(participant, character, template)

    room = character.location
    chasm = (
        Position.objects.filter(room=room, kind=PositionKind.CHASM).first()
        if room is not None
        else None
    )
    if chasm is not None:
        force_move_to_position(character, chasm)
        maybe_emit_fall(character, chasm)
        return

    impact = math.floor(damage * SENT_FLYING_IMPACT_FRACTION)
    if impact <= 0:
        return

    damage_type = DamageType.objects.filter(name=SENT_FLYING_IMPACT_DAMAGE_TYPE_NAME).first()
    dmg_result = _svc.apply_damage_to_participant(
        participant,
        impact,
        damage_type=damage_type,
    )
    process_damage_consequences(
        character_sheet=participant.character_sheet,
        damage_dealt=dmg_result.damage_dealt,
        damage_type=damage_type,
    )


def _resolve_sent_flying_markers(encounter: CombatEncounter) -> None:
    """Explicitly resolve every unanswered Sent Flying marker at round end (#2638).

    Mirrors the plummet system's own explicit-resolution idiom — never a
    per-round DoT tick. Batches: one participant query (candidates carrying a
    nonzero damage carrier) + one BATCHED ``ConditionInstance`` existence
    check across every candidate's character (never a query per participant —
    "no queries in loops"); a candidate whose marker was already cleared by a
    mid-air catch (or removed by some other path) just gets its stale carrier
    zeroed, no landing resolution. Called from ``resolve_round`` after the
    round-tick pass and before boss phase transitions.
    """
    from world.combat.sent_flying_content import SENT_FLYING_CONDITION_NAME  # noqa: PLC0415
    from world.conditions.models import ConditionInstance, ConditionTemplate  # noqa: PLC0415

    try:
        template = ConditionTemplate.get_by_name(SENT_FLYING_CONDITION_NAME)
    except ConditionTemplate.DoesNotExist:
        return

    marked = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
            sent_flying_damage__gt=0,
        ).select_related("character_sheet__character")
    )
    if not marked:
        return

    character_ids = [p.character_sheet.character_id for p in marked]
    still_marked_ids = set(
        ConditionInstance.objects.filter(
            condition=template,
            target_id__in=character_ids,
            is_suppressed=False,
        ).values_list("target_id", flat=True)
    )

    for p in marked:
        character = p.character_sheet.character
        if character.id not in still_marked_ids:
            # Stale carrier (marker already cleared elsewhere) — just reset it.
            p.sent_flying_damage = 0
            p.save(update_fields=["sent_flying_damage"])
            continue
        _resolve_one_sent_flying_landing(p, template, character)
