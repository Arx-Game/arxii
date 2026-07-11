"""`where` service (#1463) — coloured area-path rendering with colour inheritance."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.services import colored_area_path, where_listing
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.roster.factories import RosterEntryFactory


class ColoredAreaPathTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.region = AreaFactory(name="Umbros", level=AreaLevel.REGION, color="|y")
        # Ward leaves colour blank → inherits the region's |y.
        cls.ward = AreaFactory(name="Blackgate Ward", level=AreaLevel.WARD, parent=cls.region)
        # Building overrides to |r.
        cls.building = AreaFactory(
            name="Sable Hold", level=AreaLevel.BUILDING, parent=cls.ward, color="|r"
        )
        cls.profile = RoomProfileFactory(area=cls.building)
        cls.room = cls.profile.objectdb

    def test_colours_inherit_down_and_can_be_overridden(self) -> None:
        path = colored_area_path(self.room)
        assert "|yUmbros|n" in path
        assert "|yBlackgate Ward|n" in path  # inherited
        assert "|rSable Hold|n" in path  # override

    def test_segments_are_outermost_first(self) -> None:
        path = colored_area_path(self.room)
        assert path.index("Umbros") < path.index("Blackgate Ward") < path.index("Sable Hold")

    def test_room_without_area_returns_plain_name(self) -> None:
        profile = RoomProfileFactory(area=None)
        path = colored_area_path(profile.objectdb)
        assert "|" not in path
        assert path == profile.objectdb.key


class WhereListingConcealmentTests(TestCase):
    """A concealed-and-undetected character is omitted from ``where`` (#1225 review gap).

    Unlike the room-occupant list (per-observer ``can_perceive``), ``where`` is an
    anonymous global directory with no coherent per-observer detection concept, so
    omission here is unconditional — mirroring the existing quiet-mode
    (``hidden_from_viewer``) omission already in ``where_listing``.
    """

    def setUp(self) -> None:
        self.profile = RoomProfileFactory()
        self.room = self.profile.objectdb

        self.visible_sheet = RosterEntryFactory().character_sheet
        self.visible = self.visible_sheet.character
        self.visible.location = self.room

        self.concealed_sheet = RosterEntryFactory().character_sheet
        self.concealed = self.concealed_sheet.character
        self.concealed.location = self.room

        cat = ConditionCategoryFactory(conceals_from_perception=True)
        condition = ConditionTemplateFactory(category=cat)
        ConditionInstanceFactory(target=self.concealed, condition=condition)

    @staticmethod
    def _session(puppet: object) -> SimpleNamespace:
        return SimpleNamespace(puppet=puppet)

    def test_concealed_character_omitted_from_where(self) -> None:
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [
                self._session(self.visible),
                self._session(self.concealed),
            ]
            entries = where_listing()
        names = [entry.persona_name for entry in entries]
        assert self.concealed_sheet.primary_persona.name not in names

    def test_unconcealed_character_still_appears_in_where(self) -> None:
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [
                self._session(self.visible),
                self._session(self.concealed),
            ]
            entries = where_listing()
        names = [entry.persona_name for entry in entries]
        assert self.visible_sheet.primary_persona.name in names

    def test_where_entry_includes_room_id(self) -> None:
        with patch("evennia.SESSION_HANDLER") as handler:
            handler.get_sessions.return_value = [self._session(self.visible)]
            entries = where_listing()
        assert any(entry.room_id == self.room.id for entry in entries)
