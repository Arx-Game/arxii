"""Ritual anima pool contributions and the pool gate (#3001).

A ritual with ``anima_requirement > 0`` is powered by a pool. Anyone present can
pay into it — the price is the only gate, never Gifted-ness:

- **channel** — a participant spends their own anima (glut burns first).
- **prick** — a drop of blood: 1 anima, trivial damage. The folk-rite route.
- **gash** — a serious bleed: ``(1d6+1) x level`` anima with a real wound.
- **sacrifice** — a victim drained wholesale; killing them yields
  ``death_harvest_multiplier x`` their full maximum and fires the murder taint.

Contribution rows (``RitualAnimaContribution``) are the audit trail and outlive
the ``RitualSession`` they fed (sessions delete on fire).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import random
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import AnimaContributionKind
from world.magic.exceptions import RitualPoolError
from world.magic.models.anima import AnimaConfig, CharacterAnima
from world.magic.models.ritual_pool import RitualAnimaContribution

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.rituals import Ritual
    from world.magic.models.sessions import RitualSession
    from world.scenes.models import Scene

logger = logging.getLogger(__name__)

# PLACEHOLDER magnitudes (#3001 ruled values; Apostate tunes).
PRICK_ANIMA = 1
PRICK_DAMAGE = 1
GASH_DIE_SIZE = 6
GASH_DIE_BONUS = 1


def pool_total(session: RitualSession) -> int:
    """Sum of every anima contribution made under *session*."""
    from django.db.models import Sum  # noqa: PLC0415

    total = session.anima_contributions.aggregate(total=Sum("amount"))["total"]
    return total or 0


def contribute_channel(
    *,
    ritual: Ritual,
    contributor_sheet: CharacterSheet,
    amount: int,
    session: RitualSession | None = None,
) -> RitualAnimaContribution:
    """Spend the contributor's own anima into the pool (the Gifted route)."""
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    if amount <= 0:
        msg = "You must channel at least a single point of anima."
        raise RitualPoolError(msg)
    anima = _anima_or_raise(contributor_sheet)
    contributed = min(amount, anima.current + anima.glut)
    if contributed <= 0:
        msg = "You have no anima left to channel."
        raise RitualPoolError(msg)
    with transaction.atomic():
        deduct_anima(contributor_sheet.character, contributed, lethal=False)
        return _record(
            session, ritual, contributor_sheet, AnimaContributionKind.CHANNEL, contributed
        )


def contribute_prick(
    *,
    ritual: Ritual,
    contributor_sheet: CharacterSheet,
    session: RitualSession | None = None,
) -> RitualAnimaContribution:
    """A drop of blood: 1 anima, trivial damage. How anyone joins a folk rite."""
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415
    from world.vitals.services import apply_clamped_chronic_damage  # noqa: PLC0415

    anima = _anima_or_raise(contributor_sheet)
    if anima.current + anima.glut < PRICK_ANIMA:
        msg = "There is not a drop of anima left in you to give."
        raise RitualPoolError(msg)
    with transaction.atomic():
        deduct_anima(contributor_sheet.character, PRICK_ANIMA, lethal=False)
        apply_clamped_chronic_damage(contributor_sheet, PRICK_DAMAGE)
        _apply_contributor_fatigue(contributor_sheet, PRICK_ANIMA)
        return _record(session, ritual, contributor_sheet, AnimaContributionKind.PRICK, PRICK_ANIMA)


def contribute_gash(
    *,
    ritual: Ritual,
    contributor_sheet: CharacterSheet,
    session: RitualSession | None = None,
) -> RitualAnimaContribution:
    """A serious bleed: ``(1d6+1) x level`` anima, a real wound, real fatigue."""
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415
    from world.vitals.services import apply_clamped_chronic_damage  # noqa: PLC0415

    anima = _anima_or_raise(contributor_sheet)
    rolled = _roll_gash(_contributor_level(contributor_sheet))
    contributed = min(rolled, anima.current + anima.glut)
    if contributed <= 0:
        msg = "There is no anima left in your blood to give."
        raise RitualPoolError(msg)
    with transaction.atomic():
        deduct_anima(contributor_sheet.character, contributed, lethal=False)
        apply_clamped_chronic_damage(contributor_sheet, contributed)
        _apply_contributor_fatigue(contributor_sheet, contributed)
        return _record(session, ritual, contributor_sheet, AnimaContributionKind.GASH, contributed)


def contribute_sacrifice(  # noqa: PLR0913 — commit seam mirrors feed_anima's surface
    *,
    ritual: Ritual,
    sacrificer_sheet: CharacterSheet,
    victim_sheet: CharacterSheet,
    lethal: bool = False,
    session: RitualSession | None = None,
    scene: Scene | None = None,
) -> RitualAnimaContribution:
    """Drain a victim into the pool; a killing drain yields the death harvest.

    Consent/authorization is the caller's concern — this is the commit seam,
    mirroring ``feed_anima``. ``lethal=True`` requests the kill; the same guards
    feeding uses apply (PC victims and story-protected NPCs never die of it), and
    a refused kill falls back to a survivable full drain. A completed kill fires
    the murder taint at the sacrificer and mints the crime-tagged deed.
    """
    from world.magic.services.feeding import (  # noqa: PLC0415
        MURDER_TAINT_ACT,
        _maybe_kill_npc_victim,
        grant_blood_taint,
    )

    victim_anima = _anima_or_none(victim_sheet)
    if victim_anima is None:
        msg = "The victim has no anima to take."
        raise RitualPoolError(msg)
    with transaction.atomic():
        take = victim_anima.current
        victim_anima.current = 0
        victim_anima.save(update_fields=["current"])
        _apply_contributor_fatigue(victim_sheet, take)

        was_lethal = False
        if lethal:
            was_lethal = _maybe_kill_npc_victim(sacrificer_sheet, victim_sheet, scene)

        amount = take
        if was_lethal:
            config = AnimaConfig.get_singleton()
            amount = config.death_harvest_multiplier * victim_anima.maximum
            grant_blood_taint(sacrificer_sheet, MURDER_TAINT_ACT)

        if amount <= 0:
            msg = "The victim has nothing left to give."
            raise RitualPoolError(msg)
        return _record(
            session,
            ritual,
            sacrificer_sheet,
            AnimaContributionKind.SACRIFICE,
            amount,
            victim=victim_sheet,
            was_lethal=was_lethal,
        )


@dataclass(frozen=True)
class PoolGateResult:
    """Outcome of resolving a ritual's pool against its anima requirement."""

    proceeded: bool
    spectacular: bool
    deficit: int
    message: str


def resolve_pool_gate(
    *,
    ritual: Ritual,
    performer_sheet: CharacterSheet,
    pool: int,
) -> PoolGateResult:
    """Gate a ritual performance on its filled pool (#3001).

    - requirement 0 (folk rite): proceed.
    - pool >= 2x requirement: proceed, spectacular tier unlocked.
    - pool >= requirement: proceed as authored.
    - underfilled: roll the ritual's check with a deficit-scaled difficulty
      bump (PLACEHOLDER: +ceil(3 x deficit/requirement)); failure fizzles.
      A deficit with no ``RitualCheckConfig`` to roll fails closed.
    """
    requirement = ritual.anima_requirement
    if requirement <= 0:
        return PoolGateResult(True, False, 0, "")
    if pool >= 2 * requirement:
        return PoolGateResult(True, True, 0, "The pool overflows with power.")
    if pool >= requirement:
        return PoolGateResult(True, False, 0, "")

    deficit = requirement - pool
    config = ritual.check_config_or_none
    if config is None or config.check_type is None:
        return PoolGateResult(
            False,
            False,
            deficit,
            "The rite gutters and dies — the pool never held enough anima.",
        )

    from world.checks.services import perform_check  # noqa: PLC0415

    difficulty_bump = -(-3 * deficit // requirement)  # ceil; PLACEHOLDER scaling
    result = perform_check(
        performer_sheet.character,
        config.check_type,
        config.target_difficulty + difficulty_bump,
    )
    if result.success_level > 0:
        return PoolGateResult(True, False, deficit, "The rite holds together despite the want.")
    return PoolGateResult(
        False,
        False,
        deficit,
        "The rite gutters and dies — the pool never held enough anima.",
    )


def _roll_gash(level: int) -> int:
    """(1d6+1) x level — higher-level blood is simply more potent."""
    return (random.randint(1, GASH_DIE_SIZE) + GASH_DIE_BONUS) * max(1, level)  # noqa: S311 # NOSONAR game RNG, not crypto


def _contributor_level(sheet: CharacterSheet) -> int:
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    class_level = primary_class_level(sheet.character)
    return class_level.level if class_level is not None else 0


def _apply_contributor_fatigue(sheet: CharacterSheet, amount: int) -> int:
    """Anima loss always fatigues (#3001 ruling), through the authored cast ratios."""
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.fatigue.services import apply_technique_fatigue  # noqa: PLC0415

    if amount <= 0:
        return 0
    return apply_technique_fatigue(sheet, ActionCategory.PHYSICAL, amount, 0)


def _anima_or_none(sheet: CharacterSheet) -> CharacterAnima | None:
    if sheet is None:
        return None
    return sheet.anima_or_none


def _anima_or_raise(sheet: CharacterSheet) -> CharacterAnima:
    anima = _anima_or_none(sheet)
    if anima is None:
        msg = "You have no anima to draw on."
        raise RitualPoolError(msg)
    return anima


def _record(  # noqa: PLR0913 — one internal row-writer for all four routes
    session: RitualSession | None,
    ritual: Ritual,
    contributor: CharacterSheet,
    kind: str,
    amount: int,
    *,
    victim: CharacterSheet | None = None,
    was_lethal: bool = False,
) -> RitualAnimaContribution:
    return RitualAnimaContribution.objects.create(
        session=session,
        ritual=ritual,
        contributor=contributor,
        kind=kind,
        amount=amount,
        victim=victim,
        was_lethal=was_lethal,
    )
