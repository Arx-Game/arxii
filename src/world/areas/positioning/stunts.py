"""Stunts: using a feature in her place to reach another place (#4675, slice 3 of #4651).

A feature (a chandelier, a rope) stands in a place. A character in that place whose
capabilities pair with an approach on the feature's challenge may roll it to reach a place
the feature's ``reach`` allows. The roll is ``resolve_challenge`` on a one-shot instance of
the feature's challenge, as slice 2's pass over held ground does: above success level 0 she
lands cleanly, at 0 she lands roughly (whatever the template's partial consequence says),
below it she misses and stays put, and the template's own consequences are what happen.

Reach adjacency follows any edge, passable or not (a swing goes over a wall), and never
ends in the air. NPCs do not make stunts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Q

from world.areas.positioning.constants import (
    STUNT_CANT_FROM_HERE,
    FeatureReach,
    PositionKind,
    StuntOutcome,
)
from world.areas.positioning.exceptions import PositionError
from world.areas.positioning.models import Position, PositionEdge, PositionFeature
from world.areas.positioning.services import force_move_to_position, position_of
from world.areas.positioning.types import StuntOption
from world.mechanics.challenge_resolution import instantiate_challenge, resolve_challenge
from world.mechanics.models import ChallengeApproach
from world.mechanics.services import (
    _get_difficulty_indicator_for_check,
    get_capability_sources_for_character,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.types import CapabilitySource, ChallengeResolutionResult

_Way = tuple[ChallengeApproach, "CapabilitySource"]


def _best_sources(character: ObjectDB) -> dict[int, CapabilitySource]:
    """Her highest-valued source of each capability she holds above 0, by capability pk."""
    best: dict[int, CapabilitySource] = {}
    for source in get_capability_sources_for_character(character):
        if source.value <= 0:
            continue
        held = best.get(source.capability_id)
        if held is None or source.value > held.value:
            best[source.capability_id] = source
    return best


def _ways_by_template(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC making the stunt
    template_ids: set[int],
) -> dict[int, list[_Way]]:
    """Every approach on each template she has a capability for, strongest first. One query."""
    best = _best_sources(character)
    if not best or not template_ids:
        return {}
    approaches = ChallengeApproach.objects.filter(
        challenge_template_id__in=template_ids, application__capability_id__in=best
    ).select_related("application", "check_type", "challenge_template")
    ways: dict[int, list[_Way]] = {}
    for approach in approaches:
        source = best[approach.application.capability_id]
        ways.setdefault(approach.challenge_template_id, []).append((approach, source))
    for listed in ways.values():
        listed.sort(key=lambda way: (-way[1].value, way[0].pk))
    return ways


def _neighbours(current: Position) -> list[Position]:
    """Places joined to ``current`` by any edge, passable or not, none in the air."""
    edges = PositionEdge.objects.filter(
        Q(position_a=current) | Q(position_b=current)
    ).select_related("position_a", "position_b")
    neighbours = {}
    for edge in edges:
        other = edge.position_b if edge.position_a_id == current.pk else edge.position_a
        if other.kind != PositionKind.AERIAL:
            neighbours[other.pk] = other
    return sorted(neighbours.values(), key=lambda place: place.pk)


class _Destinations:
    """Where each reach can take her from ``current``; each set is read once, on demand."""

    def __init__(self, current: Position) -> None:
        self.current = current
        self._neighbours: list[Position] | None = None
        self._ground: list[Position] | None = None
        self._same_type: dict[int, list[Position]] | None = None

    def neighbours(self) -> list[Position]:
        if self._neighbours is None:
            self._neighbours = _neighbours(self.current)
        return self._neighbours

    def ground(self) -> list[Position]:
        if self._ground is None:
            self._ground = list(
                Position.objects.filter(room_id=self.current.room_id)
                .exclude(kind=PositionKind.AERIAL)
                .exclude(pk=self.current.pk)
                .order_by("pk")
            )
        return self._ground

    def same_type(self, feature_type_id: int, type_ids: set[int]) -> list[Position]:
        if self._same_type is None:
            self._same_type = {}
            others = (
                PositionFeature.objects.filter(
                    position__room_id=self.current.room_id, feature_type_id__in=type_ids
                )
                .exclude(position=self.current)
                .select_related("position")
                .order_by("position_id")
            )
            for other in others:
                listed = self._same_type.setdefault(other.feature_type_id, [])
                if other.position not in listed:
                    listed.append(other.position)
        return self._same_type.get(feature_type_id, [])

    def for_feature(self, feature: PositionFeature, type_ids: set[int]) -> list[Position]:
        reach = feature.feature_type.reach
        if reach == FeatureReach.ADJACENT:
            return self.neighbours()
        if reach == FeatureReach.ANY_PLACE:
            return self.ground()
        if reach == FeatureReach.SAME_TYPE:
            return self.same_type(feature.feature_type_id, type_ids)
        if reach == FeatureReach.ELEVATED_ADJACENT:
            return [place for place in self.neighbours() if place.kind == PositionKind.ELEVATED]
        return []


def _features_here(current: Position) -> list[PositionFeature]:
    return list(
        PositionFeature.objects.filter(position=current)
        .select_related("feature_type__challenge_template", "position")
        .order_by("pk")
    )


def stunt_options(character: ObjectDB) -> list[StuntOption]:  # noqa: OBJECTDB_PARAM - the PC
    """Every stunt ``character`` could make from a feature in her current place.

    One option per feature and destination, with the strongest approach on the feature's
    challenge she has a capability for (value above 0). Empty when she is nowhere, her
    place has no features, or no approach pairs with her capabilities. Bulk reads: the
    features, their approaches, and each reach's places once.
    """
    current = position_of(character)
    if current is None:
        return []
    features = _features_here(current)
    if not features:
        return []
    ways = _ways_by_template(character, {f.feature_type.challenge_template_id for f in features})
    if not ways:
        return []
    destinations = _Destinations(current)
    type_ids = {f.feature_type_id for f in features}
    difficulty_by_approach = {}
    options: list[StuntOption] = []
    for feature in features:
        template = feature.feature_type.challenge_template
        listed = ways.get(template.pk)
        if not listed:
            continue
        approach, source = listed[0]
        if approach.pk not in difficulty_by_approach:
            difficulty_by_approach[approach.pk] = _get_difficulty_indicator_for_check(
                character, approach.check_type, template.severity, source
            )
        options.extend(
            StuntOption(
                feature=feature,
                destination=destination,
                approach=approach,
                capability_value=source.value,
                difficulty=difficulty_by_approach[approach.pk],
                capability_source=source,
            )
            for destination in destinations.for_feature(feature, type_ids)
        )
    return options


def _choose_way(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC making the stunt
    feature: PositionFeature,
    destination: Position,
    approach: ChallengeApproach | None,
) -> _Way:
    """Her way to make this stunt, re-checked now; ``PositionError`` when there is none.

    The feature must be in her place, ``destination`` within its reach, and ``approach``
    (her strongest when None) one she has a capability for.
    """
    current = position_of(character)
    if current is None or feature.position_id != current.pk:
        raise PositionError(STUNT_CANT_FROM_HERE)
    reachable = _Destinations(current).for_feature(feature, {feature.feature_type_id})
    if destination.pk not in {place.pk for place in reachable}:
        raise PositionError(STUNT_CANT_FROM_HERE)
    template_id = feature.feature_type.challenge_template_id
    listed = _ways_by_template(character, {template_id}).get(template_id, [])
    if approach is not None:
        listed = [way for way in listed if way[0].pk == approach.pk]
    if not listed:
        raise PositionError(STUNT_CANT_FROM_HERE)
    return listed[0]


def _outcome_of(resolution: ChallengeResolutionResult) -> StuntOutcome:
    """Clean above success level 0, partial at 0, missed below it or with no roll."""
    if resolution.check_result is None:
        return StuntOutcome.MISSED
    level = resolution.check_result.success_level
    if level > 0:
        return StuntOutcome.CLEAN
    if level == 0:
        return StuntOutcome.PARTIAL
    return StuntOutcome.MISSED


def perform_stunt(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - the PC making the stunt
    feature: PositionFeature,
    destination: Position,
    approach: ChallengeApproach | None = None,
) -> StuntOutcome:
    """Roll the feature's challenge to reach ``destination``; move her unless she missed.

    Everything runs in one transaction. Refuses with ``PositionError("You can't do that
    from here.")`` before anything changes when the stunt is not hers to make now
    (``_choose_way``). Then mints a one-shot instance of the feature's challenge in the
    room, resolves it with the approach (applying the template's consequences for the
    outcome), deactivates it, and on a clean or partial outcome moves her into
    ``destination`` with no square (the map arranges her token). If resolution raises, the
    rollback removes the minted instance; nothing is saved on that path, so the original
    error is the one that surfaces.
    """
    with transaction.atomic():
        approach, source = _choose_way(character, feature, destination, approach)
        room = character.location
        instance = instantiate_challenge(
            feature.feature_type.challenge_template, location=room, target_object=room
        )
        # Every stunt is rolled in the open: a hidden instance would refuse the roll.
        if not instance.is_revealed:
            instance.is_revealed = True
            instance.save(update_fields=["is_revealed"])
        resolution = resolve_challenge(character, instance, approach, source)
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        outcome = _outcome_of(resolution)
        if outcome != StuntOutcome.MISSED:
            force_move_to_position(character, destination)
    return outcome
