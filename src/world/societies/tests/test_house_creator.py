"""Tests for the CG house creator (#1884 Phase D): gates, review, materialization."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.areas.factories import AreaFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.models import Family, FamilyMembership, KinSlotPool, Kinsperson
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import HouseClaimStatus, TitleTier
from world.societies.houses.creator import (
    approve_house_claim,
    claimable_titles,
    materialize_house_claim,
    reject_house_claim,
    submit_house_claim,
)
from world.societies.houses.models import (
    Domain,
    FealtyEdge,
    HoldingKind,
    HouseTemplate,
    SuccessionLaw,
    Title,
)
from world.societies.houses.services import HousesServiceError
from world.societies.models import OrganizationMembership


class HouseCreatorTestData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crown = OrganizationFactory(name="The Crown")
        cls.realm = cls.crown.society.realm
        cls.law = SuccessionLaw.objects.create(
            name="Charter Primogeniture", derivation="primogeniture_wedlock"
        )
        cls.farmland = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        cls.template = HouseTemplate.objects.create(
            name="Barony Charter",
            realm=cls.realm,
            family_type=Family.FamilyType.NOBLE,
            society=cls.crown.society,
            liege=cls.crown,
            default_succession_law=cls.law,
            mercy_min=-2,
            mercy_max=2,
        )
        cls.template.holdings.add(cls.farmland)
        cls.seat = Domain.objects.create(area=AreaFactory(), name="Thornmere", owner_org=cls.crown)
        cls.title = Title.objects.create(
            name="Barony of Thornmere",
            tier=TitleTier.BARONY,
            realm=cls.realm,
            seat_domain=cls.seat,
            is_claimable=True,
        )
        cls.draft = CharacterDraftFactory()

    def _submit(self, **overrides):
        kwargs = {
            "draft": self.draft,
            "title": self.title,
            "template": self.template,
            "house_name": "Thornwood",
            "backstory": "An old marcher line, quietly holding the fens for the crown.",
        }
        kwargs.update(overrides)
        return submit_house_claim(**kwargs)


class GateTests(HouseCreatorTestData):
    """The automated thematic gates refuse before staff ever look."""

    def test_valid_claim_files_pending(self):
        claim = self._submit()
        self.assertEqual(claim.status, HouseClaimStatus.PENDING)
        self.assertIn(self.title, claimable_titles(self.realm))

    def test_name_pattern_gate(self):
        with self.assertRaises(HousesServiceError):
            self._submit(house_name="thornwood of the fens")

    def test_name_collision_gate(self):
        Family.objects.create(name="Thornwood", family_type=Family.FamilyType.NOBLE)
        with self.assertRaises(HousesServiceError):
            self._submit()

    def test_principle_range_gate(self):
        with self.assertRaises(HousesServiceError):
            self._submit(principles={"mercy": 5})

    def test_empty_backstory_gate(self):
        with self.assertRaises(HousesServiceError):
            self._submit(backstory="   ")

    def test_unclaimable_title_gate(self):
        self.title.is_claimable = False
        self.title.save(update_fields=["is_claimable"])
        with self.assertRaises(HousesServiceError):
            self._submit()

    def test_one_live_claim_per_title(self):
        self._submit()
        other_draft = CharacterDraftFactory()
        with self.assertRaises(HousesServiceError):
            self._submit(draft=other_draft, house_name="Fenwick")

    def test_one_claim_per_draft(self):
        self._submit()
        with self.assertRaises(HousesServiceError):
            self._submit(house_name="Fenwick")

    def test_realm_mismatch_gate(self):
        foreign = OrganizationFactory(name="Foreign Crown")
        alien_template = HouseTemplate.objects.create(
            name="Foreign Charter",
            realm=foreign.society.realm,
            family_type=Family.FamilyType.NOBLE,
            society=foreign.society,
            liege=foreign,
            default_succession_law=self.law,
        )
        with self.assertRaises(HousesServiceError):
            self._submit(template=alien_template)


class ReviewTests(HouseCreatorTestData):
    def test_approve_and_reject_stamp_reviewer(self):
        claim = self._submit()
        reviewer = AccountFactory()
        approve_house_claim(claim, reviewer=reviewer)
        self.assertEqual(claim.status, HouseClaimStatus.APPROVED)
        self.assertEqual(claim.reviewed_by, reviewer)

        other = CharacterDraftFactory()
        second_title = Title.objects.create(
            name="Barony of Elsewhere",
            tier=TitleTier.BARONY,
            realm=self.realm,
            is_claimable=True,
        )
        claim2 = submit_house_claim(
            draft=other,
            title=second_title,
            template=self.template,
            house_name="Fenwick",
            backstory="A lesser line.",
        )
        reject_house_claim(claim2, reviewer=reviewer, note="Too thin.")
        self.assertEqual(claim2.status, HouseClaimStatus.REJECTED)
        self.assertEqual(claim2.review_note, "Too thin.")


class MaterializationTests(HouseCreatorTestData):
    def test_unapproved_claim_refuses(self):
        claim = self._submit()
        sheet = CharacterSheetFactory()
        with self.assertRaises(HousesServiceError):
            materialize_house_claim(claim, sheet=sheet)

    def test_full_package_materializes(self):
        claim = self._submit(principles={"mercy": 2})
        approve_house_claim(claim, reviewer=AccountFactory())
        sheet = CharacterSheetFactory()
        org = materialize_house_claim(claim, sheet=sheet)

        # Org + family + principles override.
        self.assertEqual(org.name, "House Thornwood")
        family = Family.objects.get(name="Thornwood")
        self.assertEqual(org.family, family)
        self.assertEqual(org.mercy_override, 2)
        self.assertEqual(org.default_succession_law, self.law)
        self.assertTrue(org.ranks.exists())

        # Fealty to the template's liege.
        self.assertEqual(FealtyEdge.objects.get(vassal=org).liege, self.crown)

        # Title seated on the founder, no longer claimable.
        self.title.refresh_from_db()
        founder = Kinsperson.objects.get(sheet=sheet)
        self.assertEqual(self.title.house, org)
        self.assertEqual(self.title.holder, founder)
        self.assertFalse(self.title.is_claimable)
        self.assertTrue(
            FamilyMembership.objects.filter(
                kinsperson=founder, family=family, basis="founding"
            ).exists()
        )

        # Seat domain reassigned + holdings package materialized.
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.owner_org, org)
        holding = self.seat.holdings.get()
        self.assertEqual(holding.income_stream.organization, org)

        # Sheet surname + kin slot pool for future kin app-ins.
        sheet.refresh_from_db()
        self.assertEqual(sheet.family, family)
        pool = KinSlotPool.objects.get(family=family)
        self.assertEqual(pool.count_remaining, 3)

        # No accidental auto-membership rows beyond the rank ladder.
        self.assertEqual(OrganizationMembership.objects.filter(organization=org).count(), 0)

    def test_seed_creator_rows_exist(self):
        from world.seeds.houses import (
            CLAIMABLE_TITLE_NAME,
            TEMPLATE_NAME,
            seed_houses_demo,
        )

        seed_houses_demo()
        seed_houses_demo()  # idempotent
        title = Title.objects.get(name=CLAIMABLE_TITLE_NAME)
        self.assertTrue(title.is_claimable)
        self.assertIsNotNone(title.seat_domain)
        template = HouseTemplate.objects.get(name=TEMPLATE_NAME)
        self.assertEqual(template.realm, title.realm)
        self.assertTrue(template.holdings.exists())
