"""Heat surfaces (#1765): room line, safe-now transition, web payload, API scoping.

Every surface is self-only (the issue's leak table) — the API tests pin the
owner/stranger boundary and the display tests pin the SAFE-renders-nothing rule.
"""

from django.test import TestCase
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from evennia_extensions.models import PlayerData
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.justice.constants import HEAT_TIER_FLOORS, HeatTier
from world.justice.display import room_heat_line, room_heat_payload, safe_transition_line
from world.justice.factories import AreaLawFactory, CrimeKindFactory, PersonaHeatFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.societies.factories import SocietyFactory

HEAT_URL = "/api/justice/heat/"


def _floor(tier: HeatTier) -> int:
    return dict(HEAT_TIER_FLOORS)[tier]


class _JurisdictionFixture:
    """A crown kingdom with a city room, plus a guild-dominated hall inside it."""

    @classmethod
    def build(cls, target) -> None:
        target.crown = SocietyFactory()
        target.guild = SocietyFactory()
        target.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=target.crown)
        target.city = AreaFactory(level=AreaLevel.CITY, parent=target.kingdom)
        target.hall = AreaFactory(
            level=AreaLevel.BUILDING, parent=target.city, dominant_society=target.guild
        )
        target.city_room = RoomProfileFactory(area=target.city).objectdb
        target.hall_room = RoomProfileFactory(area=target.hall).objectdb
        target.theft = CrimeKindFactory(slug="theft", name="Theft")
        AreaLawFactory(area=target.kingdom, crime_kind=target.theft)


class DisplayLineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _JurisdictionFixture.build(cls)
        cls.account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=cls.account)
        cls.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=cls.entry)
        cls.character = cls.entry.character_sheet.character
        cls.persona = cls.entry.character_sheet.primary_persona

    def _heat(self, value: int) -> None:
        PersonaHeatFactory(persona=self.persona, area=self.city, society=self.crown, value=value)

    def test_safe_renders_nothing(self) -> None:
        self.assertIsNone(room_heat_line(self.character, self.city_room))
        self.assertIsNone(room_heat_payload(self.character, self.city_room))

    def test_hot_renders_tier_line_and_payload(self) -> None:
        self._heat(_floor(HeatTier.HEAT_IS_ON))
        line = room_heat_line(self.character, self.city_room)
        self.assertIsNotNone(line)
        self.assertIn("The heat is on", line)
        # Default enforcer flavor renders until a society names its own.
        self.assertIn("The Watch", line)
        payload = room_heat_payload(self.character, self.city_room)
        self.assertEqual(payload["tier"], HeatTier.HEAT_IS_ON.value)

    def test_dangerous_line_names_the_local_enforcers(self) -> None:
        """Apostate 2026-07-03: the line is specific to the area's law enforcement."""
        from world.societies.models import Society

        # Mutate through the identity-mapped instance (the deep-copied test
        # fixture diverges from the cached row the jurisdiction walk returns).
        crown = Society.objects.get(pk=self.crown.pk)
        crown.enforcer_name = "The Honest"
        crown.save(update_fields=["enforcer_name"])
        self._heat(_floor(HeatTier.DANGEROUS))
        line = room_heat_line(self.character, self.city_room)
        self.assertIn("The Honest have been looking for you here", line)

    def test_sanctuary_renders_nothing_even_when_hot_outside(self) -> None:
        self._heat(_floor(HeatTier.EXTREME_HEAT))
        self.assertIsNone(room_heat_line(self.character, self.hall_room))

    def test_safe_transition_fires_only_on_a_real_drop(self) -> None:
        self._heat(_floor(HeatTier.HEAT_IS_ON))
        self.assertIsNotNone(safe_transition_line(self.character, self.city_room, self.hall_room))
        # Cold → cold move: silent.
        self.assertIsNone(safe_transition_line(self.character, self.hall_room, self.hall_room))

    def test_low_heat_transition_is_silent(self) -> None:
        self._heat(_floor(HeatTier.TENSE))
        self.assertIsNone(safe_transition_line(self.character, self.city_room, self.hall_room))


class HeatApiTests(APITestCase):
    def setUp(self) -> None:
        _JurisdictionFixture.build(self)
        self.account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=self.account)
        self.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=self.entry)
        self.persona = self.entry.character_sheet.primary_persona
        self.row = PersonaHeatFactory(
            persona=self.persona, area=self.city, society=self.crown, value=30
        )
        self.client.force_authenticate(user=self.account)

    def test_owner_sees_their_rows_as_tiers(self) -> None:
        data = self.client.get(HEAT_URL, {"viewer": self.entry.pk}).data
        rows = data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tier"], HeatTier.DANGEROUS.value)
        self.assertEqual(rows[0]["area_name"], self.city.name)
        self.assertNotIn("value", rows[0])  # tiers only — never the raw number

    def test_unowned_viewer_is_empty(self) -> None:
        stranger = RosterEntryFactory()  # not owned by self.account
        data = self.client.get(HEAT_URL, {"viewer": stranger.pk}).data
        self.assertEqual(data["results"], [])

    def test_missing_viewer_is_empty(self) -> None:
        data = self.client.get(HEAT_URL).data
        self.assertEqual(data["results"], [])

    def test_unauthenticated_is_denied(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(HEAT_URL, {"viewer": self.entry.pk})
        self.assertIn(response.status_code, (401, 403))
