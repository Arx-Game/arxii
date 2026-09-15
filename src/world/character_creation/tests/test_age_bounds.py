"""CG age bounds: the ceiling a heritage's first-appearance date imposes (#3663).

The first Misbegotten were born in 980 AS and the game opens at 1000 AS, so a
Misbegotten made in character generation can be at most 20 at launch and one
year older per IC year elapsed. ``age_bounds`` is the single place that rule
lives; the serializer and the draft payload read it.
"""

from datetime import UTC, date, datetime
from unittest.mock import Mock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.constants import AGE_MAX, AGE_MAX_ETERNAL_YOUTH, AGE_MIN
from world.character_creation.factories import BeginningsFactory, CharacterDraftFactory
from world.character_creation.serializers import BeginningsSerializer, CharacterDraftSerializer
from world.character_creation.services import age_bounds
from world.character_sheets.models import Heritage
from world.game_clock.factories import GameClockFactory
from world.species.factories import SpeciesFactory

FIRST_MISBEGOTTEN = date(980, 1, 1)


def _ic(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


class AgeBoundsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.misbegotten = Heritage.objects.create(
            name="Misbegotten",
            is_special=True,
            family_known=False,
            first_appeared_ic=FIRST_MISBEGOTTEN,
        )
        cls.normal = Heritage.objects.create(name="Normal")
        cls.tree_born = BeginningsFactory(heritage=cls.misbegotten)
        cls.raised = BeginningsFactory(heritage=cls.normal)
        cls.human = SpeciesFactory(name="Human")
        cls.elf = SpeciesFactory(name="Elf", eternal_youth=True)

    def test_launch_year_caps_at_twenty(self):
        bounds = age_bounds(self.human, self.tree_born, _ic(1000))
        assert bounds.minimum == AGE_MIN
        assert bounds.maximum == 20
        assert bounds.heritage_first_year == 980

    def test_ceiling_grows_with_ic_years(self):
        assert age_bounds(self.human, self.tree_born, _ic(1003, 6, 1)).maximum == 23

    def test_day_before_anniversary_does_not_count(self):
        assert age_bounds(self.human, self.tree_born, _ic(1002, 12, 31)).maximum == 22

    def test_floor_is_age_min_even_when_heritage_is_younger(self):
        assert age_bounds(self.human, self.tree_born, _ic(990)).maximum == AGE_MIN

    def test_eternal_youth_composes_with_heritage_ceiling(self):
        assert age_bounds(self.elf, self.tree_born, _ic(1000)).maximum == 20
        assert age_bounds(self.elf, self.tree_born, _ic(1040)).maximum == AGE_MAX_ETERNAL_YOUTH

    def test_no_clock_applies_no_heritage_ceiling(self):
        bounds = age_bounds(self.human, self.tree_born, None)
        assert bounds.maximum == AGE_MAX
        assert bounds.heritage_first_year == 980

    def test_heritage_without_anchor_keeps_general_cap(self):
        bounds = age_bounds(self.human, self.raised, _ic(1000))
        assert bounds.maximum == AGE_MAX
        assert bounds.heritage_first_year is None

    def test_no_species_and_no_beginnings(self):
        assert age_bounds(None, None, _ic(1000)).maximum == AGE_MAX


class AgeBoundsSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        misbegotten = Heritage.objects.create(
            name="Misbegotten",
            is_special=True,
            family_known=False,
            first_appeared_ic=FIRST_MISBEGOTTEN,
        )
        cls.tree_born = BeginningsFactory(heritage=misbegotten)
        cls.human = SpeciesFactory(name="Human")
        # Paused at 1000-06-01 AS: exactly twenty whole years past the anchor.
        GameClockFactory(anchor_ic_time=_ic(1000, 6, 1), paused=True)

    def _serializer(self, draft, data):
        request = Mock()
        request.user = self.account
        return CharacterDraftSerializer(
            draft, data=data, partial=True, context={"request": request}
        )

    def test_accepts_the_ceiling_and_rejects_one_past_it(self):
        draft = CharacterDraftFactory(
            account=self.account, selected_beginnings=self.tree_born, selected_species=self.human
        )
        assert self._serializer(draft, {"age": 20}).is_valid()
        serializer = self._serializer(draft, {"age": 21})
        assert not serializer.is_valid()
        assert serializer.errors["age"] == [
            "Misbegotten can be at most 20 years old: the first were born in 980 AS."
        ]

    def test_beginnings_in_the_same_request_set_the_ceiling(self):
        draft = CharacterDraftFactory(account=self.account, selected_species=self.human)
        serializer = self._serializer(
            draft, {"age": 21, "selected_beginnings_id": self.tree_born.id}
        )
        assert not serializer.is_valid()
        assert "age" in serializer.errors

    def test_payload_carries_the_bounds(self):
        draft = CharacterDraftFactory(
            account=self.account, selected_beginnings=self.tree_born, selected_species=self.human
        )
        request = Mock()
        request.user = self.account
        data = CharacterDraftSerializer(draft, context={"request": request}).data
        assert data["age_min"] == AGE_MIN
        assert data["age_max"] == 20
        assert data["selected_beginnings"]["heritage"] == {
            "name": "Misbegotten",
            "first_appeared_ic_year": 980,
        }

    def test_beginnings_without_heritage_serializes_null(self):
        beginnings = BeginningsFactory(heritage=None)
        assert BeginningsSerializer(beginnings).data["heritage"] is None
