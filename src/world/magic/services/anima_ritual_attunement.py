"""Attuning an anima ritual: the paid way to change its two picks (#5280).

The first setup of a ritual's picks is free (``anima_ritual_picks``). After that the picks are
locked, and a character changes them by attuning the ritual to a new pair of resonances she
holds. An attunement costs what staff set on ``AnimaConfig`` (anima, resonance and action
points), and may roll the config's check: a failed roll spends the costs and leaves the picks as
they were.

Nothing is spent for a refusal: an attunement that changes nothing, a pick she does not hold or
of the wrong affinity, too little resonance in a newly picked resonance, or too few action points.
Anima is never a refusal: what she lacks is drawn from her life force and becomes Soulfray, as
every other spend of anima does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.action_points.models import ActionPointPool
from world.magic.exceptions import AnimaRitualPickError, ResonanceInsufficient
from world.magic.models import (
    AnimaConfig,
    CharacterAnima,
    CharacterResonance,
    RitualCheckConfig,
    SoulfrayConfig,
)
from world.magic.services.anima import deduct_anima, ritual_succeeded
from world.magic.services.anima_ritual_picks import check_anima_ritual_picks, ritual_config_of
from world.magic.services.soulfray import accumulate_soulfray
from world.magic.types.ritual import AttunementResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance

NO_RITUAL_TO_ATTUNE = "You have no anima ritual to attune."
ALREADY_ATTUNED = "Your ritual already carries those resonances."
NOT_ENOUGH_ACTION_POINTS = "You don't have enough action points for that."
ATTUNEMENT_FAILED = "Your attunement did not take hold. Your ritual keeps the resonances it had."


def _attuned_line(primal: Resonance | None, outward: Resonance | None) -> str:
    names = " and ".join(r.name for r in (primal, outward) if r is not None)
    return f"Your ritual is now attuned to {names}."


def _newly_picked(
    stored: dict[str, int | None], primal: Resonance | None, outward: Resonance | None
) -> list[Resonance]:
    """The picks that are not what the ritual carries now, in resonance order."""
    fresh = [
        resonance
        for resonance, current in (
            (primal, stored["primal_resonance_id"]),
            (outward, stored["outward_resonance_id"]),
        )
        if resonance is not None and resonance.pk != current
    ]
    return sorted(fresh, key=lambda resonance: resonance.pk)


def _lock_and_check_resonance(
    sheet: CharacterSheet, newly_picked: list[Resonance], cost: int
) -> dict[int, CharacterResonance]:
    """Lock the rows of the newly picked resonances (in resonance order, so two attunements
    cannot deadlock) and refuse when any holds less than ``cost``.

    Raises:
        ResonanceInsufficient: a newly picked resonance whose balance is below ``cost``.
    """
    rows = {
        row.resonance_id: row
        for row in CharacterResonance.objects.select_for_update()
        .filter(character_sheet=sheet, resonance__in=newly_picked)
        .order_by("resonance_id")
    }
    if cost > 0:
        for resonance in newly_picked:
            if rows[resonance.pk].balance < cost:
                msg = f"Need {cost} {resonance.name} resonance, have {rows[resonance.pk].balance}."
                raise ResonanceInsufficient(msg)
    return rows


def _check_action_points(sheet: CharacterSheet, cost: int) -> ActionPointPool | None:
    """The sheet's pool when it can pay ``cost`` (None when the cost is 0 and she has no pool).

    Raises:
        AnimaRitualPickError: she has too few action points.
    """
    if cost <= 0:
        return None
    pool = ActionPointPool.get_or_create_for_character(sheet.character)
    held = (
        ActionPointPool.objects.select_for_update()
        .filter(pk=pool.pk)
        .values_list("current", flat=True)
        .get()
        if pool is not None
        else 0
    )
    if pool is None or held < cost:
        raise AnimaRitualPickError(NOT_ENOUGH_ACTION_POINTS)
    return pool


def _spend_anima(sheet: CharacterSheet, cost: int) -> int:
    """Charge ``cost`` anima, glut first, and put any shortfall into Soulfray. Returns the
    shortfall (0 when she had it all)."""

    deficit = deduct_anima(sheet.character, cost)
    if deficit > 0:
        accumulate_soulfray(
            character=sheet.character,
            anima=CharacterAnima.objects.get(character_id=sheet.pk),
            deficit=deficit,
            soulfray_config=SoulfrayConfig.objects.cached_singleton(),
            check_result=None,
        )
    return deficit


def _roll_succeeds(sheet: CharacterSheet, config: AnimaConfig) -> bool:
    """Roll the attunement's check; true when it counts as a success (the ritual's own boundary:
    a Partial Success counts) or when staff set no check."""
    if config.attunement_check_type is None:
        return True
    from world.checks.services import (  # noqa: PLC0415
        difficulty_points,
        perform_check_with_modifiers,
    )

    result = perform_check_with_modifiers(
        sheet.character,
        config.attunement_check_type,
        target_difficulty=difficulty_points(config.attunement_difficulty_level),
    )
    return ritual_succeeded(result.outcome)


def attune_anima_ritual(
    sheet: CharacterSheet, primal: Resonance | None, outward: Resonance | None
) -> AttunementResult:
    """Pay to change the ritual's two picks to ``primal`` and ``outward`` (either may be None).

    Every refusal is raised before anything is spent. Then, in one transaction: the action points
    are spent, the anima is deducted (a shortfall becomes Soulfray, never a refusal), each newly
    picked resonance pays its balance, and the attunement check is rolled when staff set one. Both
    picks are written only when there is no check or the roll succeeds; a failed roll keeps the
    costs and the old picks.

    Raises:
        AnimaRitualPickError: she has no ritual, the picks are what the ritual already carries,
            fail ``check_anima_ritual_picks``, or she has too few action points.
        ResonanceInsufficient: a newly picked resonance holds less than the attunement costs.
    """
    config = ritual_config_of(sheet)
    if config is None:
        raise AnimaRitualPickError(NO_RITUAL_TO_ATTUNE)
    costs = AnimaConfig.get_singleton()
    with transaction.atomic():
        # Read the stored picks under a row lock, so two attunements racing cannot both pay.
        stored = (
            RitualCheckConfig.objects.select_for_update()
            .values("primal_resonance_id", "outward_resonance_id")
            .get(pk=config.pk)
        )
        if (primal.pk if primal else None, outward.pk if outward else None) == (
            stored["primal_resonance_id"],
            stored["outward_resonance_id"],
        ):
            raise AnimaRitualPickError(ALREADY_ATTUNED)
        check_anima_ritual_picks(sheet, primal, outward)
        newly_picked = _newly_picked(stored, primal, outward)
        rows = _lock_and_check_resonance(sheet, newly_picked, costs.attunement_resonance_cost)
        pool = _check_action_points(sheet, costs.attunement_ap_cost)

        # Every refusal is behind us: from here on the costs are paid.
        if pool is not None:
            pool.spend(costs.attunement_ap_cost)
        deficit = _spend_anima(sheet, costs.attunement_anima_cost)
        resonance_spent: dict[int, int] = {}
        if costs.attunement_resonance_cost > 0:
            for resonance in newly_picked:
                row = rows[resonance.pk]
                row.balance -= costs.attunement_resonance_cost
                row.save(update_fields=["balance"])
                resonance_spent[resonance.pk] = costs.attunement_resonance_cost
            sheet.character.resonances.invalidate()
        succeeded = _roll_succeeds(sheet, costs)
        if succeeded:
            config.primal_resonance = primal
            config.outward_resonance = outward
            config.save(update_fields=["primal_resonance", "outward_resonance"])
    return AttunementResult(
        changed=succeeded,
        anima_spent=costs.attunement_anima_cost,
        soulfray_deficit=deficit,
        resonance_spent=resonance_spent,
        message=_attuned_line(primal, outward) if succeeded else ATTUNEMENT_FAILED,
    )
