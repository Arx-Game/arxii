from django.test import TestCase

from world.room_features.exceptions import RoomAlreadyHasFeatureError, RoomFeatureError


class RoomFeatureExceptionsTests(TestCase):
    def test_already_has_feature_is_a_room_feature_error(self) -> None:
        self.assertTrue(issubclass(RoomAlreadyHasFeatureError, RoomFeatureError))

    def test_already_has_feature_user_message(self) -> None:
        exc = RoomAlreadyHasFeatureError("room 5 already has a feature")
        self.assertEqual(exc.user_message, "This room already has a feature installed.")
