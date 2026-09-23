"""Tests for the CG house creator (#1884 Phase D): gates, review, materialization."""

from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory, OriginTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.constants import NOBLE_KIND_NAME
from world.roster.factories import FamilyKindFactory
from world.roster.models import Family, FamilyMembership, KinSlotPool, Kinsperson
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import plant_rung, publish_house
from world.societies.houses.constants import HouseClaimStatus, TitleTier
from world.societies.houses.creator import (
    approve_house_claim,
    claimable_titles,
    materialize_house_claim,
    reject_house_claim,
    submit_house_claim,
    templates_for_title,
)
from world.societies.houses.models import (
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
            kind=FamilyKindFactory(name=NOBLE_KIND_NAME),
            society=cls.crown.society,
            org_type=cls.crown.org_type,
            liege=cls.crown,
            default_succession_law=cls.law,
            mercy_min=-2,
            mercy_max=2,
        )
        cls.template.holdings.add(cls.farmland)
        # A real seat chain (#3983 Plan B): the crown holds a county, and an
        # unclaimed barony sits beneath it. The founder gates (chain top,
        # containment liege) need a real ancestor rung to walk to.
        crown_county = plant_rung(
            realm=cls.realm, tier=TitleTier.COUNTY, name="Thornshire", held_by=cls.crown
        )
        publish_house(cls.crown)
        cls.title = plant_rung(
            realm=cls.realm, tier=TitleTier.BARONY, name="Thornmere", parent_title=crown_county
        )
        cls.seat = cls.title.seat_domain
        cls.draft = CharacterDraftFactory()
        cls.draft.selected_origin_template = OriginTemplateFactory()
        cls.draft.save(update_fields=["selected_origin_template"])

    def _submit(self, **overrides):
        kwargs = {
            "draft": self.draft,
            "title": self.title,
            "template": self.template,
            "house_name": "Thornwood",
            "backstory": "An old marcher line, quietly holding the fens for the crown.",
            "words": "The Fens Endure",
            "colors": "russet and bog-iron grey",
            "sigil_description": "A heron statant on a black chief.",
            "lands_writeup": "Fen villages and eel weirs along the marches.",
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
        Family.objects.create(name="Thornwood", kind=FamilyKindFactory(name=NOBLE_KIND_NAME))
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
            kind=FamilyKindFactory(name=NOBLE_KIND_NAME),
            society=foreign.society,
            org_type=foreign.org_type,
            liege=foreign,
            default_succession_law=self.law,
        )
        with self.assertRaises(HousesServiceError):
            self._submit(template=alien_template)

    def test_claim_refuses_a_tier_above_the_upbringing(self):
        county_title = Title.objects.create(
            name="County of Farthing", tier=TitleTier.COUNTY, realm=self.realm, is_claimable=True
        )
        self.draft.selected_origin_template.max_claim_tier = TitleTier.BARONY
        self.draft.selected_origin_template.save(update_fields=["max_claim_tier"])
        with self.assertRaises(HousesServiceError):
            submit_house_claim(
                draft=self.draft,
                title=county_title,
                template=self.template,
                house_name="Farthing",
                backstory="x",
            )

    def test_claim_refuses_an_unpublished_liege(self):
        self.crown.published_at = None
        self.crown.save(update_fields=["published_at"])
        with self.assertRaises(HousesServiceError):
            self._submit()


class TemplatesForTitleTests(HouseCreatorTestData):
    """``templates_for_title`` prefers the title's own tier row over the
    realm's tier-less fallback (#3983)."""

    def test_templates_for_title_prefers_the_tier_row(self):
        tiered = HouseTemplate.objects.create(
            name="Baronies",
            realm=self.realm,
            tier=self.title.tier,
            kind=self.template.kind,
            org_type=self.template.org_type,
            society=self.template.society,
        )
        self.assertEqual(templates_for_title(self.title), [tiered])
        tiered.delete()
        self.assertEqual(templates_for_title(self.title), [self.template])


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
            words="Quiet Waters",
            colors="slate and reed-green",
            sigil_description="An eel naiant.",
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

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_seed_creator_rows_exist(self):
        """``realms.Realm`` is content-repo-owned (#2698); SEED_SAMPLE_CONTENT
        opts this test into the sample-seeding path so "Arx" (and everything
        downstream of it in seed_houses_demo) actually seeds."""
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
        definition = template.aspect_definitions.first()
        self.assertIsNotNone(definition)
        self.assertGreaterEqual(definition.options.filter(is_active=True).count(), 2)
        self.assertTrue(template.features.exists())
