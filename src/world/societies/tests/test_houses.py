"""Tests for the houses system (#1884): naming, recognition, succession,
fealty, pacts, domains, and the house feed."""

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.character_sheets.factories import GenderFactory
from world.currency.services import (
    accrue_income_stream,
    get_or_create_treasury,
    transfer,
)
from world.projects.constants import ProjectKind, ProjectStatus
from world.roster.constants import MembershipBasis
from world.roster.factories import (
    FamilyFactory,
    KinspersonFactory,
    ParentageEdgeFactory,
    UnionFactory,
    UnionKindFactory,
)
from world.roster.models import Family, FamilyMembership
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import (
    DomainCrisisSeverity,
    PactCommitmentKind,
    PactDissolutionReason,
    RecognitionRuleKind,
    SuccessionDerivation,
    SuccessionOrdering,
)
from world.societies.houses.models import (
    DomainCrisis,
    HoldingKind,
    HouseRecognitionRule,
    MarriagePact,
    NobiliaryParticle,
    SuccessionLaw,
    Title,
)
from world.societies.houses.services import (
    CommitmentSpec,
    HousesServiceError,
    acknowledge_into_family,
    add_holding,
    breach_commitment,
    complete_domain_improvement,
    create_domain,
    derive_succession_candidates,
    dissolve_pact,
    full_display_name,
    handle_death_for_pacts,
    liege_chain_of,
    recognize_birth,
    sign_marriage_pact,
    start_domain_improvement,
    swear_fealty,
    vassals_of,
)
from world.traits.factories import CheckOutcomeFactory


def _make_house(family_name: str = "Velaryon"):
    family = FamilyFactory(name=family_name, family_type=Family.FamilyType.NOBLE)
    org = OrganizationFactory(name=f"House {family_name}", family=family)
    return family, org


class DisplayNameTests(TestCase):
    """First + particle + House naming (#1884)."""

    def test_particle_renders_between_first_and_house(self):
        family, org = _make_house("Argente")
        NobiliaryParticle.objects.create(
            realm=org.society.realm,
            family_type=Family.FamilyType.NOBLE,
            particle="du",
        )
        person = KinspersonFactory(name="Lysande Argente", family=family)
        self.assertEqual(full_display_name(person), "Lysande du Argente")

    def test_no_particle_row_renders_plain(self):
        family, _org = _make_house("Umbra")
        person = KinspersonFactory(name="Kael Umbra", family=family)
        self.assertEqual(full_display_name(person), "Kael Umbra")

    def test_unhoused_person_keeps_bare_name(self):
        person = KinspersonFactory(name="Nix")
        self.assertEqual(full_display_name(person), "Nix")


class RecognitionTests(TestCase):
    """Realm recognition rules applied to births (#1884)."""

    @classmethod
    def setUpTestData(cls):
        cls.female = GenderFactory(key="female")
        cls.male = GenderFactory(key="male")
        cls.family, cls.org = _make_house()
        cls.realm = cls.org.society.realm
        cls.wedlock_kind = UnionKindFactory(name="Marriage", confers_wedlock=True)

    def _birth(self, *, mother=None, father=None, union=None):
        child = KinspersonFactory(name="Newborn")
        if mother is not None:
            ParentageEdgeFactory(child=child, parent=mother, born_within_union=union)
        if father is not None:
            ParentageEdgeFactory(child=child, parent=father, born_within_union=union)
        return child

    def test_matrilineal_auto_recognizes_in_wedlock(self):
        HouseRecognitionRule.objects.create(
            realm=self.realm, kind=RecognitionRuleKind.MATRILINEAL_AUTO_WEDLOCK
        )
        mother = KinspersonFactory(gender=self.female, family=self.family)
        spouse = KinspersonFactory(gender=self.male)
        union = UnionFactory(kind=self.wedlock_kind, members=[mother, spouse])
        child = self._birth(mother=mother, father=spouse, union=union)
        membership = recognize_birth(child)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.basis, MembershipBasis.BORN)
        child.refresh_from_db()
        self.assertEqual(child.family_id, self.family.pk)

    def test_matrilineal_out_of_wedlock_is_mothers_option(self):
        HouseRecognitionRule.objects.create(
            realm=self.realm, kind=RecognitionRuleKind.MATRILINEAL_AUTO_WEDLOCK
        )
        HouseRecognitionRule.objects.create(
            realm=self.realm, kind=RecognitionRuleKind.MOTHER_OPTION_OUT_OF_WEDLOCK
        )
        mother = KinspersonFactory(gender=self.female, family=self.family)
        child = self._birth(mother=mother)
        self.assertIsNone(recognize_birth(child))
        # The option, exercised:
        membership = acknowledge_into_family(child, self.family)
        self.assertEqual(membership.basis, MembershipBasis.LEGITIMIZED)

    def test_patrilineal_auto_recognizes_in_wedlock(self):
        HouseRecognitionRule.objects.create(
            realm=self.realm, kind=RecognitionRuleKind.PATRILINEAL_AUTO_WEDLOCK
        )
        father = KinspersonFactory(gender=self.male, family=self.family)
        wife = KinspersonFactory(gender=self.female)
        union = UnionFactory(kind=self.wedlock_kind, members=[father, wife])
        child = self._birth(mother=wife, father=father, union=union)
        membership = recognize_birth(child)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.family_id, self.family.pk)

    def test_consort_children_of_titleholder_recognized_without_wedlock(self):
        HouseRecognitionRule.objects.create(
            realm=self.realm, kind=RecognitionRuleKind.CONSORT_CHILDREN_ENNOBLED
        )
        matriarch = KinspersonFactory(gender=self.female, family=self.family)
        Title.objects.create(
            name="Countess of Emberfall",
            tier="county",
            realm=self.realm,
            house=self.org,
            holder=matriarch,
        )
        consort = KinspersonFactory(gender=self.male)
        child = self._birth(mother=matriarch, father=consort)
        membership = recognize_birth(child)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.family_id, self.family.pk)

    def test_already_familied_child_untouched(self):
        other = FamilyFactory(name="Otherkin")
        child = KinspersonFactory(family=other)
        self.assertIsNone(recognize_birth(child))


class SuccessionTests(TestCase):
    """Candidate derivation per law (#1884)."""

    @classmethod
    def setUpTestData(cls):
        cls.female = GenderFactory(key="female")
        cls.male = GenderFactory(key="male")
        cls.family, cls.org = _make_house("Luxen")
        cls.realm = cls.org.society.realm
        cls.wedlock_kind = UnionKindFactory(name="Marriage", confers_wedlock=True)

    def _title(self, law):
        return Title.objects.create(
            name=f"Seat of {law.name}",
            tier="duchy",
            realm=self.realm,
            house=self.org,
            succession_law=law,
        )

    def test_primogeniture_wedlock_picks_eldest_legitimate(self):
        law = SuccessionLaw.objects.create(
            name="Luxen Primogeniture",
            derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
            ordering_rule=SuccessionOrdering.ELDEST,
            require_wedlock=True,
        )
        title = self._title(law)
        holder = KinspersonFactory(family=self.family, age=60)
        spouse = KinspersonFactory()
        union = UnionFactory(kind=self.wedlock_kind, members=[holder, spouse])
        title.holder = holder
        title.save(update_fields=["holder"])
        eldest = KinspersonFactory(name="Eldest", age=30)
        younger = KinspersonFactory(name="Younger", age=20)
        bastard = KinspersonFactory(name="Bastard", age=40)
        ParentageEdgeFactory(child=eldest, parent=holder, born_within_union=union)
        ParentageEdgeFactory(child=younger, parent=holder, born_within_union=union)
        ParentageEdgeFactory(child=bastard, parent=holder)  # out of wedlock
        candidates = derive_succession_candidates(title)
        self.assertEqual([c.name for c in candidates], ["Eldest", "Younger"])

    def test_chosen_heir_law(self):
        heir = KinspersonFactory(name="Chosen")
        law = SuccessionLaw.objects.create(
            name="Ariwn Choice",
            derivation=SuccessionDerivation.CHOSEN_HEIR,
            chosen_heir=heir,
        )
        title = self._title(law)
        self.assertEqual(derive_succession_candidates(title), [heir])

    def test_tanistry_returns_family_pool(self):
        law = SuccessionLaw.objects.create(
            name="Imperial Tanistry",
            derivation=SuccessionDerivation.TANISTRY_ELECTION,
        )
        title = self._title(law)
        from world.roster.services.kinship import add_membership

        a = KinspersonFactory(name="Elector A")
        b = KinspersonFactory(name="Elector B")
        add_membership(kinsperson=a, family=self.family, basis=MembershipBasis.BORN)
        add_membership(kinsperson=b, family=self.family, basis=MembershipBasis.BORN)
        pool = derive_succession_candidates(title)
        self.assertEqual({p.name for p in pool}, {"Elector A", "Elector B"})

    def test_deceased_candidates_excluded(self):
        law = SuccessionLaw.objects.create(
            name="Plain Eldest",
            derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK,
        )
        title = self._title(law)
        holder = KinspersonFactory(family=self.family, age=70)
        title.holder = holder
        title.save(update_fields=["holder"])
        dead = KinspersonFactory(name="Dead", age=50, is_deceased=True)
        living = KinspersonFactory(name="Living", age=40)
        ParentageEdgeFactory(child=dead, parent=holder)
        ParentageEdgeFactory(child=living, parent=holder)
        self.assertEqual([c.name for c in derive_succession_candidates(title)], ["Living"])

    def test_title_override_beats_house_default(self):
        house_law = SuccessionLaw.objects.create(
            name="House Default", derivation=SuccessionDerivation.PRIMOGENITURE_WEDLOCK
        )
        self.org.default_succession_law = house_law
        self.org.save(update_fields=["default_succession_law"])
        heir = KinspersonFactory(name="Named")
        override = SuccessionLaw.objects.create(
            name="Imperial Override",
            derivation=SuccessionDerivation.CHOSEN_HEIR,
            chosen_heir=heir,
        )
        title = self._title(override)
        self.assertEqual(derive_succession_candidates(title), [heir])


class FealtyTests(TestCase):
    """The realm tree (#1884)."""

    def test_swear_walk_and_cycle_refusal(self):
        crown = OrganizationFactory(name="The Crown")
        duchy = OrganizationFactory(name="Duchy Ash")
        county = OrganizationFactory(name="County Brack")
        swear_fealty(vassal=duchy, liege=crown)
        swear_fealty(vassal=county, liege=duchy)
        self.assertEqual(vassals_of(crown), [duchy])
        self.assertEqual(set(vassals_of(crown, recursive=True)), {duchy, county})
        self.assertEqual(liege_chain_of(county), [duchy, crown])
        with self.assertRaises(HousesServiceError):
            swear_fealty(vassal=crown, liege=county)


class PactTests(TestCase):
    """Marriage pacts: coded commitments fire; the pact dies with a spouse."""

    @classmethod
    def setUpTestData(cls):
        cls.senior_family, cls.senior = _make_house("Imperial")
        cls.junior_family, cls.junior = _make_house("Ridgeback")
        cls.wedlock = UnionKindFactory(name="Marriage", confers_wedlock=True)
        cls.bride = KinspersonFactory(name="Imperial Daughter", family=cls.senior_family)
        cls.groom = KinspersonFactory(name="Gifted Warrior", family=cls.junior_family)
        cls.union = UnionFactory(kind=cls.wedlock, members=[cls.bride, cls.groom])

    def test_dowry_moves_treasury_coin_at_signing(self):
        transfer(amount=5000, reason="seed", to_treasury=get_or_create_treasury(self.senior))
        sign_marriage_pact(
            union=self.union,
            senior_house=self.senior,
            junior_house=self.junior,
            commitments=[CommitmentSpec(kind=PactCommitmentKind.DOWRY, amount=3000)],
        )
        self.assertEqual(get_or_create_treasury(self.senior).balance, 2000)
        self.assertEqual(get_or_create_treasury(self.junior).balance, 3000)

    def test_subsidy_materializes_obligation_and_dissolution_stops_it(self):
        pact = sign_marriage_pact(
            union=self.union,
            senior_house=self.senior,
            junior_house=self.junior,
            commitments=[CommitmentSpec(kind=PactCommitmentKind.SUBSIDY, percent=10)],
        )
        commitment = pact.commitments.get()
        self.assertIsNotNone(commitment.obligation)
        self.assertTrue(commitment.obligation.active)
        self.assertEqual(commitment.obligation.percent, 10)
        dissolve_pact(pact, reason=PactDissolutionReason.ANNULMENT)
        commitment.obligation.refresh_from_db()
        self.assertFalse(commitment.obligation.active)

    def test_residency_marries_junior_spouse_into_senior_family(self):
        sign_marriage_pact(
            union=self.union,
            senior_house=self.senior,
            junior_house=self.junior,
            commitments=[
                CommitmentSpec(kind=PactCommitmentKind.RESIDENCY, committed_person=self.groom)
            ],
        )
        self.groom.refresh_from_db()
        self.assertEqual(self.groom.family_id, self.senior_family.pk)
        membership = FamilyMembership.objects.get(
            kinsperson=self.groom, family=self.senior_family, ended_at__isnull=True
        )
        self.assertEqual(membership.basis, MembershipBasis.MARRIED_IN)

    def test_pact_dies_with_a_spouse(self):
        pact = sign_marriage_pact(
            union=self.union, senior_house=self.senior, junior_house=self.junior
        )
        self.bride.is_deceased = True
        self.bride.save(update_fields=["is_deceased"])
        dissolved = handle_death_for_pacts(self.bride)
        self.assertEqual([p.pk for p in dissolved], [pact.pk])
        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, PactDissolutionReason.DEATH)

    def test_breach_stamps_and_stops_obligation(self):
        pact = sign_marriage_pact(
            union=self.union,
            senior_house=self.senior,
            junior_house=self.junior,
            commitments=[CommitmentSpec(kind=PactCommitmentKind.SUBSIDY, percent=5)],
        )
        commitment = pact.commitments.get()
        breach_commitment(commitment)
        self.assertIsNotNone(commitment.breached_at)
        commitment.obligation.refresh_from_db()
        self.assertFalse(commitment.obligation.active)

    def test_one_pact_per_union(self):
        sign_marriage_pact(union=self.union, senior_house=self.senior, junior_house=self.junior)
        with self.assertRaises(HousesServiceError):
            sign_marriage_pact(union=self.union, senior_house=self.senior, junior_house=self.junior)
        self.assertEqual(MarriagePact.objects.count(), 1)


class DomainTests(TestCase):
    """Domains feed the org books through the existing stream spine (#1884)."""

    @classmethod
    def setUpTestData(cls):
        cls.family, cls.org = _make_house("Westrock")
        cls.area = AreaFactory()
        cls.persona = PersonaFactory()

    def test_holding_materializes_income_stream(self):
        domain = create_domain(area=self.area, name="Westrock Vale", owner_org=self.org)
        kind = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1200
        )
        holding = add_holding(domain=domain, kind=kind)
        self.assertEqual(holding.income_stream.organization, self.org)
        self.assertEqual(holding.income_stream.gross_amount, 1200)
        self.assertEqual(holding.income_stream.area, self.area)

    def test_accrual_scales_a_holdings_gross_by_domain_prosperity(self):
        # #2238 — prosperity drives income: a thriving domain amasses more per cycle.
        domain = create_domain(area=self.area, name="Westrock Vale", owner_org=self.org)
        kind = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        stream = add_holding(domain=domain, kind=kind).income_stream

        for prosperity, expected in ((50, 1000), (100, 2000), (0, 0)):
            domain.prosperity = prosperity
            domain.save(update_fields=["prosperity"])
            stream.uncollected_pool = 0
            stream.save(update_fields=["uncollected_pool"])
            accrue_income_stream(stream)
            self.assertEqual(stream.uncollected_pool, expected, f"prosperity {prosperity}")

    def test_accrual_is_unscaled_for_non_domain_streams(self):
        from world.currency.models import OrgIncomeStream

        stream = OrgIncomeStream.objects.create(
            organization=self.org, name="Kickups", kind="crime_kickup", gross_amount=500
        )
        accrue_income_stream(stream)
        self.assertEqual(stream.uncollected_pool, 500)  # no domain_holding → no scaling

    def test_unrest_crisis_chance_is_zero_at_or_below_threshold(self):
        from world.societies.houses.services import unrest_crisis_chance

        self.assertEqual(unrest_crisis_chance(50), 0.0)
        self.assertEqual(unrest_crisis_chance(60), 0.0)

    def test_unrest_crisis_chance_scales_above_threshold(self):
        from world.societies.houses.services import unrest_crisis_chance

        self.assertAlmostEqual(unrest_crisis_chance(80), 0.4)  # (80 - 60) * 2 / 100

    def test_maybe_open_unrest_crisis_fires_on_a_low_roll(self):
        from world.societies.houses.models import DomainCrisis
        from world.societies.houses.services import maybe_open_unrest_crisis

        domain = create_domain(area=self.area, name="Restless", owner_org=self.org)
        domain.unrest = 80
        domain.save(update_fields=["unrest"])

        crisis = maybe_open_unrest_crisis(domain, roll=0.0)
        self.assertIsNotNone(crisis)
        self.assertEqual(DomainCrisis.objects.filter(domain=domain).count(), 1)

    def test_maybe_open_unrest_crisis_skips_while_one_is_open(self):
        from world.societies.houses.services import maybe_open_unrest_crisis

        domain = create_domain(area=self.area, name="Restless", owner_org=self.org)
        domain.unrest = 90
        domain.save(update_fields=["unrest"])

        maybe_open_unrest_crisis(domain, roll=0.0)
        # An unresolved crisis is already open → no second one piles on.
        self.assertIsNone(maybe_open_unrest_crisis(domain, roll=0.0))

    def test_maybe_open_unrest_crisis_never_fires_for_a_calm_domain(self):
        from world.societies.houses.services import maybe_open_unrest_crisis

        domain = create_domain(area=self.area, name="Calm", owner_org=self.org)  # unrest 10
        self.assertIsNone(maybe_open_unrest_crisis(domain, roll=0.0))

    def test_improvement_project_applies_on_success(self):
        domain = create_domain(area=self.area, name="Westrock Vale", owner_org=self.org)
        kind = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        holding = add_holding(domain=domain, kind=kind)
        project = start_domain_improvement(
            domain=domain,
            persona=self.persona,
            cost=10_000,
            gross_increase=500,
            prosperity_increase=2,
            holding=holding,
        )
        self.assertEqual(project.kind, ProjectKind.DOMAIN_IMPROVEMENT)
        self.assertEqual(project.threshold_target, 100)
        project.outcome_tier = CheckOutcomeFactory(success_level=2)
        project.status = ProjectStatus.COMPLETED
        project.save()
        complete_domain_improvement(project)
        domain.refresh_from_db()
        holding.income_stream.refresh_from_db()
        self.assertEqual(domain.prosperity, 52)  # PLACEHOLDER default 50 + 2
        self.assertEqual(holding.income_stream.gross_amount, 1500)

    def test_failed_improvement_opens_crisis(self):
        domain = create_domain(area=self.area, name="Westrock Vale", owner_org=self.org)
        project = start_domain_improvement(
            domain=domain, persona=self.persona, cost=5000, prosperity_increase=1
        )
        project.outcome_tier = CheckOutcomeFactory(success_level=-2)
        project.status = ProjectStatus.FAILED
        project.save()
        complete_domain_improvement(project)
        crisis = DomainCrisis.objects.get(domain=domain)
        self.assertEqual(crisis.severity, DomainCrisisSeverity.TROUBLE)
        domain.refresh_from_db()
        self.assertEqual(domain.prosperity, 50)  # untouched on failure


class HousesSeedTests(TestCase):
    """The houses demo cluster is idempotent and walkable (#1884)."""

    def test_seed_idempotent_and_walkable(self):
        from world.seeds.houses import CROWN_ORG_NAME, HOUSE_ORG_NAME, seed_houses_demo
        from world.societies.models import Organization

        seed_houses_demo()
        seed_houses_demo()  # idempotent
        house = Organization.objects.get(name=HOUSE_ORG_NAME)
        self.assertIsNotNone(house.family)
        self.assertEqual(house.fealty.liege.name, CROWN_ORG_NAME)
        title = house.titles.get()
        self.assertIsNotNone(title.holder)
        self.assertEqual(house.domains.count(), 1)
        holding = house.domains.get().holdings.get()
        self.assertEqual(holding.income_stream.organization, house)


class HouseChannelTests(TestCase):
    """The house channel connects the playing household, vassals cascaded."""

    def test_sync_connects_member_and_vassal_accounts(self):
        from evennia_extensions.factories import AccountFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.scenes.factories import PersonaFactory
        from world.societies.houses.services import sync_house_channel
        from world.societies.membership_services import (
            ensure_default_rank_ladder,
            join_organization,
        )

        _family, house = _make_house("Channelwright")
        _vfamily, vassal = _make_house("Bannerkin")
        swear_fealty(vassal=vassal, liege=house)

        def playing_member(org):
            account = AccountFactory()
            persona = PersonaFactory()
            RosterTenureFactory(
                player_data=PlayerDataFactory(account=account),
                roster_entry=RosterEntryFactory(character_sheet=persona.character_sheet),
                end_date=None,
            )
            ensure_default_rank_ladder(org)
            join_organization(org, persona)
            return account

        member_account = playing_member(house)
        vassal_account = playing_member(vassal)

        channel = sync_house_channel(house)
        self.assertTrue(channel.has_connection(member_account))
        self.assertTrue(channel.has_connection(vassal_account))
        # Idempotent re-run.
        self.assertEqual(sync_house_channel(house).pk, channel.pk)
