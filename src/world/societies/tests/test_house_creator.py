"""Tests for the CG house creator (#1884 Phase D): gates, review, materialization."""

from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.areas.models import Area
from world.character_creation.factories import (
    CharacterDraftFactory,
    OriginTemplateFactory,
    StartingAreaFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.models import LocationOwnership
from world.roster.constants import NOBLE_KIND_NAME, DefinitionTier, MembershipBasis
from world.roster.factories import FamilyFactory, FamilyKindFactory, UnionKindFactory
from world.roster.models import (
    Family,
    FamilyMembership,
    KinSlotPool,
    Kinsperson,
    ParentageEdge,
    Union,
)
from world.societies.factories import OrganizationFactory
from world.societies.houses.almanach import (
    _rung_area,
    batch_unclaimed,
    name_rung,
    plant_rung,
    publish_house,
)
from world.societies.houses.constants import ClaimKinRelation, HouseClaimStatus, TitleTier
from world.societies.houses.creator import (
    approve_house_claim,
    claimable_titles,
    materialize_house_claim,
    reject_house_claim,
    submit_house_claim,
    templates_for_title,
)
from world.societies.houses.models import (
    Domain,
    FealtyEdge,
    HoldingKind,
    HouseTemplate,
    LandShape,
    SuccessionLaw,
    Title,
)
from world.societies.houses.services import HousesServiceError
from world.societies.houses.types import ClaimKinDraft, ClaimLandDraft
from world.societies.models import OrganizationMembership, Vacancy


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
        cls.crown_county = plant_rung(
            realm=cls.realm, tier=TitleTier.COUNTY, name="Thornshire", held_by=cls.crown
        )
        publish_house(cls.crown)
        cls.title = plant_rung(
            realm=cls.realm,
            tier=TitleTier.BARONY,
            name="Thornmere",
            parent_title=cls.crown_county,
        )
        cls.seat = cls.title.seat_domain
        cls.draft = CharacterDraftFactory()
        cls.draft.selected_origin_template = OriginTemplateFactory()
        cls.draft.save(update_fields=["selected_origin_template"])

        # Founder finalize fixtures (#3983 Plan B Task 2): Fervor's own
        # top-level duchy chain (a duchy can't nest inside the county above,
        # #3983's containment rule — the org's fealty to the crown comes
        # from the template's own ``liege``, not area containment), a loose
        # barony batch-minted beneath its county, a CITY capital, and the
        # vocabulary rows kin placement needs.
        cls.fervor = plant_rung(realm=cls.realm, tier=TitleTier.DUCHY, name="Fervor")
        cls.arsura = Title.objects.get(tier=TitleTier.COUNTY, seat_domain=cls.fervor.seat_domain)
        cls.ascua = Title.objects.get(tier=TitleTier.BARONY, seat_domain=cls.fervor.seat_domain)
        name_rung(cls.arsura, "Arsura")
        name_rung(cls.ascua, "Ascua")
        cls.undefined_barony = batch_unclaimed(
            parent_title=cls.arsura, tier=TitleTier.BARONY, count=1
        )[0]
        cls.coast = LandShape.objects.create(name="Coast")
        cls.solano_family = FamilyFactory(name="Solano")
        UnionKindFactory()
        cls.capital = AreaFactory(
            name="Piropa City", level=AreaLevel.CITY, realm=cls.realm, is_capital=True
        )
        cls.starting_area = StartingAreaFactory(name="Founder Start", realm=cls.realm)
        cls.draft.selected_area = cls.starting_area
        cls.draft.save(update_fields=["selected_area"])

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
        # A dedicated, method-local title — never the class-shared
        # ``self.title``: ``assign_holder`` (called inside materialize)
        # mutates the row through its OWN ``_require_chain_top``-fetched
        # (identity-mapped, cache-shared) instance, not this test's deep
        # copy, and that shared instance's mutation would otherwise outlive
        # this test's DB rollback and poison ``self.title`` for
        # ``test_unapproved_claim_refuses`` (idmapper rollback-staleness,
        # ``reference_idmapper_rollback_staleness.md`` — the same pattern
        # ``test_almanach_ladder.py`` avoids by never sharing a
        # materialized/assign_holder'd title across test methods).
        own_title = plant_rung(
            realm=self.realm,
            tier=TitleTier.BARONY,
            name="Owncastle",
            parent_title=self.crown_county,
        )
        own_seat = own_title.seat_domain
        claim = self._submit(principles={"mercy": 2}, title=own_title)
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
        own_title.refresh_from_db()
        founder = Kinsperson.objects.get(sheet=sheet)
        self.assertEqual(own_title.house, org)
        self.assertEqual(own_title.holder, founder)
        self.assertFalse(own_title.is_claimable)
        self.assertTrue(
            FamilyMembership.objects.filter(
                kinsperson=founder, family=family, basis="founding"
            ).exists()
        )

        # Seat domain reassigned + holdings package materialized.
        own_seat = Domain.objects.get(pk=own_seat.pk)
        self.assertEqual(own_seat.owner_org, org)
        holding = own_seat.holdings.get()
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


class FounderJourneyTests(HouseCreatorTestData):
    """The founder claims Fervor (#3983 Plan B): kin placement service,
    claim grants, nested submit rows, and materialize writing the whole
    rows table."""

    def test_founder_claims_fervor(self) -> None:  # noqa: PLR0915 — one full journey, one test
        reviewer = AccountFactory()
        sheet = CharacterSheetFactory()

        claim = submit_house_claim(
            draft=self.draft,
            title=self.fervor,
            template=self.template,
            house_name="Candela",
            backstory="x",
            words="w",
            colors="c",
            sigil_description="s",
            founder_relation=ClaimKinRelation.CHILD,
            founder_is_heir=True,
            kin=[
                ClaimKinDraft(name="Estuosa", relation=ClaimKinRelation.HEAD),
                ClaimKinDraft(name="Fiamma", relation=ClaimKinRelation.MOTHER, is_deceased=True),
                ClaimKinDraft(
                    name="Dario",
                    relation=ClaimKinRelation.SPOUSE,
                    born_into_id=self.solano_family.pk,
                ),
                ClaimKinDraft(name="", relation=ClaimKinRelation.CHILD),
                ClaimKinDraft(
                    name="Captain", relation=ClaimKinRelation.POSITION, is_household=True
                ),
            ],
            lands=[
                ClaimLandDraft(
                    title_id=self.fervor.pk,
                    description="the duchy",
                    land_shape_names=("Coast",),
                ),
                ClaimLandDraft(
                    title_id=self.ascua.pk,
                    description="the seat",
                    hall_name="the Torre Accesa",
                ),
                ClaimLandDraft(
                    title_id=self.undefined_barony.pk, land_name="Brasa", description="named"
                ),
            ],
            estate_name="Casa Candela",
            estate_description="the townhouse",
        )

        # A second application on Fervor while this one is pending is refused.
        with self.assertRaises(HousesServiceError):
            submit_house_claim(
                draft=CharacterDraftFactory(),
                title=self.fervor,
                template=self.template,
                house_name="Candelabra",
                backstory="y",
                words="w",
                colors="c",
                sigil_description="s",
            )

        approve_house_claim(claim, reviewer=reviewer)
        org = materialize_house_claim(claim, sheet=sheet)

        # The chain plus the loose barony extra are all seated on the house.
        # Fresh fetches, never ``refresh_from_db()`` — a no-op on
        # SharedMemoryModel (idmapper rollback-staleness corollary): the
        # nested ``@transaction.atomic`` seams inside materialize mutate
        # their OWN fetched instances, never these already-held ones.
        self.fervor.refresh_from_db()
        assert self.fervor.house_id == org.pk
        arsura = Title.objects.get(pk=self.arsura.pk)
        ascua = Title.objects.get(pk=self.ascua.pk)
        assert arsura.house_id == org.pk
        assert ascua.house_id == org.pk
        undefined = Title.objects.get(pk=self.undefined_barony.pk)
        assert undefined.house_id == org.pk
        assert undefined.name == "Brasa"

        edge = FealtyEdge.objects.get(vassal=org)
        assert edge.liege_id == self.crown.pk
        assert edge.obligation is not None

        # Land writing materialized onto the right rungs' domains.
        ascua_domain = Domain.objects.get(area=_rung_area(self.ascua))
        assert ascua_domain.hall is not None
        assert ascua_domain.hall.name == "the Torre Accesa"
        fervor_domain = Domain.objects.get(area=_rung_area(self.fervor))
        assert fervor_domain.description == "the duchy"
        assert [s.name for s in fervor_domain.land_shapes.all()] == ["Coast"]

        # The HEAD row holds the title.
        head = Kinsperson.objects.get(name="Estuosa")
        self.fervor.refresh_from_db()
        assert self.fervor.holder_id == head.pk

        # Kin placement: Fiamma is Estuosa's parent; Dario married in.
        fiamma = Kinsperson.objects.get(name="Fiamma")
        assert ParentageEdge.objects.filter(child=head, parent=fiamma).exists()
        dario = Kinsperson.objects.get(name="Dario")
        assert Union.objects.filter(members=head).filter(members=dario).exists()
        solano_membership = FamilyMembership.objects.get(
            kinsperson=dario, family=self.solano_family
        )
        assert solano_membership.basis == MembershipBasis.BORN
        assert solano_membership.is_primary is False
        house_membership = FamilyMembership.objects.get(kinsperson=dario, family=org.family)
        assert house_membership.basis == MembershipBasis.MARRIED_IN

        # The founder is placed as Estuosa and Dario's child (founder_relation=CHILD).
        founder = Kinsperson.objects.get(sheet=sheet)
        assert ParentageEdge.objects.filter(child=founder, parent=head).exists()
        assert ParentageEdge.objects.filter(child=founder, parent=dario).exists()

        # The unnamed child row materializes as an appable slot.
        # The founder is ALSO name="" (a PC node never carries a display
        # name of its own — it reads the sheet), so disambiguate on
        # ``sheet__isnull`` exactly as ``open_slots_for`` does.
        slot = Kinsperson.objects.get(name="", family=org.family, sheet__isnull=True)
        assert slot.definition_tier == DefinitionTier.NAME_ONLY
        assert slot.is_appable
        assert slot.sheet_id is None

        # The household position is a filled Vacancy, not a family member.
        captain = Kinsperson.objects.get(name="Captain")
        vacancy = Vacancy.objects.get(holder_kinsperson=captain)
        assert vacancy.name == "Household position"

        # The estate planted under the realm's capital.
        estate = Area.objects.get(name="Casa Candela")
        assert estate.parent_id == self.capital.pk
        assert LocationOwnership.objects.filter(
            area=estate, holder_organization=org, ended_at__isnull=True
        ).exists()

        assert KinSlotPool.objects.filter(family=org.family).exists()
