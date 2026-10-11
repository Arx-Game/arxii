"""Tests for the #4239 Almanach actions: one ``.run()`` success per action with
plain-int kwargs (the REST dispatch shape), one refusal that relays the
service's ``user_message``, and the shared non-staff rejection."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.almanach import (
    AlmanachAddGangAction,
    AlmanachAttachSheetAction,
    AlmanachClaimWardAction,
    AlmanachCorrectKinAction,
    AlmanachCreateFamilyAction,
    AlmanachCreateKinAction,
    AlmanachEditPersonAction,
    AlmanachFoundOrganizationAction,
    AlmanachLinkKinAction,
    AlmanachOpenCrewSlotAction,
    AlmanachPromoteKinAction,
    AlmanachSetAppableAction,
    AlmanachSetHolderAction,
    AlmanachSetStatusAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory, GenderFactory
from world.roster.constants import NOBLE_KIND_NAME, DefinitionTier
from world.roster.factories import (
    FamilyFactory,
    FamilyKindFactory,
    KinspersonFactory,
    UnionKindFactory,
)
from world.roster.models import Family, Kinsperson, ParentageEdge, Union
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import HoldingChoice, KinLink, LifeStatus, TitleTier
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.models import Title
from world.societies.models import CrewSlot, Organization, Turf


def _staff_actor(db_key: str) -> ObjectDB:
    char = CharacterFactory(db_key=db_key)
    char.db_account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.save()
    return char


def _player_actor(db_key: str) -> ObjectDB:
    char = CharacterFactory(db_key=db_key)
    char.db_account = AccountFactory(username=f"acct_{db_key}", is_staff=False)
    char.save()
    return char


class AlmanachPeopleActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = _staff_actor("PeopleStaff")
        cls.player = _player_actor("PeoplePlayer")
        cls.realm = RealmFactory(name="Umbros")
        cls.commoners = FamilyKindFactory(name="Commoner")
        cls.noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        cls.template = HouseTemplateFactory(realm=cls.realm, kind=cls.noble)
        cls.crown = OrganizationFactory(
            name="The Umbral Crown", family=FamilyFactory(name="House Crown", kind=cls.noble)
        )
        cls.throne = plant_rung(
            realm=cls.realm, tier=TitleTier.KINGDOM, name="Umbros", held_by=cls.crown
        )
        cls.marriage = UnionKindFactory(name="Marriage")
        OrganizationTypeFactory(name="gang")

    def test_non_staff_is_refused_everywhere(self):
        for action in (
            AlmanachCreateFamilyAction(),
            AlmanachCreateKinAction(),
            AlmanachLinkKinAction(),
            AlmanachSetStatusAction(),
            AlmanachClaimWardAction(),
        ):
            result = action.run(self.player)
            self.assertFalse(result.success, action.key)

    def test_create_family_alone_and_with_holding(self):
        result = AlmanachCreateFamilyAction().run(
            self.staff, kind_id=self.commoners.pk, name="Teale", realm_id=self.realm.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertIsNone(result.data["org_id"])
        self.assertTrue(Family.objects.filter(pk=result.data["family_id"]).exists())

        kathryn = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.STANDING
        )
        result = AlmanachCreateFamilyAction().run(
            self.staff,
            kind_id=self.noble.pk,
            name="Katta",
            realm_id=self.realm.pk,
            template_id=self.template.pk,
            holding=HoldingChoice.CREATE,
            title_tier=TitleTier.DUCHY,
            title_name="Duchy of Katta",
            parent_title_id=self.throne.pk,
            holder_id=kathryn.pk,
        )
        self.assertTrue(result.success, result.message)
        title = Title.objects.get(pk=result.data["title_id"])
        self.assertEqual(title.holder, kathryn)
        self.assertEqual(title.house_id, result.data["org_id"])

    def test_create_family_relays_the_refusal(self):
        result = AlmanachCreateFamilyAction().run(
            self.staff, kind_id=self.noble.pk, name="Katta", realm_id=self.realm.pk
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Pick a family type for this realm.")
        result = AlmanachCreateFamilyAction().run(
            self.staff, kind_id=self.commoners.pk, name="X", realm_id=self.realm.pk, holding="maybe"
        )
        self.assertFalse(result.success)

    def test_found_organization(self):
        family = FamilyFactory(name="Teale", kind=self.commoners, origin_realm=self.realm)
        result = AlmanachFoundOrganizationAction().run(
            self.staff, family_id=family.pk, template_id=self.template.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(Organization.objects.get(pk=result.data["org_id"]).family, family)
        again = AlmanachFoundOrganizationAction().run(
            self.staff, family_id=family.pk, template_id=self.template.pk
        )
        self.assertEqual(again.message, "That family already has an organization.")

    def test_create_kin_link_and_correct(self):
        family = FamilyFactory(name="Teale", kind=self.commoners)
        gender = GenderFactory()
        result = AlmanachCreateKinAction().run(
            self.staff,
            family_id=family.pk,
            name="Mara Teale",
            tier=DefinitionTier.STANDING,
            gender_id=gender.pk,
            age="40",
        )
        self.assertTrue(result.success, result.message)
        mara = Kinsperson.objects.get(pk=result.data["kinsperson_id"])
        self.assertEqual((mara.age, mara.gender), (40, gender))

        child = KinspersonFactory(name="Child Teale", family=family)
        result = AlmanachLinkKinAction().run(
            self.staff, node_id=child.pk, other_id=mara.pk, link=KinLink.PARENT
        )
        self.assertTrue(result.success, result.message)
        edge = ParentageEdge.objects.get(pk=result.data["edge_id"])
        self.assertEqual((edge.child, edge.parent), (child, mara))

        spouse = KinspersonFactory(name="A man of Varrow", family=FamilyFactory(name="Varrow"))
        result = AlmanachLinkKinAction().run(
            self.staff,
            node_id=mara.pk,
            other_id=spouse.pk,
            link=KinLink.SPOUSE,
            union_kind_id=self.marriage.pk,
            is_public_record="false",
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(Union.objects.get(pk=result.data["union_id"]).is_public_record)

        right = KinspersonFactory(name="Right Teale", family=family)
        result = AlmanachCorrectKinAction().run(self.staff, edge_id=edge.pk, new_parent_id=right.pk)
        self.assertTrue(result.success, result.message)
        self.assertEqual(ParentageEdge.objects.get(pk=result.data["edge_id"]).parent, right)

        refused = AlmanachLinkKinAction().run(
            self.staff, node_id=child.pk, other_id=child.pk, link=KinLink.PARENT
        )
        self.assertEqual(refused.message, "A person cannot be linked to themself.")

    def test_status_promote_appable_attach(self):
        node = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.FUNCTIONARY
        )
        result = AlmanachSetStatusAction().run(
            self.staff,
            node_id=node.pk,
            status=LifeStatus.RIP,
            record_accurate="false",
            obituary="Lost at sea.",
        )
        self.assertTrue(result.success, result.message)
        node.refresh_from_db()
        self.assertTrue(node.is_deceased)
        self.assertFalse(node.believed_deceased)
        self.assertEqual(node.obituary, "Lost at sea.")
        AlmanachSetStatusAction().run(self.staff, node_id=node.pk, status=LifeStatus.ALIVE)

        result = AlmanachPromoteKinAction().run(
            self.staff, node_id=node.pk, tier=DefinitionTier.STANDING
        )
        self.assertTrue(result.success, result.message)
        down = AlmanachPromoteKinAction().run(
            self.staff, node_id=node.pk, tier=DefinitionTier.FUNCTIONARY
        )
        self.assertEqual(down.message, "Tier only rises.")

        woman = GenderFactory()
        result = AlmanachSetAppableAction().run(
            self.staff,
            node_id=node.pk,
            appable="true",
            age_min="18",
            age_max="30",
            allowed_gender_ids=[woman.pk],
            name_locked=True,
        )
        self.assertTrue(result.success, result.message)
        node.refresh_from_db()
        self.assertTrue(node.is_appable)
        self.assertEqual(list(node.allowed_genders.all()), [woman])

        sheet = CharacterSheetFactory()
        result = AlmanachAttachSheetAction().run(self.staff, node_id=node.pk, sheet_id=sheet.pk)
        self.assertTrue(result.success, result.message)
        node.refresh_from_db()
        self.assertEqual(node.sheet, sheet)
        self.assertEqual(node.definition_tier, DefinitionTier.SHEETED)
        self.assertFalse(node.is_appable)

        result = AlmanachPromoteKinAction().run(
            self.staff, node_id=KinspersonFactory(name="Steward").pk, tier=DefinitionTier.SHEETED
        )
        self.assertTrue(result.success, result.message)
        self.assertIsNotNone(result.data["sheet_id"])

    def test_set_holder(self):
        outsider = KinspersonFactory(name="Outsider")
        refused = AlmanachSetHolderAction().run(
            self.staff, title_id=self.throne.pk, node_id=outsider.pk
        )
        self.assertEqual(refused.message, "The holder must be of the holding family.")
        result = AlmanachCreateKinAction().run(
            self.staff, family_id=self.crown.family_id, name="Royal"
        )
        result = AlmanachSetHolderAction().run(
            self.staff, title_id=self.throne.pk, node_id=result.data["kinsperson_id"]
        )
        self.assertTrue(result.success, result.message)
        self.throne.refresh_from_db()
        self.assertEqual(self.throne.holder.name, "Royal")

    def test_ward_gang_and_crew_slot(self):
        city = AreaFactory(level=AreaLevel.BARONY)
        ward = AreaFactory(level=AreaLevel.WARD, parent=city)
        neighborhood = AreaFactory(level=AreaLevel.NEIGHBORHOOD, parent=ward)
        family = OrganizationFactory(name="the Saltside family")
        result = AlmanachClaimWardAction().run(
            self.staff, organization_id=family.pk, area_id=ward.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(Turf.objects.get(pk=result.data["turf_id"]).controlling_org, family)

        result = AlmanachAddGangAction().run(
            self.staff,
            family_org_id=family.pk,
            name="Ashfingers",
            neighborhood_area_id=neighborhood.pk,
        )
        self.assertTrue(result.success, result.message)
        gang = Organization.objects.get(pk=result.data["org_id"])
        self.assertEqual(gang.parent_org, family)

        corner = RoomProfileFactory(area=neighborhood, is_outdoor=True)
        result = AlmanachOpenCrewSlotAction().run(
            self.staff, gang_id=gang.pk, name="The Saltside corner", room_ids=[str(corner.pk)]
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(
            list(CrewSlot.objects.get(pk=result.data["crew_slot_id"]).rooms.all()), [corner]
        )

        refused = AlmanachClaimWardAction().run(
            self.staff, organization_id=family.pk, area_id=neighborhood.pk
        )
        self.assertEqual(refused.message, "A family's turf is a ward or a city.")

    def test_edit_person(self):
        node = KinspersonFactory(name="Kathryn", age=24)
        result = AlmanachEditPersonAction().run(
            self.staff, node_id=node.pk, name="Kathryn mar Katta", age="25"
        )
        self.assertTrue(result.success, result.message)
        node.refresh_from_db()
        self.assertEqual((node.name, node.age), ("Kathryn mar Katta", 25))
        pc = KinspersonFactory(name="A PC", definition_tier=DefinitionTier.PC, age=30)
        refused = AlmanachEditPersonAction().run(self.staff, node_id=pc.pk, name="Renamed")
        self.assertFalse(refused.success)
        ok = AlmanachEditPersonAction().run(self.staff, node_id=pc.pk, age="31")
        self.assertTrue(ok.success, ok.message)
