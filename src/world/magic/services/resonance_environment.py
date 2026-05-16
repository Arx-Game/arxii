"""Services for the resonance-environment primitive."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models, transaction

from evennia_extensions.models import RoomProfile
from world.areas.models import AreaClosure
from world.locations.constants import KeyType
from world.locations.models import LocationValueModifier
from world.locations.services import effective_value
from world.magic.constants import (
    AffinityInteractionKind,
    ResonanceDirection,
)
from world.magic.models import AffinityInteraction, ResonanceEnvironmentConfig
from world.magic.models.affinity import Affinity, Resonance
from world.magic.models.aura import CharacterAura
from world.magic.types.aura import AffinityType

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.magic.models.techniques import Technique


@dataclass(frozen=True)
class ResonanceEnvironmentEffect:
    """Result of evaluate_resonance_environment.

    valence:              ResonanceValence value, or "" when inert.
    kind:                 AffinityInteractionKind value, or "" when inert.
    direction:            ResonanceDirection value.
    magnitude:            0 when inert; >0 scales boon or harm.
    source_affinity:      The caster's working affinity, or None when inert.
    environment_affinity: The place's dominant affinity, or None when inert.
    """

    valence: str
    kind: str
    direction: str
    magnitude: int
    source_affinity: Affinity | None
    environment_affinity: Affinity | None


def _inert(direction: str = ResonanceDirection.BALANCED) -> ResonanceEnvironmentEffect:
    """Return an inert effect with no interaction."""
    return ResonanceEnvironmentEffect(
        valence="",
        kind="",
        direction=direction,
        magnitude=0,
        source_affinity=None,
        environment_affinity=None,
    )


def _get_room_resonances(room: DefaultObject) -> list[Resonance]:
    """Return all Resonance objects with any cascade contribution to this room.

    Queries LocationValueModifier rows where key_type=RESONANCE for the
    room's cascade (room-profile level + ancestor area levels). Returns
    distinct Resonance instances. Returns empty list if the room has no
    RoomProfile.
    """
    try:
        profile = room.room_profile
    except RoomProfile.DoesNotExist:
        return []

    area = profile.area
    ancestor_ids: list[int] = []
    if area is not None:
        ancestor_ids = list(
            AreaClosure.objects.filter(descendant_id=area.pk).values_list("ancestor_id", flat=True)
        )

    modifier_qs = LocationValueModifier.objects.filter(
        key_type=KeyType.RESONANCE,
    ).filter(models.Q(room_profile=profile) | models.Q(area_id__in=ancestor_ids))

    resonance_ids = modifier_qs.values_list("resonance_id", flat=True).distinct()
    return list(Resonance.objects.filter(pk__in=resonance_ids).select_related("affinity"))


def _dominant_place_affinity(room: DefaultObject, resonances: list[Resonance]) -> Affinity | None:
    """Determine the place's dominant affinity.

    Over the room's cascade resonances, the affinity whose summed
    effective_value(room, resonance=r) is largest. Tiebreak on equal
    sums by Affinity.name ascending (deterministic).

    Returns None if resonances is empty or all effective values are 0.
    """
    # Sum effective_value per affinity
    affinity_sums: dict[int, tuple[int, Affinity]] = {}
    for resonance in resonances:
        aff = resonance.affinity
        val = effective_value(room, resonance=resonance)
        if aff.pk not in affinity_sums:
            affinity_sums[aff.pk] = (0, aff)
        current_sum, _ = affinity_sums[aff.pk]
        affinity_sums[aff.pk] = (current_sum + val, aff)

    if not affinity_sums:
        return None

    # Find max; tiebreak by Affinity.name ascending
    best_sum = max(v for v, _ in affinity_sums.values())
    candidates = [(aff.name, aff) for total, aff in affinity_sums.values() if total == best_sum]
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _place_magnitude(
    room: DefaultObject,
    place_affinity: Affinity,
    resonances: list[Resonance],
) -> int:
    """Sum effective_value(room, resonance=r) over place-affinity resonances."""
    return sum(
        effective_value(room, resonance=r) for r in resonances if r.affinity_id == place_affinity.pk
    )


def _working_affinity_cast_time(
    technique: Technique,
    place_affinity: Affinity,
) -> tuple[Affinity | None, AffinityInteraction | None]:
    """Determine working affinity for cast-time evaluation.

    Collect distinct affinities from technique.gift.resonances. For each,
    look up AffinityInteraction vs place_affinity. Pick the interaction with
    the highest severity_multiplier; tiebreak by Affinity.name ascending.

    Returns (chosen_affinity, chosen_interaction). Returns (None, None) if
    no interactions are found.
    """
    # Collect distinct affinities from the gift's resonances
    gift_resonances = list(technique.gift.resonances.select_related("affinity").all())
    seen_affinity_pks: set[int] = set()
    affinities: list[Affinity] = []
    for r in gift_resonances:
        aff = r.affinity
        if aff.pk not in seen_affinity_pks:
            seen_affinity_pks.add(aff.pk)
            affinities.append(aff)

    if not affinities:
        return None, None

    # Gather (sort_key, interaction, affinity) tuples for pairs that have a row
    # Sort key: highest severity first (negated), then name ascending for tiebreak
    candidates: list[tuple[Decimal, str, AffinityInteraction, Affinity]] = []
    for aff in affinities:
        try:
            interaction = AffinityInteraction.objects.get(
                source_affinity=aff,
                environment_affinity=place_affinity,
            )
        except AffinityInteraction.DoesNotExist:
            continue
        candidates.append((-interaction.severity_multiplier, aff.name, interaction, aff))

    if not candidates:
        return None, None

    candidates.sort(key=lambda t: (t[0], t[1]))
    _, _, chosen_interaction, chosen_affinity = candidates[0]
    return chosen_affinity, chosen_interaction


def _working_affinity_presence_time(
    caster: DefaultObject,
    place_affinity: Affinity,
) -> tuple[Affinity | None, AffinityInteraction | None]:
    """Determine working affinity for presence-time evaluation (technique=None).

    Uses the caster's dominant CharacterAura affinity. Returns (None, None)
    if the caster has no CharacterAura or no interaction row exists.
    """
    try:
        aura = caster.aura
    except CharacterAura.DoesNotExist:
        return None, None

    dominant_type: AffinityType = aura.dominant_affinity
    # Map AffinityType enum value ("celestial", "primal", "abyssal") to Affinity
    try:
        working_affinity = Affinity.objects.get(name__iexact=dominant_type.value)
    except Affinity.DoesNotExist:
        return None, None

    try:
        interaction = AffinityInteraction.objects.get(
            source_affinity=working_affinity,
            environment_affinity=place_affinity,
        )
    except AffinityInteraction.DoesNotExist:
        return None, None

    return working_affinity, interaction


def _compute_direction(
    interaction: AffinityInteraction,
    caster_alignment: Decimal,
    place_magnitude: int,
    config: ResonanceEnvironmentConfig,
) -> str:
    """Compute direction from interaction aggressor and CORRUPT comparison.

    For CORRUPT kind: compare caster_strength proxy to place_magnitude.
      caster_strength = caster_alignment * 100 * config.caster_power_scalar
      caster_strength - place_magnitude > balanced_band → CASTER_DOMINANT
      place_magnitude - caster_strength > balanced_band → ENVIRONMENT_DOMINANT
      else → BALANCED

    For non-CORRUPT (AMPLIFY / REJECT / REPEL): ENVIRONMENT_DOMINANT — the
    environment acts on the working, whether the outcome is a boon or harm.
    """
    if interaction.kind == AffinityInteractionKind.CORRUPT:
        caster_strength = caster_alignment * Decimal(100) * config.caster_power_scalar
        diff_caster = caster_strength - Decimal(place_magnitude)
        diff_env = Decimal(place_magnitude) - caster_strength
        if diff_caster > Decimal(config.balanced_band):
            return ResonanceDirection.CASTER_DOMINANT
        if diff_env > Decimal(config.balanced_band):
            return ResonanceDirection.ENVIRONMENT_DOMINANT
        return ResonanceDirection.BALANCED

    return ResonanceDirection.ENVIRONMENT_DOMINANT


def evaluate_resonance_environment(
    *,
    caster: DefaultObject,
    room: DefaultObject,
    technique: Technique | None = None,
) -> ResonanceEnvironmentEffect:
    """How a place of power's resonance reacts to a caster/working.

    ``technique=None`` → presence-time evaluation (no technique-resonance
    factor; uses caster's dominant CharacterAura affinity). ``technique=...``
    → cast-time evaluation (uses technique.gift.resonances).

    Mechanism only. Returns the interaction; never applies effects. The
    reactive flow branches on the result and applies authored content.

    Missing CharacterAura → inert (valence="", magnitude=0). Documented
    so callers know NPCs and constructs without aura records are always
    inert in this mechanism.
    """
    # Step 1a: Enumerate the room's cascade resonances.
    room_resonances = _get_room_resonances(room)
    if not room_resonances:
        return _inert()

    # Step 2: Determine place's dominant affinity.
    place_affinity = _dominant_place_affinity(room, room_resonances)
    if place_affinity is None:
        return _inert()

    # Step 1b: Determine working affinity and look up AffinityInteraction.
    if technique is not None:
        working_affinity, interaction = _working_affinity_cast_time(technique, place_affinity)
    else:
        # Presence-time: _working_affinity_presence_time handles missing aura gracefully.
        working_affinity, interaction = _working_affinity_presence_time(caster, place_affinity)

    # Step 3: Missing interaction row → inert.
    if interaction is None or working_affinity is None:
        return _inert()

    # Step 4: place_magnitude = sum of effective_value over place-affinity resonances.
    p_magnitude = _place_magnitude(room, place_affinity, room_resonances)

    # Step 5: caster_alignment = caster.aura.<working_affinity_name_lower> / 100.
    try:
        aura = caster.aura
    except CharacterAura.DoesNotExist:
        return _inert()

    aura_field = working_affinity.name.lower()
    caster_aura_value: Decimal = getattr(aura, aura_field, Decimal("0.00"))
    caster_alignment = caster_aura_value / Decimal(100)

    # Step 6: raw = place_magnitude * caster_alignment * severity * base_coefficient.
    config = get_resonance_environment_config()
    raw = (
        Decimal(p_magnitude)
        * caster_alignment
        * interaction.severity_multiplier
        * config.base_coefficient
    )

    # Step 7: direction.
    direction = _compute_direction(interaction, caster_alignment, p_magnitude, config)

    # Step 8: magnitude = round(raw). 0 → inert.
    magnitude = round(raw)
    if magnitude <= 0:
        return _inert(direction)

    return ResonanceEnvironmentEffect(
        valence=interaction.valence,
        kind=interaction.kind,
        direction=direction,
        magnitude=magnitude,
        source_affinity=working_affinity,
        environment_affinity=place_affinity,
    )


def get_resonance_environment_config() -> ResonanceEnvironmentConfig:
    """Get-or-create the resonance environment config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = ResonanceEnvironmentConfig.objects.get_or_create(pk=1)
        return cfg
