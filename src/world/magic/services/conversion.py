"""Resonance conversion service for Fall / Redemption (#1583).

Shared conversion engine for both the extended Rite of Atonement (partial,
lossy) and the full Fall/Redemption ceremony (full, asymmetric).

Key invariants:
- ``lifetime_earned`` is *transferred* (not decremented) so that
  ``recompute_aura`` — which sums ``lifetime_earned`` by affinity — shifts
  correctly. The total lifetime_earned across both resonances is preserved
  (modulo the multiplier). See the spec's "Monotonicity invariant — revised
  after reviewer finding" section.
- ``balance`` is zeroed (full) or reduced (partial) on the source resonance.
- ``Thread.resonance`` FK is re-anchored (full conversion only).
- ``ResonanceGrant`` audit rows are written for the target-side grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import GainSource
from world.magic.exceptions import ConversionMappingError
from world.magic.models.aura import CharacterResonance
from world.magic.models.fall_redemption import (
    FallRedemptionConfig,
    ResonanceConversion,
)
from world.magic.services.resonance import grant_resonance

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Resonance


@dataclass(frozen=True)
class ConvertedResonance:
    """Per-resonance details of a single conversion."""

    source_resonance_id: int
    target_resonance_id: int
    balance_before: int
    balance_after: int  # 0 for full, reduced for partial
    lifetime_earned_before: int
    lifetime_earned_after: int  # 0 for full, reduced for partial
    granted_balance: int  # amount granted to target (after multiplier)
    granted_lifetime: int  # lifetime_earned transferred to target


@dataclass(frozen=True)
class ConversionResult:
    """Frozen result of a resonance conversion."""

    character_sheet_id: int
    converted_resonances: tuple[ConvertedResonance, ...]
    threads_reanchored: int
    multiplier: Decimal


def get_fall_redemption_config() -> FallRedemptionConfig:
    """Lazy-create the FallRedemptionConfig singleton at pk=1."""
    config = FallRedemptionConfig.objects.cached_singleton()
    if config is None:
        config, _ = FallRedemptionConfig.objects.get_or_create(pk=1)
    return config


def _resolve_target_resonance(
    source_resonance: Resonance,
    target_affinity: str,
) -> Resonance:
    """Look up the target resonance via ResonanceConversion mapping.

    Raises ConversionMappingError if no row exists.
    """
    try:
        mapping = ResonanceConversion.objects.get(
            source_resonance=source_resonance,
            target_affinity=target_affinity,
        )
    except ResonanceConversion.DoesNotExist as exc:
        msg = (
            f"No ResonanceConversion mapping for source_resonance="
            f"{source_resonance.name} → target_affinity={target_affinity}."
        )
        raise ConversionMappingError(msg) from exc
    return mapping.target_resonance


def _get_multiplier(config: FallRedemptionConfig, from_affinity: str, to_affinity: str) -> Decimal:
    """Return the conversion multiplier for a given path."""
    key = f"{from_affinity}_to_{to_affinity}_multiplier"
    return getattr(config, key)


@transaction.atomic
def _convert_partial(
    cr: CharacterResonance,
    character_sheet: CharacterSheet,
    target_resonance: Resonance,
    multiplier: Decimal,
    penance_amount: int | None,
) -> tuple[int, int] | None:
    """Partial conversion: convert a portion of balance back (Atonement)."""
    amount_to_convert = min(
        penance_amount if penance_amount is not None else cr.balance,
        cr.balance,
    )
    if amount_to_convert <= 0:
        return None

    if cr.balance > 0:
        lifetime_fraction = int(
            (Decimal(amount_to_convert) / Decimal(cr.balance)) * Decimal(cr.lifetime_earned)
        )
    else:
        lifetime_fraction = 0

    granted_balance = int(Decimal(amount_to_convert) * multiplier)
    granted_lifetime = lifetime_fraction

    cr.balance -= amount_to_convert
    cr.lifetime_earned -= lifetime_fraction
    cr.save(update_fields=["balance", "lifetime_earned"])

    if granted_balance > 0:
        grant_resonance(
            character_sheet,
            target_resonance,
            granted_balance,
            source=GainSource.PENANCE,
        )
        # grant_resonance added granted_balance to lifetime_earned;
        # we want the transferred fraction instead.
        target_cr = CharacterResonance.objects.get(
            character_sheet=character_sheet,
            resonance=target_resonance,
        )
        if granted_lifetime != granted_balance:
            target_cr.lifetime_earned += granted_lifetime - granted_balance
            target_cr.save(update_fields=["lifetime_earned"])

    return granted_balance, granted_lifetime


def _convert_full(
    cr: CharacterResonance,
    character_sheet: CharacterSheet,
    target_resonance: Resonance,
    multiplier: Decimal,
) -> tuple[int, int] | None:
    """Full conversion: convert everything (Fall/Redemption)."""
    from world.magic.models.grant import ResonanceGrant  # noqa: PLC0415

    granted_balance = int(Decimal(cr.balance) * multiplier)
    granted_lifetime = int(Decimal(cr.lifetime_earned) * multiplier)

    cr.balance = 0
    cr.lifetime_earned = 0
    cr.save(update_fields=["balance", "lifetime_earned"])

    target_cr, _ = CharacterResonance.objects.get_or_create(
        character_sheet=character_sheet,
        resonance=target_resonance,
        defaults={"balance": 0, "lifetime_earned": 0},
    )
    target_cr.balance += granted_balance
    target_cr.lifetime_earned += granted_lifetime
    target_cr.save(update_fields=["balance", "lifetime_earned"])

    ResonanceGrant.objects.create(
        character_sheet=character_sheet,
        resonance=target_resonance,
        amount=granted_balance,
        source=GainSource.FALL_CONVERSION,
    )

    return granted_balance, granted_lifetime


def convert_resonance(  # noqa: PLR0913
    character_sheet: CharacterSheet,
    *,
    source_affinity: str,
    target_affinity: str,
    multiplier: Decimal,
    partial: bool = False,
    penance_amount: int | None = None,
) -> ConversionResult:
    """Convert resonance balances and lifetime_earned between affinities.

    For each CharacterResonance row whose resonance.affinity.name.lower()
    matches source_affinity:

    1. Look up the target resonance via ResonanceConversion mapping.
    2. Apply multiplier to balance (gain or loss).
    3. Transfer a proportional fraction of lifetime_earned to the target.
    4. Zero the source balance (full) or reduce by penance_amount (partial).
    5. Grant the converted amount to the target via grant_resonance.
    6. Re-anchor all Threads on the source resonance to the target resonance
       (full conversion only).

    Args:
        character_sheet: The character undergoing conversion.
        source_affinity: The affinity being converted away from.
        target_affinity: The destination affinity.
        multiplier: >1.0 for Fall (gain), <1.0 for Redemption/Atonement (loss).
        partial: True for Atonement (only converts non-native → Celestial,
            does not touch threads).
        penance_amount: For partial: how much balance to convert. None = all.

    Returns:
        ConversionResult with per-resonance details.
    """
    # Find all CharacterResonance rows matching the source affinity
    source_rows = list(
        CharacterResonance.objects.filter(
            character_sheet=character_sheet,
            resonance__affinity__name__iexact=source_affinity,
        ).select_related("resonance__affinity")
    )

    converted: list[ConvertedResonance] = []

    for cr in source_rows:
        source_resonance = cr.resonance
        target_resonance = _resolve_target_resonance(source_resonance, target_affinity)

        balance_before = cr.balance
        lifetime_before = cr.lifetime_earned

        if partial:
            conv = _convert_partial(
                cr, character_sheet, target_resonance, multiplier, penance_amount
            )
        else:
            conv = _convert_full(cr, character_sheet, target_resonance, multiplier)

        if conv is not None:
            converted.append(
                ConvertedResonance(
                    source_resonance_id=source_resonance.pk,
                    target_resonance_id=target_resonance.pk,
                    balance_before=balance_before,
                    balance_after=cr.balance,
                    lifetime_earned_before=lifetime_before,
                    lifetime_earned_after=cr.lifetime_earned,
                    granted_balance=conv[0],
                    granted_lifetime=conv[1],
                )
            )

    # Thread re-anchoring (full conversion only)
    threads_reanchored = 0
    if not partial and converted:
        threads_reanchored = _reanchor_threads(
            character_sheet, converted, multiplier, source_affinity
        )

    # Batch aura recomputation
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415

    recompute_aura(character_sheet)

    return ConversionResult(
        character_sheet_id=character_sheet.pk,
        converted_resonances=tuple(converted),
        threads_reanchored=threads_reanchored,
        multiplier=multiplier,
    )


def _reanchor_threads(
    character_sheet: CharacterSheet,
    converted: list[ConvertedResonance],
    multiplier: Decimal,
    source_affinity: str,
) -> int:
    """Re-anchor all Threads on source resonances to their target resonances.

    If a target-resonance thread with the same anchor already exists, the
    source thread is retired and its developed_points are merged into the
    existing target thread.
    """
    from world.magic.models import Thread  # noqa: PLC0415

    # Build a mapping: source_resonance_id → target_resonance_id
    resonance_map = {c.source_resonance_id: c.target_resonance_id for c in converted}

    threads = Thread.objects.filter(
        owner=character_sheet,
        resonance__affinity__name__iexact=source_affinity,
        retired_at__isnull=True,
    )

    count = 0
    for thread in threads:
        target_resonance_id = resonance_map.get(thread.resonance_id)
        if target_resonance_id is None:
            continue

        # Scale developed_points by the multiplier
        new_points = max(0, int(Decimal(thread.developed_points) * multiplier))

        # Check for an existing thread on the target resonance with the same anchor
        existing = _find_existing_target_thread(thread, character_sheet, target_resonance_id)
        if existing is not None:
            # Merge: add scaled points to existing thread, retire source
            existing.developed_points += new_points
            existing.save(update_fields=["developed_points"])
            from django.utils import timezone  # noqa: PLC0415

            thread.retired_at = timezone.now()
            thread.save(update_fields=["retired_at"])
        else:
            # Simple re-anchor: change the resonance FK
            thread.resonance_id = target_resonance_id
            thread.developed_points = new_points
            thread.save(update_fields=["resonance", "developed_points"])

        count += 1

    return count


def _find_existing_target_thread(
    source_thread: object,
    character_sheet: CharacterSheet,
    target_resonance_id: int,
) -> object | None:
    """Find an existing non-retired thread on the target resonance with the same anchor.

    Two threads have the same anchor if they share the same target_kind and
    the same typed FK (target_trait, target_technique, etc.).
    """
    from world.magic.models import Thread  # noqa: PLC0415

    kwargs = {
        "owner": character_sheet,
        "resonance_id": target_resonance_id,
        "retired_at__isnull": True,
        "target_kind": source_thread.target_kind,
    }

    # Match on whichever typed FK is set
    for fk_field in (
        "target_trait",
        "target_technique",
        "target_facet",
        "target_relationship_track",
        "target_capstone",
        "target_covenant_role",
        "target_gift",
        "target_mantle",
        "target_sanctum_details",
    ):
        fk_value = getattr(source_thread, fk_field, None)
        if fk_value is not None:
            kwargs[fk_field] = fk_value

    return Thread.objects.filter(**kwargs).exclude(pk=source_thread.pk).first()
