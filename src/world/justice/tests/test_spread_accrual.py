"""The knowledge-seam writer: word landing where the deed is criminal mints heat (#1765)."""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import PersonaHeat
from world.justice.services import heat_for, tag_deed_crimes
from world.scenes.factories import PersonaFactory
from world.societies.constants import DeedKnowledgeSource
from world.societies.factories import LegendEntryFactory, SocietyFactory
from world.societies.knowledge_services import grant_deed_knowledge


class KnowledgeSeamAccrualTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.city_room = RoomProfileFactory(area=cls.city).objectdb
        cls.murder = CrimeKindFactory(slug="murder", name="Murder")
        AreaLawFactory(area=cls.kingdom, crime_kind=cls.murder)
        cls.actor = PersonaFactory()
        cls.deed = LegendEntryFactory(persona=cls.actor)

    def test_knowledge_with_room_mints_heat_once_per_new_knower(self):
        tag_deed_crimes(self.deed, [self.murder])
        hearers = [PersonaFactory(), PersonaFactory()]
        created = grant_deed_knowledge(
            deed=self.deed,
            personas=hearers,
            source=DeedKnowledgeSource.HEARD_TOLD,
            room=self.city_room,
        )
        self.assertEqual(created, 2)
        self.assertEqual(heat_for(self.actor, self.city_room).value, DEFAULT_HEAT_WEIGHT * 2)
        # Retelling to the same ears is idempotent — no new rows, no new heat.
        again = grant_deed_knowledge(
            deed=self.deed,
            personas=hearers,
            source=DeedKnowledgeSource.HEARD_TOLD,
            room=self.city_room,
        )
        self.assertEqual(again, 0)
        self.assertEqual(heat_for(self.actor, self.city_room).value, DEFAULT_HEAT_WEIGHT * 2)

    def test_no_room_no_heat(self):
        tag_deed_crimes(self.deed, [self.murder])
        grant_deed_knowledge(
            deed=self.deed,
            personas=[PersonaFactory()],
            source=DeedKnowledgeSource.WITNESSED,
        )
        self.assertEqual(PersonaHeat.objects.count(), 0)

    def test_untagged_deed_spreads_cold(self):
        grant_deed_knowledge(
            deed=self.deed,
            personas=[PersonaFactory()],
            source=DeedKnowledgeSource.HEARD_TOLD,
            room=self.city_room,
        )
        self.assertEqual(PersonaHeat.objects.count(), 0)


class CreationTimeTaggingTests(TestCase):
    """#1765 — criminality is declared at deed birth (create_solo_deed / create_legend_event)."""

    def test_create_solo_deed_accepts_crime_kinds(self) -> None:
        from world.societies.factories import LegendSourceTypeFactory
        from world.societies.services import create_solo_deed

        arson = CrimeKindFactory(slug="arson", name="Arson")
        persona = PersonaFactory()
        entry = create_solo_deed(
            persona,
            "PLACEHOLDER: burned the granary",
            LegendSourceTypeFactory(),
            10,
            crime_kinds=[arson],
        )
        self.assertEqual([t.crime_kind for t in entry.crime_tags.all()], [arson])
