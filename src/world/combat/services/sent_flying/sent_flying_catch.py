"""Catching a sent-flying target."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from world.combat.constants import REACTIONS_PER_ROUND, CombatManeuver, ParticipantStatus
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services.damage.interpose_dispatch import _narrate_reaction_declined
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from typeclasses.characters import Character


def _try_catch_sent_flying(participant: CombatParticipant) -> Character | None:
    """Find and fire the first eligible armed INTERPOSE to catch a Sent Flying victim.

    Same query shape as :func:`_try_interpose` (an armed INTERPOSE this round
    whose ``focused_ally_target`` is *participant* or ``None``), restricted to
    ACTIVE participants and excluding self-interpose. The fire gate is
    budget-only — ``REACTIONS_PER_ROUND`` via the interposer's
    ``reactions_used`` (#2639) — and deliberately never calls
    ``dispatch_interpose``/the mundane or technique challenge chain: that
    machinery grades HOW MUCH of a landing hit's *amount* a block reduces,
    which has no meaning for a mid-air catch (a binary rescue, not gradeable
    damage mitigation). "Fires" here means the SAME thing
    ``_dispatch_interpose_action``'s docstring documents for the mundane path:
    an attempt that clears budget, independent of any roll. Only one guardian
    is ever queried (the first eligible), so
    ``combat.constants.ABSORPTION_CAP_PER_MOMENT`` — built for multiple
    interceptors answering ONE ``DamagePreApplyPayload`` — has no second
    attempt to cap here; not consulted (documented v1 scope, #2638).

    Returns the catching Character on fire, or None (no eligible/budget-
    exhausted guardian (who is told privately, #3574): the marker stays for
    explicit resolution).
    """
    encounter = participant.encounter
    if encounter.status != RoundStatus.RESOLVING:
        return None

    # Q(...) | Q(...), not `focused_ally_target__in=[participant, None]`: the
    # latter silently drops the None entry (Django compiles field__in with a
    # None member to a bare `IN (x)`, never `x OR field IS NULL`) — see the
    # bug-fix note on _try_interpose's identical query, discovered while
    # writing this sibling (#2638).
    action = (
        CombatRoundAction.objects.filter(
            Q(focused_ally_target=participant) | Q(focused_ally_target__isnull=True),
            participant__encounter=encounter,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.INTERPOSE,
            participant__status=ParticipantStatus.ACTIVE,
        )
        .exclude(participant=participant)
        .select_related("participant__character_sheet__character")
        .first()
    )
    if action is None:
        return None

    interposer = action.participant
    if interposer.reactions_used >= REACTIONS_PER_ROUND:
        _narrate_reaction_declined(
            interposer.character_sheet.character,
            participant.character_sheet.character,
            cap=False,
        )
        return None

    interposer.reactions_used += 1
    interposer.save(update_fields=["reactions_used"])
    return interposer.character_sheet.character
