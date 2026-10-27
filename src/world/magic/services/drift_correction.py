"""The drift correction rite: preview, focus, check and conversion (#4733, slice 4 of #4672).

A character holding an open ``DriftConversionOffer`` may perform the configured rite to
convert drift (resonance held off their aura) toward a resonance the offer has a cap for.
The rite consumes a qualifying offering, rolls the configured check with a focus bonus, and
converts the share of the requested amount that the outcome tier's
``DriftCorrectionOutcomeShare`` names, at the authored pair rate. Everything runs in one
transaction: a refusal or a raise consumes and moves nothing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max

from world.checks.services import perform_check_with_modifiers
from world.magic.constants import GainSource
from world.magic.exceptions import (
    ConversionMappingError,
    DriftConversionInvalidError,
    DriftCorrectionNotConfiguredError,
    DriftOfferNotFoundError,
)
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
    DriftCorrectionOutcomeShare,
)
from world.magic.models.resonance_environment import AffinityInteraction
from world.magic.services.conversion import conversion_pair, convert_resonance_amount
from world.magic.services.drift import convertible_drift, get_drift_correction_config
from world.magic.services.ritual_components import resolve_and_consume_ritual_components
from world.magic.services.touchstone import touchstone_cast_bonus
from world.magic.types.drift import (
    DriftConversionPreview,
    DriftCorrectionResult,
    DriftSourceOption,
)
from world.mechanics.services import equipment_walk_total

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models.affinity import Resonance


def focus_bonus(sheet: CharacterSheet, target: Resonance) -> int:
    """What the character's worn focus adds to the rite's check toward ``target``.

    The equipment walk total on the target's modifier target (0 when it has none) plus
    the touchstone bonus for that resonance (0 when no tied touchstone is worn).
    """
    try:
        modifier_target = target.modifier_target
    except ObjectDoesNotExist:
        modifier_target = None
    walk = 0 if modifier_target is None else equipment_walk_total(sheet.character, modifier_target)
    return walk + touchstone_cast_bonus(sheet, target)


def _cap_for(offer: DriftConversionOffer, target: Resonance) -> DriftConversionCap | None:
    return DriftConversionCap.objects.filter(offer=offer, target_resonance=target).first()


def _projected(amount: int, multiplier: Decimal) -> int:
    """The pair-rate output of converting ``amount``, floored at 1 like the conversion."""
    if amount <= 0:
        return 0
    return max(1, int(Decimal(amount) * multiplier))


def preview_conversion(offer: DriftConversionOffer, target: Resonance) -> DriftConversionPreview:
    """What the character could convert toward ``target`` under ``offer``, at a full share.

    Sources are the character's ``convertible_drift`` toward the target. ``cap_remaining``
    is 0 when the offer holds no cap toward the target.
    """
    sheet = offer.character_sheet
    cap = _cap_for(offer, target)
    cap_remaining = cap.cap if cap is not None else 0
    sources = []
    for row in convertible_drift(sheet, target):
        pair = conversion_pair(row.resonance.affinity, target.affinity)
        max_amount = min(cap_remaining, row.balance)
        sources.append(
            DriftSourceOption(
                resonance_id=row.resonance_id,
                resonance_name=row.resonance.name,
                balance=row.balance,
                multiplier=pair.conversion_multiplier,
                conversion_type=pair.conversion_type,
                max_amount=max_amount,
                projected_output=_projected(max_amount, pair.conversion_multiplier),
            )
        )
    return DriftConversionPreview(
        target_resonance_id=target.pk,
        cap_remaining=cap_remaining,
        sources=tuple(sources),
        focus_bonus=focus_bonus(sheet, target),
    )


def max_yield_per_earned_point(config: DriftCorrectionConfig) -> Decimal:
    """The most target resonance one point of deed gain can ever yield through the rite.

    ``cap_percent / 100 x the largest authored pair multiplier x the largest converted
    share``. Tuning keeps this below 1, so correcting drift never out-earns the deed itself.
    """
    max_multiplier = AffinityInteraction.objects.filter(
        conversion_multiplier__isnull=False
    ).aggregate(top=Max("conversion_multiplier"))["top"] or Decimal(0)
    max_share = DriftCorrectionOutcomeShare.objects.aggregate(top=Max("converted_share"))[
        "top"
    ] or Decimal(0)
    return Decimal(config.cap_percent) / Decimal(100) * max_multiplier * max_share


def _locked_offer(offer: DriftConversionOffer) -> DriftConversionOffer:
    # A filter, not get(): the identity map would answer get() without the database or lock.
    locked = list(DriftConversionOffer.objects.select_for_update().filter(pk=offer.pk))
    if not locked:
        raise DriftOfferNotFoundError
    scene = locked[0].scene
    if not scene.is_active or scene.is_finished:
        raise DriftOfferNotFoundError
    return locked[0]


def _validated_source(
    sheet: CharacterSheet, source: Resonance, target: Resonance, amount: int, cap_value: int
) -> AffinityInteraction:
    """Check the requested amount and source; return the authored pair."""
    if amount <= 0:
        msg = "Convert at least 1."
        raise DriftConversionInvalidError(msg)
    if amount > cap_value:
        msg = f"You may convert at most {cap_value} toward that resonance."
        raise DriftConversionInvalidError(msg)
    try:
        pair = conversion_pair(source.affinity, target.affinity)
    except ConversionMappingError as exc:
        msg = "That resonance cannot be converted toward that one."
        raise DriftConversionInvalidError(msg) from exc
    if source.pk not in {row.resonance_id for row in convertible_drift(sheet, target)}:
        msg = "That resonance is not drift you can convert."
        raise DriftConversionInvalidError(msg)
    balance = (
        CharacterResonance.objects.filter(character_sheet=sheet, resonance=source)
        .values_list("balance", flat=True)
        .first()
        or 0
    )
    if amount > balance:
        msg = f"You hold only {balance} of that resonance."
        raise DriftConversionInvalidError(msg)
    return pair


@transaction.atomic
def perform_drift_correction_rite(
    offer: DriftConversionOffer,
    *,
    source_resonance: Resonance,
    target_resonance: Resonance,
    amount: int,
    components: list[ItemInstance],
) -> DriftCorrectionResult:
    """Perform the drift correction rite under ``offer``.

    Locks the offer, refuses a lapsed or unconfigured rite and an invalid request, consumes
    the offering, rolls the configured check with ``focus_bonus`` as extra modifiers, then
    converts ``floor(amount x share)`` of the source at the pair rate, granting it as
    ``DRIFT_CORRECTION``. The cap shrinks by what converted; an exhausted cap row is
    deleted, and the offer with it once no cap is left. A tier with no share still consumes
    the offering and moves nothing.

    Raises:
        DriftOfferNotFoundError: The offer is gone, its scene finished, or no cap targets
            ``target_resonance``.
        DriftCorrectionNotConfiguredError: Rite, check type or the rolled tier's share is
            unauthored.
        DriftConversionInvalidError: Bad amount, source, or unauthored pair.
        RitualComponentError: The offering does not satisfy the rite.
    """
    offer = _locked_offer(offer)
    sheet = offer.character_sheet
    config = get_drift_correction_config()
    if config.rite_id is None or config.check_type_id is None:
        raise DriftCorrectionNotConfiguredError
    cap = _cap_for(offer, target_resonance)
    if cap is None:
        raise DriftOfferNotFoundError
    # Read the cap from the database, not the shared instance: the lock above serializes
    # writers, and the identity map would not refresh a cached row's value.
    cap_value = DriftConversionCap.objects.filter(pk=cap.pk).values_list("cap", flat=True)[0]
    pair = _validated_source(sheet, source_resonance, target_resonance, amount, cap_value)

    resolve_and_consume_ritual_components(
        ritual=config.rite,
        components=components,
        performer_sheet=sheet,
        resonance_context=target_resonance,
    )
    bonus = focus_bonus(sheet, target_resonance)
    check = perform_check_with_modifiers(
        sheet.character,
        config.check_type,
        config.check_difficulty,
        extra_modifiers=bonus,
    )
    outcome = check.outcome
    share_row = (
        DriftCorrectionOutcomeShare.objects.filter(outcome_tier=outcome).first()
        if outcome is not None
        else None
    )
    if share_row is None:
        raise DriftCorrectionNotConfiguredError

    converted = int(Decimal(amount) * share_row.converted_share)
    granted = 0
    if converted > 0:
        granted, _ = convert_resonance_amount(
            sheet,
            source_resonance=source_resonance,
            target_resonance=target_resonance,
            amount=converted,
            multiplier=pair.conversion_multiplier,
            gain_source=GainSource.DRIFT_CORRECTION,
        )
        remaining = cap_value - converted
        if remaining > 0:
            cap.cap = remaining
            cap.save(update_fields=["cap"])
        else:
            cap.delete()
            if not DriftConversionCap.objects.filter(offer=offer).exists():
                offer.delete()

    return DriftCorrectionResult(
        source_resonance_id=source_resonance.pk,
        target_resonance_id=target_resonance.pk,
        attempted_amount=amount,
        converted_amount=converted,
        granted_amount=granted,
        outcome_name=outcome.name,
        success_level=outcome.success_level,
        conversion_type=pair.conversion_type,
        focus_bonus=bonus,
    )
