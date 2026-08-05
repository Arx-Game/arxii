"""Felt sun exposure (#2846) — the graded read under the sunlight bane/allergy system.

Extends ADR-0073's boolean shelter gate into one non-negative number per
character per room:

    residual = max(0, base(phase, sky) - shade - coverage - authored - resonance - magic)

The breakdown deliberately keeps mundane coverage separate from
resonance-imbued garment protection and modifier magic: the sun-flex
achievement candidate (#2377) and the vampire "shrug it off in something
skimpy" fantasy are pure reads over these fields.

Only the sun feeds ``base`` — no other light source ever counts. Shade
(``shade_only_residual``) is tracked separately because a bane-tier character
loses the condition only when *shadow* handles the sun, not clothing
(see ``world.species.sun_constants``).
"""

from __future__ import annotations

from typing import NamedTuple

from world.game_clock.constants import TimePhase
from world.game_clock.services import get_ic_phase
from world.locations.constants import StatKey
from world.species.sun_constants import (
    BASE_SUN_DAWN_DUSK,
    BASE_SUN_DAY,
    CLOTHING_COVERAGE_CAP,
    SUN_COVERAGE_REGIONS,
    SUN_MITIGATION_TARGET_NAME,
    SUN_PROTECTION_PER_REGION,
)


class SunExposure(NamedTuple):
    """Component breakdown of one character's felt sun exposure in one room."""

    base: int
    shade: int
    coverage: int
    authored_sun: int
    resonance_sun: int
    magic: int
    residual: int
    shade_only_residual: int


_NO_EXPOSURE = SunExposure(0, 0, 0, 0, 0, 0, 0, 0)


def felt_sun_exposure(character, room) -> SunExposure:
    """Compute *character*'s felt sun exposure in *room* with full breakdown."""
    base = _base_sunlight(room)
    if base <= 0:
        return _NO_EXPOSURE
    shade = _shade_value(character, room)
    coverage, authored_sun, resonance_sun = _clothing_protection(character)
    sheet = character.character_sheet
    magic = _magic_mitigation(sheet) if sheet is not None else 0
    residual = max(0, base - shade - coverage - authored_sun - resonance_sun - magic)
    shade_only_residual = max(0, base - shade)
    return SunExposure(
        base=base,
        shade=shade,
        coverage=coverage,
        authored_sun=authored_sun,
        resonance_sun=resonance_sun,
        magic=magic,
        residual=residual,
        shade_only_residual=shade_only_residual,
    )


def _base_sunlight(room) -> int:
    """Direct sunlight reaching *room*'s occupants before any mitigation.

    ``is_outdoor`` is the primary signal (matching the pre-#2846 gate); an
    *authored* ROOFED/SEALED enclosure blocks direct sun (a covered veranda).
    The unauthored WALLED default on an outdoor room is contradictory data and
    deliberately does NOT block — most outdoor grid rooms never set enclosure.
    """
    if not _sky_exposed(room):
        return 0
    phase = get_ic_phase()
    if phase == TimePhase.DAY:
        return BASE_SUN_DAY
    if phase in (TimePhase.DAWN, TimePhase.DUSK):
        return BASE_SUN_DAWN_DUSK
    return 0


def _sky_exposed(room) -> bool:
    """Whether direct sun can reach *room* at all (outdoor + no authored roof)."""
    if room is None:
        return False
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from evennia_extensions.constants import RoomEnclosure  # noqa: PLC0415

    try:
        profile = room.room_profile
    except (ObjectDoesNotExist, AttributeError):
        return False
    if not profile.is_outdoor:
        return False
    return profile.enclosure not in (RoomEnclosure.ROOFED, RoomEnclosure.SEALED)


def _shade_value(character, room) -> int:
    """Graded shade: the room's radiant-shelter cascade plus position shelter (#1744/#1756)."""
    from world.areas.positioning.services import (  # noqa: PLC0415
        position_of,
        position_shelter_value,
    )
    from world.conditions.factories import ensure_radiant_damage_type  # noqa: PLC0415
    from world.locations.services import effective_value  # noqa: PLC0415

    radiant = ensure_radiant_damage_type()
    total = effective_value(room, damage_type=radiant)
    position = position_of(character)
    if position is not None:
        total += position_shelter_value(position, radiant)
    return max(0, total)


def _clothing_protection(character) -> tuple[int, int, int]:
    """(coverage, mundane authored SUN, resonance-imbued SUN) from worn garments.

    A non-revealing garment protects each sun-relevant body region it is
    actually equipped over (capped — purpose-made gear goes further via
    authored rows). A revealing garment covers the slot but exposes skin, so
    it contributes only its authored ``GarmentMitigation`` SUN rows. Mirrors
    the per-template semantics of the comfort walk
    (``world.locations.character_comfort._worn_garment_mitigation``).
    """
    from world.items.models import GarmentMitigation  # noqa: PLC0415
    from world.items.services.appearance import covered_regions  # noqa: PLC0415

    # The shared skin-coverage predicate (#2985); SUN only counts its own regions.
    sun_covered = covered_regions(character) & set(SUN_COVERAGE_REGIONS)
    template_ids: set[int] = {row.item_instance.template.pk for row in character.equipped_items}
    coverage = min(
        CLOTHING_COVERAGE_CAP,
        len(sun_covered) * SUN_PROTECTION_PER_REGION,
    )
    authored = 0
    resonance_authored = 0
    if template_ids:
        rows = GarmentMitigation.objects.filter(
            item_template_id__in=template_ids, stat_key=StatKey.SUN
        )
        for mitigation in rows:
            if mitigation.resonance_id is None:
                authored += mitigation.value
            else:
                resonance_authored += mitigation.value
    return coverage, authored, resonance_authored


def _magic_mitigation(sheet) -> int:
    """Sun mitigation from the mechanics modifier system (spells/wards/conditions).

    ``sun_mitigation`` is a content-repo-owned ModifierTarget (#2698) — looked
    up, never invented here; absent target reads as 0. A glutted appetite
    holder (#2853, ruled) adds ``glut × GLUT_SUN_MITIGATION_FACTOR`` — stolen
    life answers the sun. It dampens severity but never clears a bane's debuff
    floor (only real shadow does, ADR-0179 — the floor reads shade only).
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415
    from world.mechanics.services import get_modifier_total  # noqa: PLC0415

    target = ModifierTarget.objects.filter(name=SUN_MITIGATION_TARGET_NAME).first()
    total = 0
    if target is not None:
        total = max(0, get_modifier_total(sheet, target))
    total += _glut_sun_mitigation(sheet)
    return total


def _glut_sun_mitigation(sheet) -> int:
    """Sun mitigation from feeding glut, for appetite holders (#2853)."""
    from world.species.appetites import (  # noqa: PLC0415
        GLUT_SUN_MITIGATION_FACTOR,
        AppetiteKind,
        appetite_for,
    )

    anima = sheet.anima_or_none
    if anima is None or anima.glut <= 0:
        return 0
    if appetite_for(sheet) == AppetiteKind.NONE:
        return 0
    return anima.glut * GLUT_SUN_MITIGATION_FACTOR
