"""Tests for the #4239 Almanach services: create a family with or without an
organization, kin from nothing, links to anyone, status, tier, appable, holder."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory, GenderFactory
from world.roster.constants import NOBLE_KIND_NAME, DefinitionTier, MembershipBasis
from world.roster.factories import (
    FamilyFactory,
    FamilyKindFactory,
    KinspersonFactory,
    ParentageEdgeFactory,
    UnionKindFactory,
)
from world.roster.models import Family, FamilyMembership, ParentageEdge, Union
from world.roster.services.kinship import add_membership
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    attach_sheet,
    correct_parentage,
    create_family,
    create_kin,
    found_organization,
    link_kin,
    plant_rung,
    promote_kin,
    set_appable,
    set_life_status,
    set_personal_holder,
)
from world.societies.houses.constants import HoldingChoice, KinLink, LifeStatus, TitleTier
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.services import HousesServiceError
from world.societies.models import Organization


class _Realm(TestCase):
    @classmethod
    def setUpTestData(cls):
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


class CreateFamilyTests(_Realm):
    def test_commoner_family_alone_makes_no_organization(self):
        made = create_family(kind=self.commoners, name="Teale", realm=self.realm)
        self.assertIsNone(made.organization)
        self.assertIsNone(made.title)
        self.assertEqual(made.family.name, "Teale")
        self.assertEqual(made.family.origin_realm, self.realm)
        self.assertFalse(Organization.objects.filter(family=made.family).exists())

    def test_blank_or_taken_name_refuses(self):
        with self.assertRaises(HousesServiceError):
            create_family(kind=self.commoners, name="  ", realm=self.realm)
        create_family(kind=self.commoners, name="Teale", realm=self.realm)
        with self.assertRaises(HousesServiceError):
            create_family(kind=self.commoners, name="Teale", realm=self.realm)

    def test_noble_kind_without_template_refuses(self):
        with self.assertRaises(HousesServiceError) as ctx:
            create_family(kind=self.noble, name="Katta", realm=self.realm)
        self.assertIn("family type", ctx.exception.user_message)

    def test_noble_with_holding_creates_domain_title_and_holder(self):
        kathryn = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.STANDING
        )
        made = create_family(
            kind=self.noble,
            name="Katta",
            realm=self.realm,
            template=self.template,
            holding=HoldingChoice.CREATE,
            title_tier=TitleTier.DUCHY,
            title_name="Duchy of Katta",
            parent_title=self.throne,
            holder=kathryn,
        )
        self.assertIsNotNone(made.organization)
        self.assertEqual(made.organization.family, made.family)
        self.assertEqual(made.title.house, made.organization)
        self.assertEqual(made.title.holder, kathryn)
        self.assertFalse(made.title.is_claimable)
        membership = FamilyMembership.objects.get(kinsperson=kathryn, family=made.family)
        self.assertEqual(membership.basis, MembershipBasis.FOUNDING)

    def test_vacant_title_takes_an_unclaimed_rung(self):
        vacant = plant_rung(
            realm=self.realm, tier=TitleTier.COUNTY, name="Varrow", parent_title=self.throne
        )
        self.assertTrue(vacant.is_claimable)
        made = create_family(
            kind=self.noble,
            name="Varrow",
            realm=self.realm,
            template=self.template,
            holding=HoldingChoice.VACANT,
            parent_title=vacant,
        )
        vacant.refresh_from_db()
        self.assertEqual(vacant.house, made.organization)
        self.assertFalse(vacant.is_claimable)

    def test_vacant_title_in_another_realm_refuses_and_writes_nothing(self):
        other = RealmFactory(name="Inferna")
        vacant = plant_rung(realm=other, tier=TitleTier.COUNTY, name="Elsewhere")
        with self.assertRaises(HousesServiceError):
            create_family(
                kind=self.noble,
                name="Varrow",
                realm=self.realm,
                template=self.template,
                holding=HoldingChoice.VACANT,
                parent_title=vacant,
            )
        self.assertFalse(Family.objects.filter(name="Varrow").exists())
        self.assertFalse(Organization.objects.filter(name="House Varrow").exists())

    def test_held_title_refuses_as_vacant(self):
        with self.assertRaises(HousesServiceError):
            create_family(
                kind=self.noble,
                name="Usurper",
                realm=self.realm,
                template=self.template,
                holding=HoldingChoice.VACANT,
                parent_title=self.throne,
            )


class FoundOrganizationTests(_Realm):
    def test_attaches_to_the_existing_family(self):
        family = FamilyFactory(name="Teale", kind=self.commoners, origin_realm=self.realm)
        KinspersonFactory(name="Old Teale", family=family)
        org = found_organization(family=family, template=self.template)
        self.assertEqual(org.family, family)
        self.assertEqual(Family.objects.filter(name="Teale").count(), 1)
        with self.assertRaises(HousesServiceError):
            found_organization(family=family, template=self.template)


class CreateKinTests(_Realm):
    def test_needs_only_a_family(self):
        family = FamilyFactory(name="Teale", kind=self.commoners)
        gender = GenderFactory()
        node = create_kin(
            family=family, name="Mara Teale", tier=DefinitionTier.STANDING, gender=gender, age=40
        )
        self.assertEqual(node.family, family)
        self.assertEqual(node.definition_tier, DefinitionTier.STANDING)
        self.assertEqual(node.age, 40)
        self.assertEqual(FamilyMembership.objects.get(kinsperson=node).basis, MembershipBasis.BORN)
        self.assertFalse(Organization.objects.filter(family=family).exists())

    def test_sheeted_or_pc_tier_refuses(self):
        family = FamilyFactory(name="Teale", kind=self.commoners)
        for tier in (DefinitionTier.SHEETED, DefinitionTier.PC):
            with self.assertRaises(HousesServiceError):
                create_kin(family=family, name="X", tier=tier)


class LinkKinTests(_Realm):
    def setUp(self):
        self.katta = FamilyFactory(name="Katta", kind=self.noble)
        self.varrow = FamilyFactory(name="Varrow", kind=self.commoners)
        self.mother = KinspersonFactory(name="Mother mar Katta", family=self.katta)
        self.kathryn = KinspersonFactory(name="Kathryn mar Katta", family=self.katta)
        self.varrow_man = KinspersonFactory(name="A man of Varrow", family=self.varrow)

    def test_parent_and_child_links(self):
        edge = link_kin(node=self.kathryn, other=self.mother, link=KinLink.PARENT)
        self.assertEqual((edge.child, edge.parent), (self.kathryn, self.mother))
        edge2 = link_kin(node=self.mother, other=self.varrow_man, link=KinLink.CHILD)
        self.assertEqual((edge2.child, edge2.parent), (self.varrow_man, self.mother))

    def test_spouse_across_families_is_one_union_and_a_married_in_membership(self):
        kind = UnionKindFactory(name="Marriage")
        union = link_kin(
            node=self.mother, other=self.varrow_man, link=KinLink.SPOUSE, union_kind=kind
        )
        self.assertEqual(Union.objects.count(), 1)
        self.assertEqual(set(union.members.all()), {self.mother, self.varrow_man})
        membership = FamilyMembership.objects.get(kinsperson=self.varrow_man, family=self.katta)
        self.assertEqual(membership.basis, MembershipBasis.MARRIED_IN)
        self.assertFalse(membership.is_primary)
        self.varrow_man.refresh_from_db()
        self.assertEqual(self.varrow_man.family, self.varrow)

    def test_secret_spouse_and_missing_kind(self):
        kind = UnionKindFactory(name="Concubinage", confers_wedlock=False)
        union = link_kin(
            node=self.mother,
            other=self.varrow_man,
            link=KinLink.SPOUSE,
            union_kind=kind,
            is_public_record=False,
        )
        self.assertFalse(union.is_public_record)
        self.assertFalse(
            FamilyMembership.objects.filter(kinsperson=self.varrow_man, family=self.katta).exists()
        )
        with self.assertRaises(HousesServiceError):
            link_kin(node=self.mother, other=self.varrow_man, link=KinLink.SPOUSE)

    def test_self_and_bad_link_refuse(self):
        with self.assertRaises(HousesServiceError):
            link_kin(node=self.kathryn, other=self.kathryn, link=KinLink.PARENT)
        with self.assertRaises(HousesServiceError):
            link_kin(node=self.kathryn, other=self.mother, link="cousin")


class CorrectParentageTests(_Realm):
    def test_replaces_the_parent_and_keeps_the_rest(self):
        child = KinspersonFactory(name="Child")
        wrong = KinspersonFactory(name="Wrong")
        right = KinspersonFactory(name="Right")
        edge = ParentageEdgeFactory(child=child, parent=wrong, is_public_record=False)
        fixed = correct_parentage(edge=edge, new_parent=right)
        self.assertFalse(ParentageEdge.objects.filter(pk=edge.pk).exists())
        self.assertEqual((fixed.child, fixed.parent), (child, right))
        self.assertFalse(fixed.is_public_record)
        with self.assertRaises(HousesServiceError):
            correct_parentage(edge=fixed, new_parent=child)


class SetLifeStatusTests(_Realm):
    def test_rip_accurate_and_inaccurate(self):
        node = KinspersonFactory(name="Father")
        set_life_status(node=node, status=LifeStatus.RIP, obituary="Fell at the ford.")
        node.refresh_from_db()
        self.assertTrue(node.is_deceased)
        self.assertTrue(node.believed_deceased)
        self.assertFalse(node.is_missing)
        self.assertEqual(node.obituary, "Fell at the ford.")
        set_life_status(node=node, status=LifeStatus.RIP, record_accurate=False)
        node.refresh_from_db()
        self.assertTrue(node.is_deceased)
        self.assertFalse(node.believed_deceased)

    def test_missing_alive_and_believed_dead_while_living(self):
        node = KinspersonFactory(name="Heir")
        set_life_status(node=node, status=LifeStatus.MISSING)
        node.refresh_from_db()
        self.assertTrue(node.is_missing)
        self.assertFalse(node.is_deceased)
        set_life_status(node=node, status=LifeStatus.ALIVE, record_accurate=False)
        node.refresh_from_db()
        self.assertFalse(node.is_missing)
        self.assertFalse(node.is_deceased)
        self.assertTrue(node.believed_deceased)
        with self.assertRaises(HousesServiceError):
            set_life_status(node=node, status="gone")

    def test_pc_death_refuses(self):
        node = KinspersonFactory(name="A PC", definition_tier=DefinitionTier.PC)
        with self.assertRaises(HousesServiceError):
            set_life_status(node=node, status=LifeStatus.RIP)
        set_life_status(node=node, status=LifeStatus.ALIVE, obituary="")


class PromoteKinTests(_Realm):
    def test_tier_only_rises_and_pc_is_locked(self):
        staff = AccountFactory(username="staffer", is_staff=True)
        node = KinspersonFactory(name="Kathryn", definition_tier=DefinitionTier.STANDING)
        with self.assertRaises(HousesServiceError):
            promote_kin(node=node, tier=DefinitionTier.FUNCTIONARY, gm_account=staff)
        with self.assertRaises(HousesServiceError):
            promote_kin(node=node, tier=DefinitionTier.PC, gm_account=staff)
        pc = KinspersonFactory(name="A PC", definition_tier=DefinitionTier.PC)
        with self.assertRaises(HousesServiceError):
            promote_kin(node=pc, tier=DefinitionTier.SHEETED, gm_account=staff)

    def test_functionary_to_standing(self):
        staff = AccountFactory(username="staffer", is_staff=True)
        node = KinspersonFactory(name="Steward", definition_tier=DefinitionTier.FUNCTIONARY)
        promote_kin(node=node, tier=DefinitionTier.STANDING, gm_account=staff)
        node.refresh_from_db()
        self.assertEqual(node.definition_tier, DefinitionTier.STANDING)

    def test_sheeted_mints_a_story_npc_and_binds_it(self):
        staff = AccountFactory(username="staffer", is_staff=True)
        node = KinspersonFactory(
            name="Kathryn mar Katta", definition_tier=DefinitionTier.STANDING, is_appable=True
        )
        promote_kin(node=node, tier=DefinitionTier.SHEETED, gm_account=staff)
        node.refresh_from_db()
        self.assertEqual(node.definition_tier, DefinitionTier.SHEETED)
        self.assertIsNotNone(node.sheet)
        self.assertFalse(node.is_appable)
        self.assertEqual(node.sheet.personas.first().name, "Kathryn mar Katta")


class AttachSheetTests(_Realm):
    def test_staff_sheet_makes_sheeted(self):
        node = KinspersonFactory(name="Kathryn", definition_tier=DefinitionTier.STANDING)
        sheet = CharacterSheetFactory()
        attach_sheet(node=node, sheet=sheet)
        node.refresh_from_db()
        self.assertEqual(node.sheet, sheet)
        self.assertEqual(node.definition_tier, DefinitionTier.SHEETED)
        with self.assertRaises(HousesServiceError):
            attach_sheet(node=node, sheet=CharacterSheetFactory())
        other = KinspersonFactory(name="Other")
        with self.assertRaises(HousesServiceError):
            attach_sheet(node=other, sheet=sheet)


class SetAppableTests(_Realm):
    def test_constraints_and_sheeted_refusal(self):
        node = KinspersonFactory(name="Sister")
        woman = GenderFactory()
        set_appable(
            node=node,
            appable=True,
            age_min=18,
            age_max=30,
            allowed_genders=[woman],
            name_locked=True,
        )
        node.refresh_from_db()
        self.assertTrue(node.is_appable)
        self.assertEqual((node.age_min, node.age_max), (18, 30))
        self.assertTrue(node.name_locked)
        self.assertEqual(list(node.allowed_genders.all()), [woman])
        with self.assertRaises(HousesServiceError):
            set_appable(node=node, appable=True, age_min=40, age_max=30)
        sheeted = KinspersonFactory(name="Sheeted", sheet=CharacterSheetFactory())
        with self.assertRaises(HousesServiceError):
            set_appable(node=sheeted, appable=True)
        set_appable(node=sheeted, appable=False)


class SetPersonalHolderTests(_Realm):
    def test_holder_must_be_of_the_holding_family(self):
        outsider = KinspersonFactory(name="Outsider")
        with self.assertRaises(HousesServiceError):
            set_personal_holder(title=self.throne, node=outsider)
        royal = KinspersonFactory(name="Royal")
        add_membership(kinsperson=royal, family=self.crown.family, basis=MembershipBasis.BORN)
        set_personal_holder(title=self.throne, node=royal)
        self.throne.refresh_from_db()
        self.assertEqual(self.throne.holder, royal)
        vacant = plant_rung(realm=self.realm, tier=TitleTier.COUNTY, name="Nowhere")
        with self.assertRaises(HousesServiceError):
            set_personal_holder(title=vacant, node=royal)
