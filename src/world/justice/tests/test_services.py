"""Service-layer journeys: law cascade, jurisdiction, accrual, read, decay (#1765).

The area fixture is one feudal chain plus a rival border and an in-city
sanctuary, shared by every test:

    kingdom (dominant: crown)
      └─ city
           ├─ ward
           │    └─ hall (dominant: guild)   ← sanctuary
           └─ (rooms at city/ward level)
    rival_kingdom (dominant: rival)          ← across the border
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT, HeatTier
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import HeatSource, PersonaHeat
from world.justice.services import (
    accrue_for_deed_knowledge,
    accrue_heat,
    associate_heat,
    enforcing_society_for,
    heat_decay_tick,
    heat_for,
    law_for,
    tag_deed_crimes,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import SocietyFactory


class JusticeFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory()
        cls.rival = SocietyFactory()
        cls.guild = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.ward = AreaFactory(level=AreaLevel.WARD, parent=cls.city)
        cls.hall = AreaFactory(
            level=AreaLevel.BUILDING, parent=cls.ward, dominant_society=cls.guild
        )
        cls.rival_kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.rival)
        cls.theft = CrimeKindFactory(slug="theft", name="Theft")
        cls.kingdom_law = AreaLawFactory(
            area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT
        )
        cls.persona = PersonaFactory()

        cls.city_room = RoomProfileFactory(area=cls.city).objectdb
        cls.ward_room = RoomProfileFactory(area=cls.ward).objectdb
        cls.hall_room = RoomProfileFactory(area=cls.hall).objectdb
        cls.rival_room = RoomProfileFactory(area=cls.rival_kingdom).objectdb


class LawCascadeTests(JusticeFixtureMixin, TestCase):
    def test_kingdom_default_reaches_the_ward(self):
        self.assertEqual(law_for(self.ward, self.theft), self.kingdom_law)

    def test_local_row_overrides_the_liege(self):
        ward_law = AreaLawFactory(area=self.ward, crime_kind=self.theft, heat_weight=99)
        self.assertEqual(law_for(self.ward, self.theft), ward_law)
        # The city between them still sees the kingdom default.
        self.assertEqual(law_for(self.city, self.theft), self.kingdom_law)

    def test_exemption_short_circuits(self):
        AreaLawFactory(area=self.ward, crime_kind=self.theft, exempts=True)
        self.assertIsNone(law_for(self.ward, self.theft))
        self.assertEqual(law_for(self.city, self.theft), self.kingdom_law)

    def test_no_law_anywhere(self):
        smuggling = CrimeKindFactory(slug="smuggling", name="Smuggling")
        self.assertIsNone(law_for(self.ward, smuggling))

    def test_enforcing_society_walks_up(self):
        self.assertEqual(enforcing_society_for(self.ward), self.crown)
        self.assertEqual(enforcing_society_for(self.hall), self.guild)


class AccrualAndReadTests(JusticeFixtureMixin, TestCase):
    def test_accrue_and_read_at_the_scene(self):
        row = accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.ward)
        self.assertIsNotNone(row)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(row.society, self.crown)
        reading = heat_for(self.persona, self.ward_room)
        self.assertEqual(reading.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(reading.tier, HeatTier.WATCHED)

    def test_ward_heat_is_invisible_up_in_the_city(self):
        """Emergent falloff: heat minted in the ward doesn't read at city scope."""
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.ward)
        self.assertEqual(heat_for(self.persona, self.city_room).value, 0)

    def test_city_heat_reads_down_in_the_ward(self):
        """Knowledge that landed city-wide follows you into its wards."""
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.city)
        self.assertEqual(heat_for(self.persona, self.ward_room).value, DEFAULT_HEAT_WEIGHT)

    def test_cross_border_immunity(self):
        """No extradition: knowledge landing in the rival kingdom mints nothing."""
        result = accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.rival_kingdom)
        # The rival kingdom has no theft law of its own in this fixture.
        self.assertIsNone(result)
        # Even with a local law, a *crown* warrant never reads there.
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.city)
        self.assertEqual(heat_for(self.persona, self.rival_room).value, 0)

    def test_sanctuary_reads_safe(self):
        """Story 8: the guild hall reads Safe mid-manhunt (dominant-society mismatch)."""
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.city)
        self.assertGreater(heat_for(self.persona, self.city_room).value, 0)
        reading = heat_for(self.persona, self.hall_room)
        self.assertEqual(reading.value, 0)
        self.assertEqual(reading.tier, HeatTier.SAFE)

    def test_other_persona_is_cold(self):
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.ward)
        bystander = PersonaFactory()
        self.assertEqual(heat_for(bystander, self.ward_room).value, 0)

    def test_scale_multiplies_and_provenance_lands(self):
        accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.ward, scale=3)
        reading = heat_for(self.persona, self.ward_room, include_sources=True)
        self.assertEqual(reading.value, DEFAULT_HEAT_WEIGHT * 3)
        self.assertEqual(len(reading.sources), 1)
        self.assertEqual(reading.sources[0].amount, DEFAULT_HEAT_WEIGHT * 3)


class AssociationTests(JusticeFixtureMixin, TestCase):
    def test_outing_copies_the_warrants(self):
        mask = PersonaFactory()
        accrue_heat(persona=mask, crime_kind=self.theft, area=self.ward)
        accrue_heat(persona=mask, crime_kind=self.theft, area=self.city)
        touched = associate_heat(from_persona=mask, to_persona=self.persona)
        self.assertEqual(touched, 2)
        self.assertEqual(
            heat_for(self.persona, self.ward_room).value,
            heat_for(mask, self.ward_room).value,
        )
        # The mask keeps its own heat (copy, not move).
        self.assertGreater(heat_for(mask, self.ward_room).value, 0)


class DeedKnowledgeAccrualTests(JusticeFixtureMixin, TestCase):
    def test_tagged_deed_knowledge_mints_scaled_heat(self):
        from world.societies.factories import LegendEntryFactory

        deed = LegendEntryFactory(persona=self.persona)
        tag_deed_crimes(deed, [self.theft])
        accrue_for_deed_knowledge(deed=deed, room=self.ward_room, new_knower_count=2)
        reading = heat_for(self.persona, self.ward_room, include_sources=True)
        self.assertEqual(reading.value, DEFAULT_HEAT_WEIGHT * 2)
        self.assertEqual(reading.sources[0].deed, deed)

    def test_untagged_deed_is_a_no_op(self):
        from world.societies.factories import LegendEntryFactory

        deed = LegendEntryFactory(persona=self.persona)
        accrue_for_deed_knowledge(deed=deed, room=self.ward_room, new_knower_count=5)
        self.assertEqual(PersonaHeat.objects.count(), 0)


class DecayTests(JusticeFixtureMixin, TestCase):
    def test_decay_floors_and_deletes(self):
        hot = accrue_heat(persona=self.persona, crime_kind=self.theft, area=self.city)
        cold_persona = PersonaFactory()
        AreaLawFactory(area=self.ward, crime_kind=self.theft, heat_weight=2)
        cold = accrue_heat(persona=cold_persona, crime_kind=self.theft, area=self.ward)
        self.assertEqual(cold.value, 2)
        heat_decay_tick()
        PersonaHeat.flush_instance_cache()  # bulk F() update bypasses the identity map
        self.assertEqual(PersonaHeat.objects.get(pk=hot.pk).value, DEFAULT_HEAT_WEIGHT - 5)
        # The 2-point row hit zero and was dropped.
        self.assertFalse(PersonaHeat.objects.filter(pk=cold.pk).exists())
        self.assertEqual(HeatSource.objects.filter(heat_id=cold.pk).count(), 0)
