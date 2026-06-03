"""Services for the resonance-environment primitive."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models, transaction

from actions.types import WeightedConsequence
from evennia_extensions.models import RoomProfile
from world.areas.models import AreaClosure
from world.checks.consequence_resolution import apply_resolution, select_consequence_from_result
from world.checks.constants import EffectType
from world.checks.models import CheckType
from world.checks.services import perform_check
from world.checks.types import ResolutionContext
from world.conditions.services import apply_condition, remove_condition
from world.locations.constants import KeyType
from world.locations.models import LocationValueModifier
from world.locations.services import effective_value
from world.magic.constants import (
    ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME,
    AffinityInteractionKind,
    ResonanceDirection,
    ResonanceValence,
)
from world.magic.models import AffinityInteraction, ResonanceEnvironmentConfig
from world.magic.models.affinity import Affinity, Resonance
from world.magic.models.aura import CharacterAura
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.types.aura import AffinityType

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.character_sheets.models import CharacterSheet
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
    interaction:          The resolved AffinityInteraction row, or None when inert.
                          Carried from the primitive so consumers never re-query it.
    backfire_difficulty:  Precomputed check difficulty for OPPOSED backfire.
                          0 when inert or when valence is not OPPOSED.
                          Formula: backfire_base_difficulty + round(magnitude *
                          backfire_difficulty_per_magnitude).
    """

    valence: str
    kind: str
    direction: str
    magnitude: int
    source_affinity: Affinity | None
    environment_affinity: Affinity | None
    interaction: AffinityInteraction | None
    backfire_difficulty: int


def magical_profile(character_sheet: CharacterSheet) -> CharacterAura | None:
    """Return the character's CharacterAura, or None if not magically active.

    Magically active == the sheet's character has a related CharacterAura
    (every finalized PC; created unconditionally at CG by finalize_magic_data).
    A CharacterSheet may exist without an aura (NPC sheet / not-yet-finalized)
    → Quiescent. Sole magic-capability gate; stores nothing, not granted.
    """
    try:
        return character_sheet.character.aura
    except CharacterAura.DoesNotExist:
        return None


def _inert(direction: str = ResonanceDirection.BALANCED) -> ResonanceEnvironmentEffect:
    """Return an inert effect with no interaction."""
    return ResonanceEnvironmentEffect(
        valence="",
        kind="",
        direction=direction,
        magnitude=0,
        source_affinity=None,
        environment_affinity=None,
        interaction=None,
        backfire_difficulty=0,
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


def get_room_dominant_affinity(room: DefaultObject) -> Affinity | None:
    """Return the dominant cascade affinity for a room, or None if inert.

    Wraps ``_get_room_resonances`` + ``_dominant_place_affinity`` as a public
    entry point for callers outside this module (e.g. ``Room.dominant_affinity``).
    Returns None when the room has no RoomProfile, no tagged resonances, or
    all effective values are zero.
    """
    resonances = _get_room_resonances(room)
    return _dominant_place_affinity(room, resonances)


def _place_magnitude(
    room: DefaultObject,
    place_affinity: Affinity,
    resonances: list[Resonance],
) -> int:
    """Sum effective_value(room, resonance=r) over place-affinity resonances."""
    return sum(
        effective_value(room, resonance=r) for r in resonances if r.affinity_id == place_affinity.pk
    )


def _all_place_affinity_magnitudes(
    room: DefaultObject,
    resonances: list[Resonance],
) -> dict[Affinity, int]:
    """Sum effective_value per distinct Affinity across all cascade resonances.

    Used by the enriched formula to weight contributions from every place affinity,
    not only the dominant one. Affinities whose total is zero are excluded.
    """
    sums: dict[int, tuple[Affinity, int]] = {}
    for r in resonances:
        aff = r.affinity
        val = effective_value(room, resonance=r)
        if aff.pk not in sums:
            sums[aff.pk] = (aff, 0)
        aff_obj, current = sums[aff.pk]
        sums[aff.pk] = (aff_obj, current + val)
    return {aff_obj: total for aff_obj, total in sums.values() if total > 0}


def _working_affinities_for_raw(
    technique: Technique | None,
    working_affinity: Affinity,
) -> list[Affinity]:
    """Return the ordered list of working affinities for the enriched raw sum.

    Cast-time: all distinct affinities from the gift's resonances, preserving
    encounter order (the caller's loop is deterministic).
    Presence-time: just the single dominant aura affinity.
    """
    if technique is None:
        return [working_affinity]
    seen: set[int] = set()
    result: list[Affinity] = []
    for r in technique.gift.resonances.select_related("affinity").all():
        if r.affinity.pk not in seen:
            seen.add(r.affinity.pk)
            result.append(r.affinity)
    return result


def _enriched_raw(
    aura: CharacterAura,
    all_working: list[Affinity],
    place_magnitudes: dict[Affinity, int],
    primary_valence: str,
    config: ResonanceEnvironmentConfig,
) -> Decimal:
    """Compute the enriched raw severity by summing all same-valence (G, P) pair contributions.

    For each (working-affinity G, place-affinity P) pair whose AffinityInteraction shares
    ``primary_valence``:
        contribution = place_magnitude_P × caster_alignment_G × severity_G→P × base_coefficient

    Technique-resonance opposition weighting: ``all_working`` contains every distinct affinity
    from the gift's resonances (cast-time) or just the dominant aura affinity (presence-time).
    Multi-resonance place weighting: ``place_magnitudes`` covers every place affinity, so
    secondary affinities contribute in proportion to their magnitude and interaction severity.
    Pairs whose interaction row is absent or has a different valence are skipped.
    """
    raw = Decimal(0)
    for g_aff in all_working:
        g_alignment = getattr(aura, g_aff.name.lower(), Decimal("0.00")) / Decimal(100)
        for p_aff, p_mag in place_magnitudes.items():
            g_p = AffinityInteraction.objects.interaction_for(g_aff, p_aff)
            if g_p is None or g_p.valence != primary_valence:
                continue
            raw += Decimal(p_mag) * g_alignment * g_p.severity_multiplier * config.base_coefficient
    return raw


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
        interaction = AffinityInteraction.objects.interaction_for(aff, place_affinity)
        if interaction is None:
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

    interaction = AffinityInteraction.objects.interaction_for(working_affinity, place_affinity)
    if interaction is None:
        return None, None

    return working_affinity, interaction


def _compute_direction(
    interaction: AffinityInteraction,
    caster_alignment: Decimal,
    place_magnitude: int,
    config: ResonanceEnvironmentConfig,
) -> str:
    """Compute direction from caster strength vs place magnitude.

    The strength comparison runs when the interaction is flagged
    ``caster_dominance_defiles`` OR its kind is CORRUPT (the ``OR CORRUPT``
    preserves pair #8's existing computed direction). In that case:
      caster_strength = caster_alignment * 100 * config.caster_power_scalar
      caster_strength - place_magnitude > balanced_band → CASTER_DOMINANT
      place_magnitude - caster_strength > balanced_band → ENVIRONMENT_DOMINANT
      else → BALANCED

    Otherwise (non-flagged AMPLIFY / REJECT / REPEL): ENVIRONMENT_DOMINANT — the
    environment acts on the working; the caster can never overpower the place.
    """
    if interaction.caster_dominance_defiles or interaction.kind == AffinityInteractionKind.CORRUPT:
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

    # Step 5: caster_alignment for the primary working affinity (used in direction, Step 7).
    try:
        aura = caster.aura
    except CharacterAura.DoesNotExist:
        return _inert()

    aura_field = working_affinity.name.lower()
    caster_aura_value: Decimal = getattr(aura, aura_field, Decimal("0.00"))
    caster_alignment = caster_aura_value / Decimal(100)

    # Step 6 (enriched): see _enriched_raw for formula details.
    # Technique-resonance opposition weighting: all distinct gift affinities contribute.
    # Multi-resonance place weighting: all place affinities contribute, not only dominant.
    config = get_resonance_environment_config()
    all_working = _working_affinities_for_raw(technique, working_affinity)
    place_magnitudes = _all_place_affinity_magnitudes(room, room_resonances)
    raw = _enriched_raw(aura, all_working, place_magnitudes, interaction.valence, config)

    # Step 7: direction.
    direction = _compute_direction(interaction, caster_alignment, p_magnitude, config)

    # Step 8: magnitude = round(raw). 0 → inert.
    magnitude = round(raw)
    if magnitude <= 0:
        return _inert(direction)

    # Step 9: backfire_difficulty — only for OPPOSED valence.
    # Formula mirrors the (now-deleted) flow adapter: base + round(magnitude * per_magnitude).
    backfire_difficulty = 0
    if interaction.valence == ResonanceValence.OPPOSED:
        backfire_difficulty = config.backfire_base_difficulty + round(
            magnitude * float(config.backfire_difficulty_per_magnitude)
        )

    return ResonanceEnvironmentEffect(
        valence=interaction.valence,
        kind=interaction.kind,
        direction=direction,
        magnitude=magnitude,
        source_affinity=working_affinity,
        environment_affinity=place_affinity,
        interaction=interaction,
        backfire_difficulty=backfire_difficulty,
    )


def get_resonance_environment_config() -> ResonanceEnvironmentConfig:
    """Get-or-create the resonance environment config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = ResonanceEnvironmentConfig.objects.get_or_create(pk=1)
        return cfg


def clear_resonance_alignment(*, character_sheet: CharacterSheet) -> None:
    """Remove any resonance-alignment buff ConditionInstance from this character.

    Membership is data-derived from
    ``ResonanceAlignmentBoonTier.objects.boon_condition_templates()``
    (the cached accessor). Only ConditionInstances whose template is in that set are removed;
    all others are untouched. Idempotent — no-op if no buff is present.

    Hot-path zero-repeated-query design: called on every character move (T9 wires it into
    at_post_move). Uses ``character.conditions`` (the cached ConditionHandler installed as a
    cached_property on ObjectParent/Character). After the handler is warmed (first access per
    identity-map lifetime), subsequent calls are query-free — the handler caches active
    ConditionInstances; ``instances_for_templates`` filters in Python.

    Common no-buff case (non-magical characters / non-aligned rooms): handler already warm
    → boon_templates cached → empty Python intersection → return. ZERO queries.
    """
    boon_templates = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
    if not boon_templates:
        return

    character = character_sheet.character

    # instances_for_templates: Python filter over the cached active list — zero queries
    # after the handler is warm. ``remove_condition`` invalidates the handler so the
    # next ``active()`` call re-queries; that is correct and intentional.
    to_remove = [
        instance.condition
        for instance in character.conditions.instances_for_templates(boon_templates)
    ]

    for template in to_remove:
        remove_condition(character, template)


def refresh_resonance_alignment(*, character_sheet: CharacterSheet) -> None:
    """Apply (or refresh) the presence-tied ALIGNED resonance-environment buff.

    Integration-point B from the resonance-environment spec. Steps:

    1. Clear any existing resonance-alignment buff (idempotent reconcile).
    2. Gate: character must be magically active (CharacterAura exists).
    3. Gate: character must have a location with a RoomProfile.
    4. Evaluate presence-time resonance environment (technique=None).
    5. Gate: effect must be ALIGNED with magnitude > 0.
    6. Band-select the highest authored tier whose min_magnitude <= magnitude (in Python,
       using the ascending-ordered cached_alignment_boon_tiers list on the interaction).
    7. Apply the tier's ConditionTemplate to the character (no duration_rounds — persists
       until cleared on next move or explicit clear).
    """
    # Step 1: idempotent clear.
    clear_resonance_alignment(character_sheet=character_sheet)

    # Step 2: magic-activity gate.
    aura = magical_profile(character_sheet)
    if aura is None:
        return

    # Step 3: location + room-profile gate.
    character = character_sheet.character
    room_obj = character.location
    if room_obj is None:
        return

    try:
        room_obj.room_profile  # noqa: B018  # access for existence check
    except RoomProfile.DoesNotExist:
        return

    # Step 4: presence-time evaluation.
    effect = evaluate_resonance_environment(caster=character, room=room_obj, technique=None)

    # Step 5: must be ALIGNED with non-zero magnitude.
    if effect.valence != ResonanceValence.ALIGNED or effect.magnitude == 0:
        return

    # Step 6: band-select highest tier whose min_magnitude <= effect.magnitude.
    # interaction is carried on the effect (no re-query).
    interaction = effect.interaction
    if interaction is None:
        return

    tier = max(
        (t for t in interaction.cached_alignment_boon_tiers if t.min_magnitude <= effect.magnitude),
        key=lambda t: t.min_magnitude,
        default=None,
    )
    if tier is None:
        return

    # Step 7: apply; idempotent by construction (step 1 cleared all prior boons).
    apply_condition(
        character,
        tier.condition_template,
        source_description="resonance environment alignment",
    )


@dataclass(frozen=True)
class ResonanceEnvironmentCastResult:
    """Result of resonance_environment_for_cast.

    valence:  ResonanceValence value, or "" when inert.
    applied:  Tuple of ConditionTemplate names applied during this call.
              Empty when inert or when no effects fired.
    """

    valence: str
    applied: tuple[str, ...]


_INERT_CAST_RESULT = ResonanceEnvironmentCastResult(valence="", applied=())


def _get_endure_hallowed_ground_check_type() -> CheckType:
    """Return the seeded 'endure_hallowed_ground' CheckType.

    Uses get() — never get_or_create — because this is authored content seeded
    with a ResultChart; fabricating a chartless row would silently break the
    resolution pipeline. If the seed is missing, CheckType.DoesNotExist propagates
    loudly (a real misconfiguration), not masked.
    """
    return CheckType.objects.get(name=ENDURE_HALLOWED_GROUND_CHECK_TYPE_NAME)


def _is_opposed_backfire(effect: ResonanceEnvironmentEffect) -> bool:
    """Return True when the effect should trigger the OPPOSED backfire pipeline.

    Suppressed when defilement fires: a CASTER_DOMINANT caster on a
    ``caster_dominance_defiles`` interaction overpowers the place and defiles it
    instead of suffering the reject/repel backfire (e.g. a strong Abyssal caster
    defiles a Celestial place rather than taking Hallowed Burn). A weak caster
    (ENVIRONMENT_DOMINANT) still backfires normally.
    """
    return (
        effect.kind != AffinityInteractionKind.CORRUPT
        and effect.valence == ResonanceValence.OPPOSED
        and effect.kind in (AffinityInteractionKind.REJECT, AffinityInteractionKind.REPEL)
        and effect.interaction is not None
        and effect.interaction.consequence_pool is not None
        and not (
            effect.direction == ResonanceDirection.CASTER_DOMINANT
            and effect.interaction.caster_dominance_defiles
        )
    )


def resonance_environment_for_cast(
    *,
    caster_sheet: CharacterSheet,
    room_profile: RoomProfile,
    technique: Technique | None,
) -> ResonanceEnvironmentCastResult:
    """Apply resonance-environment backfire for OPPOSED casts.

    Called from the technique-use orchestrator after accrue_corruption_for_cast.
    Emits no events and runs no flows — this is a direct core-service call.

    Branch behaviour
    ----------------
    - No CharacterAura         → inert (Quiescent caster; NPCs, unfinalized PCs)
    - magnitude == 0           → inert
    - kind == CORRUPT          → inert (deferred; direction computed but not acted on here)
    - ALIGNED                  → inert (presence-tied boon; handled by T7)
    - OPPOSED + no pool        → inert (no authored content for this pairing yet)
    - OPPOSED + pool           → perform_check at effect.backfire_difficulty, select
                                  from pool.cached_consequences, apply to caster

    Check/select/apply path
    -----------------------
    Uses perform_check → select_consequence_from_result → apply_resolution.
    select_consequence_from_result is used (not select_consequence) because
    pool.cached_consequences is list[WeightedConsequence], which is the type
    select_consequence_from_result is documented and typed to accept.
    select_consequence expects list[Consequence] and is incompatible without
    an unsafe cast. This matches the spec's net behaviour: endurance check at
    backfire_difficulty → weighted select by outcome tier → apply authored condition.
    """
    # Gate: must be magically active.
    aura = magical_profile(caster_sheet)
    if aura is None:
        return _INERT_CAST_RESULT

    # Down-convert at the primitive boundary (localized, not widened public type).
    caster = caster_sheet.character
    room = room_profile.objectdb

    effect = evaluate_resonance_environment(caster=caster, room=room, technique=technique)

    if not _is_opposed_backfire(effect):
        return _INERT_CAST_RESULT

    # Interaction instance is carried on the primitive result — no re-query.
    # _is_opposed_backfire already confirmed interaction and pool are non-None.
    interaction = effect.interaction  # type: ignore[union-attr]
    pool = interaction.consequence_pool

    # Perform the endurance check at the config-derived difficulty.
    check_type = _get_endure_hallowed_ground_check_type()
    check_result = perform_check(caster, check_type, effect.backfire_difficulty)

    # Select from the pool using the existing check result (pool holds WeightedConsequence).
    weighted_consequences = pool.cached_consequences
    pending = select_consequence_from_result(caster, check_result, weighted_consequences)

    # Derive applied condition names BEFORE apply_resolution, from the selected consequence's
    # APPLY_CONDITION effects. This gives a deterministic source immune to prose formatting.
    # Unwrap WeightedConsequence to the underlying Consequence (mirrors apply_resolution's
    # own isinstance unwrap so both paths agree on which Consequence is in play).
    raw_consequence = pending.selected_consequence
    if isinstance(raw_consequence, WeightedConsequence):
        raw_consequence = raw_consequence.consequence

    applied_names = tuple(
        effect.condition_template.name
        for effect in raw_consequence.effects.all()
        if effect.effect_type == EffectType.APPLY_CONDITION
        and effect.condition_template_id is not None
    )

    # Apply effects to the caster.
    context = ResolutionContext(character=caster)
    apply_resolution(pending, context)

    return ResonanceEnvironmentCastResult(
        valence=effect.valence,
        applied=applied_names,
    )
