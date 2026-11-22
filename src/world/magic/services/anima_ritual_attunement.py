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
from world.magic.exceptions import (
    AnimaRitualPickError,
    CharacterEngagedForRitual,
    ResonanceInsufficient,
)
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
    from core.models import ArxSharedMemoryModel as SharedMemoryModel
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance

NO_RITUAL_TO_ATTUNE = "You have no anima ritual to attune."
ALREADY_ATTUNED = "Your ritual already carries those resonances."
NOT_ENOUGH_ACTION_POINTS = "You don't have enough action points for that."
NO_PICKS_YET = "Your ritual has no resonances yet. Set them up first, for free."
NO_ANIMA_TO_SPEND = "You have no anima to spend on that."
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
                refusal = ResonanceInsufficient(msg)
                refusal.user_message = (
                    f"You do not have enough {resonance.name} to attune your ritual."
                )
                raise refusal
    return rows


def _action_point_pool(sheet: CharacterSheet, cost: int) -> ActionPointPool | None:
    """The sheet's pool when the attunement costs action points, else None.

    The spend itself is the check (``ActionPointPool.spend`` refuses under a row lock), so the
    caller spends this pool first of everything it charges.

    Raises:
        AnimaRitualPickError: the attunement costs action points and she has no pool.
    """
    if cost <= 0:
        return None
    pool = ActionPointPool.get_or_create_for_character(sheet.character)
    if pool is None:
        raise AnimaRitualPickError(NOT_ENOUGH_ACTION_POINTS)
    return pool


def _put_back(touched: list[tuple[SharedMemoryModel, tuple[str, ...]]]) -> None:
    """Set each row's named in-memory fields to what the database holds.

    A rolled-back spend leaves the identity map showing the spent values, and
    ``refresh_from_db`` would copy the cached instance onto itself, so the stored values are read
    with ``values`` (which builds no model) and put back on the instance.
    """
    for row, names in touched:
        stored = type(row).objects.filter(pk=row.pk).values(*names).first()
        if stored is not None:
            for name, value in stored.items():
                setattr(row, name, value)


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

    Every refusal is raised before anything is spent (in combat, no resonances set up yet, picks
    unchanged, a changed pick not held or of the wrong affinity, too little resonance or action
    points, no anima row when anima is charged). Then, in one transaction: the action points are
    spent, the anima is deducted (a shortfall becomes Soulfray, never a refusal), each newly picked
    resonance pays its balance, and the attunement check is rolled when staff set one. Both picks
    are written only when there is no check or the roll succeeds; a failed roll keeps the costs and
    the old picks.

    If anything raises after the first spend, the database rolls back and the cached rows (action
    points, anima, resonance balances, the ritual's picks) are put back to match it.

    Raises:
        AnimaRitualPickError: she has no ritual, is in combat, has not set the picks up yet, the
            picks are what the ritual already carries, a changed pick fails
            ``check_anima_ritual_picks`` (a pick she keeps stays even once she no longer holds
            it), or she has too few action points.
        ResonanceInsufficient: a newly picked resonance holds less than the attunement costs.
    """
    config = ritual_config_of(sheet)
    if config is None:
        raise AnimaRitualPickError(NO_RITUAL_TO_ATTUNE)
    costs = AnimaConfig.get_singleton()
    picks_before = (config.primal_resonance, config.outward_resonance)
    touched: list[tuple[SharedMemoryModel, tuple[str, ...]]] = []
    committed = False
    try:
        with transaction.atomic():
            result = _attune(sheet, config, costs, primal, outward, touched)
        committed = True
        return result
    finally:
        if not committed:
            # The database has rolled back; the identity map has not.
            _put_back(touched)
            config.primal_resonance, config.outward_resonance = picks_before
            sheet.character.resonances.invalidate()


def _check_attunable(
    sheet: CharacterSheet,
    config: RitualCheckConfig,
    primal: Resonance | None,
    outward: Resonance | None,
) -> dict[str, int | None]:
    """Refuse an attunement the ritual cannot take, and return the picks it stores now (read
    under a row lock, so two attunements racing cannot both pay). Nothing has been spent.

    Raises:
        AnimaRitualPickError: she is in combat, the ritual has no picks yet (the free setup is the
            only way to set empty picks), the picks are what it carries, or they fail
            ``check_anima_ritual_picks``.
    """
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    if CharacterEngagement.objects.filter(character_id=sheet.character.pk).exists():
        raise AnimaRitualPickError(CharacterEngagedForRitual.user_message)
    stored = (
        RitualCheckConfig.objects.select_for_update()
        .values("primal_resonance_id", "outward_resonance_id")
        .get(pk=config.pk)
    )
    if stored["primal_resonance_id"] is None and stored["outward_resonance_id"] is None:
        raise AnimaRitualPickError(NO_PICKS_YET)
    if (primal.pk if primal else None, outward.pk if outward else None) == (
        stored["primal_resonance_id"],
        stored["outward_resonance_id"],
    ):
        raise AnimaRitualPickError(ALREADY_ATTUNED)
    check_anima_ritual_picks(
        sheet,
        primal,
        outward,
        primal_changed=(primal.pk if primal else None) != stored["primal_resonance_id"],
        outward_changed=(outward.pk if outward else None) != stored["outward_resonance_id"],
    )
    return stored


def _attune(  # noqa: PLR0913 - one attunement's whole context
    sheet: CharacterSheet,
    config: RitualCheckConfig,
    costs: AnimaConfig,
    primal: Resonance | None,
    outward: Resonance | None,
    touched: list[tuple[SharedMemoryModel, tuple[str, ...]]],
) -> AttunementResult:
    """The body of ``attune_anima_ritual``, inside its transaction. Rows the spend section
    changes are added to ``touched`` before it starts, so the caller can put them back."""
    stored = _check_attunable(sheet, config, primal, outward)
    newly_picked = _newly_picked(stored, primal, outward)
    rows = _lock_and_check_resonance(sheet, newly_picked, costs.attunement_resonance_cost)
    pool = _action_point_pool(sheet, costs.attunement_ap_cost)
    anima = CharacterAnima.objects.filter(character_id=sheet.pk).first()
    if anima is None and costs.attunement_anima_cost > 0:
        raise AnimaRitualPickError(NO_ANIMA_TO_SPEND)
    if pool is not None:
        touched.append((pool, ("current", "banked")))
    if anima is not None:
        touched.append((anima, ("current", "glut")))
    touched.extend((row, ("balance",)) for row in rows.values())

    # The costs. The action points go first: ``spend`` is itself the check, and refuses before
    # anything else has been charged.
    if pool is not None and not pool.spend(costs.attunement_ap_cost):
        raise AnimaRitualPickError(NOT_ENOUGH_ACTION_POINTS)
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
