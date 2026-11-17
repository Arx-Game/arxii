"""Settling the Mire at the rite of settling (#5177).

A Sineater carries corruption for each of their Sinners as ``MireHolding`` rows. They settle
what they carry for one Sinner by writing a burden reflection and choosing Absolve, Condemn
or Succumb; the rite carries it out at its share ``s``. For each resonance held from that
Sinner:

| Choice          | Effect at share s                                                       |
| Absolve/Condemn | ``cleared = floor(held x s)`` leaves the Mire (no resonance granted back);   |
|                 | the Sineater earns ``purify_reward_percent`` of it in their own thread's    |
|                 | resonance; the tie moves toward affection (Absolve) or conflict (Condemn)   |
| Succumb         | ``taken = floor(held x s)`` leaves the Mire and becomes the Sinner's        |
|                 | resonance in the Sineater's own aura (SUCCUMBED, a deed); the Sinner earns  |
|                 | ``succumb_bonus_percent`` of it plus ``jackpot_percent`` of what was        |
|                 | purified for them since the last payout; both gauges move                    |

``apply_fall`` runs once per rite after everything else: when the Sineater's aura is now
predominantly Abyssal, every Sinner they succumbed to since their last fall is paid, with extra
for the one whose Mire they succumbed to last. Nothing here sends a message: the lines for the
Sineater are returned for the rite's result, and the Sinners' are ``RiteNotice`` rows the action
sends once the rite has committed. A share of 0 moves nothing and pays nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import SoulTetherError
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import MireHolding
from world.magic.services.mire import release_mire
from world.magic.services.resonance import grant_resonance
from world.magic.services.soul_tether import (
    _increment_stat_safe,
    ensure_sineater_thread,
    get_soul_tether_config,
    sineater_has_fallen,
    sinner_thread_resonance,
)
from world.magic.types.drift import RiteNotice
from world.relationships.services import move_gauges

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.reflection import Reflection, SettlingRite
    from world.relationships.models import CharacterRelationship

_NO_RESONANCE_LINE = "You hold no resonance for your side of the bond to channel, so you earn none."
_FALL_LINE = (
    "Your aura is now predominantly Abyssal, and you have fallen: you can carry no one's sins "
    "until it is predominantly something else."
)


@dataclass(frozen=True)
class BurdenOutcome:
    """What one burden reflection did: the line its writer reads, the lines other characters
    are told, and the Mire succumbed to (0 unless the reflection succumbed and took some)."""

    line: str
    notices: tuple[RiteNotice, ...] = ()
    succumbed: int = 0


@dataclass(frozen=True)
class FallOutcome:
    """What a Sineater's fall did: the sentence added to their line, and the Sinners' notices."""

    line: str
    notices: tuple[RiteNotice, ...] = ()


def _name(sheet: CharacterSheet) -> str:
    return sheet.primary_persona.name


def _gauge_steps(points: int, share: Decimal) -> int:
    """``points`` scaled by ``share`` and rounded to the nearest whole step (halves up)."""
    return int((Decimal(points) * share).to_integral_value(rounding=ROUND_HALF_UP))


def _grant(
    sheet: CharacterSheet, resonance: Resonance | None, amount: int, source: GainSource
) -> int:
    """Grant ``amount`` of ``resonance`` under ``source``; nothing to grant, or no resonance,
    grants nothing. Returns the amount granted."""
    if resonance is None or amount <= 0:
        return 0
    grant_resonance(sheet, resonance, amount, source=source)
    return amount


def _held_rows(tether: CharacterRelationship) -> list[MireHolding]:
    """Every holding of this tether (locked), including emptied ones that keep a jackpot."""
    return list(
        MireHolding.objects.select_for_update()
        .select_related("resonance")
        .filter(relationship=tether)
        .order_by("resonance_id")
    )


def _listing(parts: list[tuple[Resonance, int]]) -> str:
    return " and ".join(f"{amount} {resonance.name}" for resonance, amount in parts)


def apply_burden(
    sheet: CharacterSheet, reflection: Reflection, rite: SettlingRite, share: Decimal
) -> BurdenOutcome:
    """Carry out one burden reflection at ``share``: Absolve, Condemn or Succumb."""
    if reflection.choice == ReflectionChoice.SUCCUMB:
        return _succumb(sheet, reflection, rite, share)
    return _purify(sheet, reflection, share)


def _purify(sheet: CharacterSheet, reflection: Reflection, share: Decimal) -> BurdenOutcome:
    tether = reflection.tether
    cfg = get_soul_tether_config()
    absolving = reflection.choice == ReflectionChoice.ABSOLVE
    verb = "absolve" if absolving else "condemn"
    on = f"the Mire you carry for {_name(tether.target)}"
    cleared = 0
    reward = 0
    for holding in _held_rows(tether):
        if holding.amount <= 0:
            continue
        part = release_mire(holding=holding, amount=int(Decimal(holding.amount) * share))
        if part <= 0:
            continue
        cleared += part
        reward += part * cfg.purify_reward_percent // 100
        holding.purified_since_payout += part
        holding.save(update_fields=["purified_since_payout"])
    if cleared == 0:
        return BurdenOutcome(f"You {verb} {on}, but the rite carries none of it through.")
    steps = _gauge_steps(cfg.absolve_affection if absolving else cfg.condemn_conflict, share)
    if steps > 0:
        move_gauges(side=tether, amount=steps if absolving else -steps)
    resonance = _own_thread_resonance(sheet, tether)
    line = f"You {verb} {on}: {cleared} of it clears."
    if resonance is None:
        line = f"{line} {_NO_RESONANCE_LINE}"
    elif _grant(sheet, resonance, reward, GainSource.MIRE_PURIFIED) > 0:
        line = f"{line} Your {resonance.name} grows by {reward}."
    return BurdenOutcome(line)


def _own_thread_resonance(sheet: CharacterSheet, tether: CharacterRelationship) -> Resonance | None:
    """The resonance of the Sineater's own thread on this tether, woven when absent; None when
    the tether is gone or they hold no resonance for a thread to channel."""
    try:
        thread = ensure_sineater_thread(sheet, tether.target)
    except SoulTetherError:
        return None
    return thread.resonance if thread is not None else None


def _succumb(
    sheet: CharacterSheet, reflection: Reflection, rite: SettlingRite, share: Decimal
) -> BurdenOutcome:
    tether = reflection.tether
    sinner = tether.target
    cfg = get_soul_tether_config()
    on = f"the Mire you carry for {_name(sinner)}"
    rows = _held_rows(tether)
    taken_by: list[tuple[Resonance, int]] = []
    bonus = 0
    for holding in rows:
        if holding.amount <= 0:
            continue
        taken = release_mire(holding=holding, amount=int(Decimal(holding.amount) * share))
        if taken <= 0:
            continue
        grant_resonance(
            sheet,
            holding.resonance,
            taken,
            source=GainSource.SUCCUMBED,
            settling_rite=rite,
            reflection=reflection,
        )
        holding.succumbed_since_fall += taken
        holding.save(update_fields=["succumbed_since_fall"])
        taken_by.append((holding.resonance, taken))
        bonus += taken * cfg.succumb_bonus_percent // 100
    total = sum(amount for _, amount in taken_by)
    if total == 0:
        return BurdenOutcome(f"You succumb to {on}, but the rite carries none of it through.")
    # The jackpot is the tether's, however many resonances it is held in: paid once, then reset.
    bonus += sum(row.purified_since_payout for row in rows) * cfg.jackpot_percent // 100
    for row in rows:
        if row.purified_since_payout:
            row.purified_since_payout = 0
            row.save(update_fields=["purified_since_payout"])
    for steps, sign in (
        (_gauge_steps(cfg.succumb_affection, share), 1),
        (_gauge_steps(cfg.succumb_conflict, share), -1),
    ):
        if steps > 0:
            move_gauges(side=tether, amount=sign * steps)
    _increment_stat_safe(sinner, "sineater.succumbed", 1)
    _increment_stat_safe(sinner, "sineater.succumbed_amount", total)
    notices: tuple[RiteNotice, ...] = ()
    sinner_resonance = sinner_thread_resonance(tether)
    if _grant(sinner, sinner_resonance, bonus, GainSource.SUCCUMB_BONUS) > 0:
        notices = (
            RiteNotice(
                sinner,
                f"{_name(sheet)} has succumbed to what they carried for you. "
                f"Your {sinner_resonance.name} grows by {bonus}.",
            ),
        )
    becomes = "become" if len(taken_by) > 1 else "becomes"
    line = f"You succumb to {on}: {_listing(taken_by)} {becomes} part of you."
    return BurdenOutcome(line, notices, succumbed=total)


def apply_fall(sheet: CharacterSheet, last: CharacterRelationship) -> FallOutcome | None:
    """Pay the Sinners when the Sineater has fallen, or None when they have not (or no one is
    owed). ``last`` is the tether of the Mire succumbed to last in this rite.

    Each Sinner with ``succumbed_since_fall`` above 0 earns ``fall_payout_percent`` of it in their
    own thread's resonance; ``last``'s Sinner earns ``fall_breaker_bonus_percent`` more on top.
    Every counter resets, which is what stops a second payout for the same fall. The Sinner's
    ``sineater.broken`` stat rises when they are paid.
    """
    if not sineater_has_fallen(sheet):
        return None
    rows = list(
        MireHolding.objects.select_for_update()
        .select_related("relationship__target")
        .filter(relationship__source=sheet, succumbed_since_fall__gt=0)
        .order_by("relationship_id", "resonance_id")
    )
    if not rows:
        return None
    cfg = get_soul_tether_config()
    totals: dict[int, int] = {}
    tethers: dict[int, CharacterRelationship] = {}
    for row in rows:
        totals[row.relationship_id] = totals.get(row.relationship_id, 0) + row.succumbed_since_fall
        tethers[row.relationship_id] = row.relationship
        row.succumbed_since_fall = 0
        row.save(update_fields=["succumbed_since_fall"])
    notices: list[RiteNotice] = []
    for tether_id, total in totals.items():
        tether = tethers[tether_id]
        payout = total * cfg.fall_payout_percent // 100
        if tether_id == last.pk:
            payout += payout * cfg.fall_breaker_bonus_percent // 100
        resonance = sinner_thread_resonance(tether)
        if _grant(tether.target, resonance, payout, GainSource.SINEATER_FALL) <= 0:
            continue
        _increment_stat_safe(tether.target, "sineater.broken", 1)
        notices.append(
            RiteNotice(
                tether.target,
                f"{_name(sheet)} has fallen to the Abyss. Your {resonance.name} grows by {payout}.",
            )
        )
    return FallOutcome(_FALL_LINE, tuple(notices))
