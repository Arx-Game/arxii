from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.locations.services import (
    _validate_holder_kwargs,
    _validate_location_kwargs,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class ValidateLocationKwargsTests(TestCase):
    def test_accepts_area_only(self) -> None:
        _validate_location_kwargs(AreaFactory(), None)

    def test_accepts_room_profile_only(self) -> None:
        _validate_location_kwargs(None, RoomProfileFactory())

    def test_rejects_both_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_location_kwargs(AreaFactory(), RoomProfileFactory())

    def test_rejects_neither_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_location_kwargs(None, None)


class ValidateHolderKwargsTests(TestCase):
    def test_accepts_persona_only(self) -> None:
        _validate_holder_kwargs(PersonaFactory(), None)

    def test_accepts_organization_only(self) -> None:
        _validate_holder_kwargs(None, OrganizationFactory())

    def test_rejects_both_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_holder_kwargs(PersonaFactory(), OrganizationFactory())

    def test_rejects_neither_set(self) -> None:
        with self.assertRaises(ValueError):
            _validate_holder_kwargs(None, None)
