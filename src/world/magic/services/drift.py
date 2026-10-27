"""Drift holdings and the conversion offer a deed opens (#4733, slice 4 of #4672).

Drift is resonance a character holds that sits off their own aura: any
``CharacterResonance`` with a positive balance whose affinity differs from the aura's
dominant affinity. There is no threshold. A deed (a grant from a ``DEED_GAIN_SOURCES``
source) that grows a resonance of the character's own affinity, made in a live scene by a
character who has convertible drift, opens a ``DriftConversionOffer`` for that scene and
adds to the cap of converting drift toward the resonance the deed grew. The offer lapses
when the scene finishes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.constants import DEED_GAIN_SOURCES
from world.magic.exceptions import ConversionMappingError
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
)
from world.magic.services.conversion import conversion_pair

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Affinity, Resonance
    from world.magic.models.gain import ResonanceGrant
    from world.scenes.models import Scene


def get_drift_correction_config() -> DriftCorrectionConfig:
    """Lazy-create the DriftCorrectionConfig singleton at pk=1."""
    config = DriftCorrectionConfig.objects.cached_singleton()
    if config is None:
        config, _ = DriftCorrectionConfig.objects.get_or_create(pk=1)
    return config


def own_affinity(sheet: CharacterSheet) -> Affinity | None:
    """The affinity the character's aura is mostly made of, or None.

    None when the sheet has no aura yet or the aura holds no shares. Never raises.
    """
    aura = sheet.aura_or_none
    if aura is None or not aura.cached_shares:
        return None
    return aura.dominant_affinity


def drift_holdings(sheet: CharacterSheet) -> list[CharacterResonance]:
    """Resonance held off the aura: positive balance, affinity other than the aura's own.

    Largest balance first. Empty when the character has no own affinity.
    """
    own = own_affinity(sheet)
    if own is None:
        return []
    return list(
        CharacterResonance.objects.filter(character_sheet=sheet, balance__gt=0)
        .exclude(resonance__affinity=own)
        .select_related("resonance__affinity")
        .order_by("-balance")
    )


def _has_conversion(source: Affinity, target: Affinity) -> bool:
    try:
        conversion_pair(source, target)
    except ConversionMappingError:
        return False
    return True


def convertible_drift(sheet: CharacterSheet, target: Resonance) -> list[CharacterResonance]:
    """``drift_holdings`` narrowed to rows with an authored conversion into target's affinity."""
    return [
        row
        for row in drift_holdings(sheet)
        if _has_conversion(row.resonance.affinity, target.affinity)
    ]


def open_or_extend_conversion_offer(grant: ResonanceGrant) -> DriftConversionOffer | None:
    """Open (or extend) the character's conversion offer for the scene a deed grant happened in.

    Returns None, changing nothing, unless all of these hold: the grant is a deed; it grew a
    resonance of the character's own affinity; the character has convertible drift toward
    that resonance; and the character stands in a live scene. A deed made outside a live
    scene opens no offer and is not an error. The cap toward the granted resonance grows by
    ``cap_percent`` of the grant (at least 1), and the grant is linked to that cap.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if grant.source not in DEED_GAIN_SOURCES:
        return None
    sheet = grant.character_sheet
    own = own_affinity(sheet)
    if own is None or grant.resonance.affinity_id != own.pk:
        return None
    if not convertible_drift(sheet, grant.resonance):
        return None
    scene = get_active_scene(sheet.character.location)
    if scene is None:
        return None
    offer, _ = DriftConversionOffer.objects.get_or_create(character_sheet=sheet, scene=scene)
    cap, _ = DriftConversionCap.objects.get_or_create(
        offer=offer, target_resonance=grant.resonance, defaults={"cap": 0}
    )
    percent = get_drift_correction_config().cap_percent
    cap.cap += max(1, grant.amount * percent // 100)
    cap.save(update_fields=["cap"])
    cap.grants.add(grant)
    return offer


def lapse_conversion_offers(scene: Scene) -> int:
    """Delete every conversion offer the scene opened (their caps go with them).

    Returns how many offers lapsed.
    """
    offers = DriftConversionOffer.objects.filter(scene=scene)
    lapsed = offers.count()
    offers.delete()
    return lapsed
