"""Tests for the #4239 Almanach reads: the front rolls and search, a person's
document, a rung's document, a family's document, and the Books, Forces,
Openings and Turf chapters on the house document."""

from __future__ import annotations

from django.db.models import Sum
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrganizationTreasury, OrgIncomeStream
from world.military.factories import MilitaryUnitFactory
from world.roster.constants import NOBLE_KIND_NAME, DefinitionTier
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinspersonFactory
from world.roster.services.kinship import OMNISCIENT
from world.societies.crew_slots import open_crew_slot
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.almanach import (
    _rung_area,
    create_family,
    create_kin,
    link_kin,
    plant_rung,
    set_appable,
)
from world.societies.houses.almanach_pages import (
    books_for,
    family_document,
    forces_for,
    front_rolls,
    openings_for,
    person_document,
    rung_document,
    search,
)
from world.societies.houses.almanach_reads import document_for_house
from world.societies.houses.constants import HoldingChoice, KinLink, LifeStatus, TitleTier
from world.societies.houses.factories import HoldingKindFactory, HouseTemplateFactory
from world.societies.houses.models import Domain, DomainGarrisonPost
from world.societies.houses.services import add_holding
from world.societies.turf_services import add_gang, claim_ward


class AlmanachPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.realm = RealmFactory(name="Umbros")
        cls.commoners = FamilyKindFactory(name="Commoner")
        cls.noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        template = HouseTemplateFactory(realm=cls.realm, kind=cls.noble)
        cls.crown = OrganizationFactory(
            name="The Umbral Crown", family=FamilyFactory(name="House Crown", kind=cls.noble)
        )
        cls.throne = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Umbros", held_by=cls.crown
        )
        cls.kathryn = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.STANDING
        )
        made = create_family(
            kind=cls.noble,
            name="Katta",
            realm=cls.realm,
            template=template,
            holding=HoldingChoice.CREATE,
            title_tier=TitleTier.DUCHY,
            title_name="Duchy of Katta",
            parent_title=cls.throne,
            holder=cls.kathryn,
        )
        cls.katta = made.family
        cls.house = made.organization
        cls.duchy = made.title
        cls.mother = create_kin(family=cls.katta, name="Mother mar Katta")
        link_kin(node=cls.kathryn, other=cls.mother, link=KinLink.PARENT)
        cls.sister = create_kin(family=cls.katta, name="Sister mar Katta")
        link_kin(node=cls.sister, other=cls.mother, link=KinLink.PARENT)
        set_appable(node=cls.sister, appable=True)
        cls.vacant_county = plant_rung(
            realm=cls.realm, tier=TitleTier.COUNTY, name="", parent_title=cls.duchy
        )
        cls.domain = Domain.objects.get(pk=_rung_area(cls.duchy).pk)
        add_holding(domain=cls.domain, kind=HoldingKindFactory(name="Quarry"), unsited=True)
        OrgIncomeStream.objects.create(
            organization=cls.house,
            name="Katta land taxes",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=1900,
            uncollected_pool=5700,
        )
        OrganizationTreasury.objects.create(organization=cls.house, balance=42000)
        cls.guard = MilitaryUnitFactory(
            name="Katta household guard", owner_org=cls.house, individual_count=120
        )
        DomainGarrisonPost.objects.create(domain=cls.domain, unit=cls.guard)

        cls.teale = create_family(kind=cls.commoners, name="Teale", realm=cls.realm).family
        cls.mara = create_kin(family=cls.teale, name="Mara Teale")
        cls.old = create_kin(family=cls.teale, name="Old Teale")
        set_appable(node=cls.old, appable=True)

        OrganizationTypeFactory(name="gang")
        cls.city = AreaFactory(name="Arx", level=AreaLevel.BARONY)
        cls.ward = AreaFactory(name="Saltside", level=AreaLevel.WARD, parent=cls.city)
        cls.neighborhood = AreaFactory(
            name="the Wharf", level=AreaLevel.NEIGHBORHOOD, parent=cls.ward
        )
        cls.saltside = OrganizationFactory(
            name="the Saltside family",
            family=FamilyFactory(name="Saltside", kind=cls.commoners),
        )
        claim_ward(organization=cls.saltside, area=cls.ward)
        cls.gang = add_gang(
            family_org=cls.saltside, name="Ashfingers", neighborhood=cls.neighborhood
        )
        open_crew_slot(
            gang=cls.gang,
            name="The corner",
            rooms=[RoomProfileFactory(area=cls.neighborhood, is_outdoor=True)],
        )

    def test_front_rolls_without_a_query(self):
        rolls = front_rolls()
        umbros = next(r for r in rolls.noble if r["name"] == "Umbros")
        self.assertEqual(umbros["kind"], "realm")
        self.assertGreaterEqual(umbros["titles"], 3)
        self.assertGreaterEqual(umbros["unclaimed"], 1)
        arx = next(r for r in rolls.crime if r["name"] == "Arx")
        self.assertEqual((arx["families"], arx["gangs"], arx["crew_slots"]), (1, 1, 1))
        names = [r["name"] for r in rolls.commoner]
        self.assertIn("Teale", names)
        self.assertNotIn("Katta", names)
        self.assertNotIn("Saltside", names)
        teale = next(r for r in rolls.commoner if r["name"] == "Teale")
        self.assertEqual((teale["on_record"], teale["appable"]), (2, 1))

    def test_front_rolls_with_a_query(self):
        rolls = front_rolls(q="katt")
        self.assertEqual([r["name"] for r in rolls.noble], ["House Katta"])
        self.assertEqual(rolls.commoner, [])
        rolls = front_rolls(q="salt")
        self.assertEqual([r["name"] for r in rolls.crime], ["the Saltside family"])
        rolls = front_rolls(q="tea")
        self.assertEqual([r["name"] for r in rolls.commoner], ["Teale"])

    def test_search(self):
        self.assertEqual(search("K"), [])
        kinds = {h.kind for h in search("Katt")}
        self.assertEqual(kinds, {"person", "family", "organization", "title"})
        self.assertEqual(len(search("Katt", limit=2)), 2)

    def test_person_document(self):
        doc = person_document(self.kathryn)
        self.assertEqual(doc.person["tier_display"], {"number": 2, "label": "Standing NPC"})
        self.assertEqual(doc.person["status"], LifeStatus.ALIVE)
        self.assertTrue(doc.person["record_accurate"])
        self.assertEqual(doc.family["organization_id"], self.house.pk)
        relations = {k["name"]: k["relation"] for k in doc.kin}
        self.assertEqual(relations["Mother mar Katta"], "parent")
        self.assertIn("Sister mar Katta", relations)
        self.assertEqual(doc.house["name"], "House Katta")
        self.assertEqual(doc.titles[0]["name"], "Duchy of Katta")
        self.assertEqual(doc.titles[0]["held_by"], "House Katta")
        self.assertEqual(doc.titles[0]["seat"], self.duchy.seat_domain.name)
        # The ladder's rule: an unclaimed child rung is not yet a vassal of a held one.
        self.assertEqual(doc.titles[0]["vassals"], 0)
        self.assertFalse(doc.sheet["is_appable"])
        self.assertEqual(doc.memberships, [])
        self.assertEqual(doc.record["parents"], 1)
        self.assertEqual(doc.record["siblings"], 1)

    def test_person_document_for_an_orphan_family_member(self):
        doc = person_document(self.old)
        self.assertIsNone(doc.house)
        self.assertIsNone(doc.family["organization_id"])
        self.assertTrue(doc.sheet["is_appable"])
        self.assertEqual(doc.person["tier_display"]["label"], "Offscreen Reference")

    def test_rung_document(self):
        doc = rung_document(self.duchy)
        self.assertEqual(doc.title["held_by"], "House Katta")
        self.assertEqual(doc.title["holder"], "Kathryn mar Katta")
        self.assertEqual(doc.title["sworn_to"], "The Umbral Crown")
        self.assertEqual(doc.demesne["domain_id"], self.domain.pk)
        self.assertEqual(len(doc.holdings), 1)
        self.assertTrue(doc.holdings[0]["unsited"])
        expected = OrgIncomeStream.objects.filter(organization=self.house, active=True).aggregate(
            g=Sum("gross_amount"), p=Sum("uncollected_pool")
        )
        self.assertEqual(doc.books["income_week"], expected["g"])
        self.assertEqual(doc.books["uncollected"], expected["p"])
        self.assertEqual(doc.books["treasury"], 42000)
        self.assertEqual(len(doc.forces), 1)
        self.assertTrue(doc.forces[0]["posted_here"])
        self.assertEqual(doc.forces[0]["men"], 120)
        self.assertEqual(len(doc.vassals), 1)
        self.assertEqual(doc.vassals[0]["held_by"], "")

    def test_books_and_forces_for_nothing(self):
        self.assertEqual(books_for(None).income_week, 0)
        self.assertEqual(forces_for(None), [])

    def test_house_document_chapters(self):
        doc = document_for_house(self.house, viewer=OMNISCIENT, staff=True)
        self.assertEqual(doc.books["treasury"], 42000)
        self.assertEqual(len(doc.forces), 1)
        self.assertEqual([a["name"] for a in doc.openings["appable"]], ["Sister mar Katta"])
        self.assertEqual(len(doc.openings["vacant_seats"]), 1)
        self.assertIsNone(doc.turf)
        self.assertEqual(len(openings_for(self.house).vacant_seats), 1)

    def test_crime_family_turf_chapter(self):
        doc = document_for_house(self.saltside, viewer=OMNISCIENT, staff=True)
        self.assertIsNotNone(doc.turf)
        self.assertEqual([w["name"] for w in doc.turf["wards"]], ["Saltside"])
        self.assertEqual(doc.turf["tier"], "Crime Family")
        gang = doc.turf["gangs"][0]
        self.assertEqual(gang["name"], "Ashfingers")
        self.assertEqual(gang["neighborhood"], "the Wharf")
        self.assertEqual(gang["crews"][0]["name"], "The corner")
        self.assertTrue(gang["crews"][0]["is_open"])

    def test_family_document_without_an_organization(self):
        doc = family_document(self.teale, viewer=OMNISCIENT, staff=True)
        self.assertIsNone(doc.organization_id)
        self.assertEqual(len(doc.tree["nodes"]), 2)
        self.assertEqual([a["name"] for a in doc.openings["appable"]], ["Old Teale"])
        doc = family_document(self.katta, viewer=OMNISCIENT, staff=True)
        self.assertEqual(doc.organization_id, self.house.pk)
