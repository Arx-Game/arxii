"""Burning resonance as a Strain option (#4736, #4672 decisions 14-15).

A character who strains while pulling a thread may also burn resonance from that
thread's resonance. The burn rides the pull: it is declared on
``CastPullDeclaration.burn``, debited with the pull under the same lock in
``spend_resonance_for_pull`` and audited on ``CombatPull.resonance_burned``.

``resolve_resonance_burn`` decides how much of a request is reached:

1. The ceiling is ``floor(runtime intensity x StrainConfig.burn_per_intensity)``; the
   request is capped by it and by the balance left once the pull's own cost is paid.
2. A strain check (``StrainConfig.strain_check_type`` with the ``PUSHING_HARD`` skill
   terms) selects an outcome tier, whose authored ``StrainBurnReach.reach_percent`` of
   the capped request is what she reaches. Only the reached amount is debited.
3. Reached points become strain units at the burned resonance's
   ``Affinity.burn_value``. An Abyssal caster burning Celestial or Primal resonance
   makes a hasty fall: the points are first converted at the Fall pair rate
   (``conversion_pair(source, abyssal).conversion_multiplier``) and valued as Abyssal.

The strain units join the anima strain before the one diminishing curve
(``strain_to_intensity``) in ``use_technique``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import MagicActivity
from world.magic.exceptions import AffinityNotConfigured, ResonanceBurnUnavailable
from world.magic.models.affinity import Affinity
from world.magic.models.aura import CharacterResonance
from world.magic.services.acting_aura import acting_aura
from world.magic.types.burn import BurnPreview, BurnValuation, ResonanceBurnResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import StrainConfig
    from world.covenants.perks.context import SituationContext
    from world.magic.models import Resonance, Technique
    from world.traits.models import CheckOutcome

_PERCENT = 100


def burn_ceiling(runtime_intensity: int, config: StrainConfig) -> int:
    """The most resonance a cast at ``runtime_intensity`` may burn (floored)."""
    return int(Decimal(max(runtime_intensity, 0)) * config.burn_per_intensity)


def _caster_affinity(sheet: CharacterSheet) -> Affinity | None:
    """The caster's affinity: her acting aura's dominant affinity, or None."""
    aura = acting_aura(sheet)
    return aura.dominant_affinity if aura is not None else None


def _hasty_fall_affinity(sheet: CharacterSheet, resonance: Resonance) -> Affinity | None:
    """The Abyssal affinity when burning ``resonance`` is a hasty fall, else None.

    A hasty fall is an Abyssal caster (by her acting aura's dominant affinity) burning
    resonance of any other affinity.
    """
    caster_affinity = _caster_affinity(sheet)
    if caster_affinity is None:
        return None
    try:
        abyssal = Affinity.objects.get_abyssal_affinity()
    except AffinityNotConfigured:
        return None
    if caster_affinity.pk != abyssal.pk or resonance.affinity_id == abyssal.pk:
        return None
    return abyssal


def _burn_rate(sheet: CharacterSheet, resonance: Resonance) -> tuple[Decimal, Decimal, bool]:
    """``(conversion, burn_value, hasty_fall)`` for one point of ``resonance``.

    Raises:
        ConversionMappingError: A hasty fall with no Fall pair authored.
    """
    abyssal = _hasty_fall_affinity(sheet, resonance)
    if abyssal is None:
        return Decimal(1), resonance.affinity.burn_value, False
    from world.magic.services.conversion import conversion_pair  # noqa: PLC0415

    pair = conversion_pair(resonance.affinity, abyssal)
    return pair.conversion_multiplier, abyssal.burn_value, True


def value_burn(sheet: CharacterSheet, resonance: Resonance, points: int) -> BurnValuation:
    """What ``points`` of burned ``resonance`` are worth to ``sheet``'s caster.

    Raises:
        ConversionMappingError: A hasty fall with no Fall pair authored.
    """
    conversion, burn_value, hasty_fall = _burn_rate(sheet, resonance)
    valued_points = int(Decimal(points) * conversion)
    return BurnValuation(
        points=points,
        valued_points=valued_points,
        strain_units=int(Decimal(valued_points) * burn_value),
        hasty_fall=hasty_fall,
    )


def _reach_percent(outcome: CheckOutcome | None) -> int:
    """The authored reach for ``outcome``; 0 when the tier has no row (a probe lists it)."""
    from world.combat.models import StrainBurnReach  # noqa: PLC0415

    if outcome is None:
        return 0
    row = StrainBurnReach.objects.filter(outcome_tier=outcome).first()
    return row.reach_percent if row is not None else 0


def _available_balance(sheet: CharacterSheet, resonance: Resonance, pull_cost: int) -> int:
    """The balance left for burning once the pull's own cost is paid (unlocked read)."""
    row = CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance).first()
    balance = row.balance if row is not None else 0
    return max(balance - pull_cost, 0)


def resolve_resonance_burn(  # noqa: PLR0913 - one burn request and the action it rides
    *,
    sheet: CharacterSheet,
    resonance: Resonance,
    requested: int,
    runtime_intensity: int,
    pull_cost: int,
    situation_ctx: SituationContext | None = None,
) -> ResonanceBurnResult:
    """Cap, roll and value a burn request. Debits nothing.

    The caller passes ``result.reached`` to ``spend_resonance_for_pull``, which debits
    it with the pull under the same lock and refuses if the balance no longer covers it.

    Raises:
        ResonanceBurnUnavailable: No strain check type is designated.
        ConversionMappingError: A hasty fall with no Fall pair authored.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.combat.services.encounter.config import get_strain_config  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    config = get_strain_config()
    if config.strain_check_type_id is None:
        raise ResonanceBurnUnavailable
    # Refuse a hasty fall with no Fall pair before anything is rolled.
    _burn_rate(sheet, resonance)

    ceiling = burn_ceiling(runtime_intensity, config)
    capped = max(min(requested, ceiling, _available_balance(sheet, resonance, pull_cost)), 0)
    check_result = None
    reach_percent = 0
    if capped > 0:
        check_result = perform_check_with_modifiers(
            sheet.character,
            config.strain_check_type,
            target_difficulty=config.strain_check_difficulty,
            situation_ctx=situation_ctx,
            extra_traits=activity_skill_terms(MagicActivity.PUSHING_HARD),
        )
        reach_percent = _reach_percent(check_result.outcome)
    reached = capped * reach_percent // _PERCENT
    return ResonanceBurnResult(
        resonance=resonance,
        requested=requested,
        ceiling=ceiling,
        capped=capped,
        reach_percent=reach_percent,
        reached=reached,
        valuation=value_burn(sheet, resonance, reached),
        check_result=check_result,
    )


def burn_message(result: ResonanceBurnResult) -> str:
    """The one system line that tells the caster what she burned.

    A burn that reached nothing says why: the ceiling at her intensity is 0, she has no
    balance left once the pull is paid, or her strain check reached none of it.
    """
    name = result.resonance.name
    if result.reached == 0 and result.requested > 0:
        if result.ceiling == 0:
            reason = "your burn ceiling is 0 at this intensity"
        elif result.capped == 0:
            reason = f"you have no {name} resonance left once the pull is paid"
        else:
            reason = "your strain check reached none of it"
        return f"You burn none of the {result.requested} {name} resonance you asked for: {reason}."
    line = f"You burn {result.reached} of {result.requested} {name} resonance"
    if result.hasty_fall and result.reached > 0:
        return f"{line}; it falls at the pair rate to {result.valuation.valued_points}."
    return f"{line}."


def announce_burn(character: ObjectDB, result: ResonanceBurnResult) -> None:
    """Tell the caster what she burned once the debit commits.

    Sent on commit, so a declaration or cast that rolls back tells her nothing.
    """
    message = burn_message(result)
    transaction.on_commit(lambda: character.msg(message))


def _intensity_tier_name(runtime_intensity: int) -> str | None:
    """The name of the highest ``IntensityTier`` she has reached, or None below them all."""
    from world.magic.models import IntensityTier  # noqa: PLC0415

    reached = [t for t in IntensityTier.objects.cached_all() if t.threshold <= runtime_intensity]
    if not reached:
        return None
    return max(reached, key=lambda t: t.threshold).name


def _corruption_affinity(resonance: Resonance, hasty_fall_into: Affinity | None) -> Affinity | None:
    """The affinity whose corruption a burn of ``resonance`` leaves, or None.

    A hasty fall leaves the Abyssal corruption it fell into; a raw burn leaves its own
    affinity's corruption, unless that affinity never corrupts (coefficient 0).
    """
    if hasty_fall_into is not None:
        return hasty_fall_into
    if resonance.affinity.corruption_coefficient > 0:
        return resonance.affinity
    return None


def preview_burn(
    sheet: CharacterSheet,
    resonance: Resonance,
    technique: Technique,
    pull_cost: int,
) -> BurnPreview:
    """The burn numbers and labels the pull preview shows for ``technique``."""
    from world.combat.services.encounter.config import get_strain_config  # noqa: PLC0415
    from world.magic.exceptions import ConversionMappingError  # noqa: PLC0415
    from world.magic.services.techniques import get_runtime_technique_stats  # noqa: PLC0415

    config = get_strain_config()
    stats = get_runtime_technique_stats(technique, sheet.character)
    ceiling = min(
        burn_ceiling(stats.intensity, config),
        _available_balance(sheet, resonance, pull_cost),
    )
    caster_affinity = _caster_affinity(sheet)
    off_affinity = caster_affinity is not None and caster_affinity.pk != resonance.affinity_id
    hasty_fall_into = _hasty_fall_affinity(sheet, resonance)
    corruption_affinity = _corruption_affinity(resonance, hasty_fall_into)
    corruption_affinity_name = corruption_affinity.name if corruption_affinity is not None else None
    ceiling_tier_name = _intensity_tier_name(stats.intensity)
    try:
        conversion, burn_value, hasty_fall = _burn_rate(sheet, resonance)
    except ConversionMappingError:
        return BurnPreview(
            ceiling=0,
            strain_units_per_point=Decimal(0),
            hasty_fall=True,
            available=False,
            resonance_name=resonance.name,
            off_affinity=off_affinity,
            corruption_affinity_name=corruption_affinity_name,
            ceiling_tier_name=ceiling_tier_name,
        )
    return BurnPreview(
        ceiling=ceiling,
        strain_units_per_point=conversion * burn_value,
        hasty_fall=hasty_fall,
        available=config.strain_check_type_id is not None,
        resonance_name=resonance.name,
        off_affinity=off_affinity,
        corruption_affinity_name=corruption_affinity_name,
        ceiling_tier_name=ceiling_tier_name,
    )
