"""Journeys for place features (#4675, slice 3 of #4651).

Staff attach a feature (a chandelier) to a blueprint place; staging the blueprint gives the
live place the same feature on the same square. A feature square must lie inside its place.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.positioning.factories import BlueprintFeatureFactory, FeatureTypeFactory
from world.areas.positioning.models import PositionFeature
from world.areas.positioning.services import (
    add_blueprint_position,
    attach_feature,
    create_blueprint,
    detach_feature,
    instantiate_blueprint,
)


def _blueprint_with_floor(feature_type=None, square=(6, 4)):
    blueprint = create_blueprint("Hall")
    floor = add_blueprint_position(blueprint, "Floor")
    floor.area_x, floor.area_y, floor.area_w, floor.area_h = 2, 2, 10, 8
    floor.save()
    if feature_type is not None:
        BlueprintFeatureFactory(
            blueprint_position=floor,
            feature_type=feature_type,
            square_x=square[0],
            square_y=square[1],
        )
    return blueprint, floor


class FeatureJourneys(TestCase):
    def test_staging_a_blueprint_gives_the_live_place_its_feature(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor(chandelier)
        room = RoomProfileFactory().objectdb

        positions = instantiate_blueprint(blueprint, room)

        feature = PositionFeature.objects.get(position=positions[0])
        self.assertEqual(feature.feature_type, chandelier)
        self.assertEqual((feature.square_x, feature.square_y), (6, 4))

    def test_restaging_with_a_featureless_blueprint_leaves_no_features(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        with_feature, _ = _blueprint_with_floor(chandelier)
        bare = create_blueprint("Bare")
        add_blueprint_position(bare, "Floor")
        room = RoomProfileFactory().objectdb
        instantiate_blueprint(with_feature, room)

        instantiate_blueprint(bare, room, replace=True)

        self.assertFalse(PositionFeature.objects.filter(position__room=room).exists())

    def test_a_feature_square_outside_its_place_is_refused(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        _, floor = _blueprint_with_floor()
        feature = BlueprintFeatureFactory.build(
            blueprint_position=floor, feature_type=chandelier, square_x=40, square_y=4
        )
        with self.assertRaisesMessage(ValidationError, "That square is outside Floor."):
            feature.full_clean()

    def test_a_square_on_a_place_with_no_area_is_refused(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint = create_blueprint("Plain")
        bare = add_blueprint_position(blueprint, "Yard")
        feature = BlueprintFeatureFactory.build(
            blueprint_position=bare, feature_type=chandelier, square_x=1, square_y=1
        )
        with self.assertRaises(ValidationError):
            feature.full_clean()

    def test_attach_then_detach_round_trips(self):
        chandelier = FeatureTypeFactory(name="Chandelier")
        blueprint, _ = _blueprint_with_floor()
        room = RoomProfileFactory().objectdb
        place = instantiate_blueprint(blueprint, room)[0]

        feature = attach_feature(place, chandelier, square=(6, 4))
        self.assertEqual(list(place.features.all()), [feature])
        self.assertEqual((feature.square_x, feature.square_y), (6, 4))

        detach_feature(feature)
        self.assertFalse(place.features.exists())
