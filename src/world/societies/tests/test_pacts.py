"""Org pacts, betrothal, wedding, and the match dossier (#2999)."""

from django.test import TestCase

from world.roster.constants import NOBLE_KIND_NAME, MembershipBasis
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinspersonFactory
from world.roster.models import FamilyMembership, Union, UnionKind
from world.scenes.factories import PersonaFactory
from world.societies.dossier_services import build_dossier
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.constants import (
    BETROTHAL_STATURE_SHARE_PCT,
    DIVORCE_INITIATOR_PRESTIGE_PENALTY,
    DIVORCE_OTHER_SPOUSE_PRESTIGE_PENALTY,
    GIFTED_RATING_RENOWN,
    SCANDAL_PRESTIGE_PENALTY,
    OrgPactDissolutionReason,
    PactDissolutionReason,
)
from world.societies.houses.models import (
    Betrothal,
    HouseStature,
    MarriagePact,
    OrgPact,
    PactKind,
)
from world.societies.houses.pact_services import (
    break_betrothal,
    dissolve_org_pact,
    flag_betrayal_between,
    initiate_divorce,
    propose_betrothal,
    propose_org_pact,
    ratify_org_pact,
    solemnize_wedding,
)
from world.societies.houses.services import CommitmentSpec, HousesServiceError
from world.societies.houses.stature_services import compute_components

NO_LEGEND = {"legend_reader": lambda _persona: 0}


def _house(name: str, *, with_leader: bool = True):
    family = FamilyFactory(name=name, kind=FamilyKindFactory(name=NOBLE_KIND_NAME))
    org = OrganizationFactory(name=f"House {name}", family=family)
    leader = None
    if with_leader:
        leader = PersonaFactory()
        OrganizationMembershipFactory(organization=org, persona=leader, rank=1)
    return org, leader


def _kin(family, rating: int = 0, name: str | None = None):
    kin = KinspersonFactory(name=name or f"{family.name} kin", family=family, gifted_rating=rating)
    FamilyMembership.objects.create(
        kinsperson=kin,
        family=family,
        basis=MembershipBasis.BORN,
        started_at="2020-01-01T00:00:00Z",
    )
    return kin


class OrgPactTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a, cls.leader_a = _house("Alder")
        cls.org_b, cls.leader_b = _house("Birch")
        cls.compact = PactKind.objects.create(
            name="Defensive Compact", allied_share_pct=40, non_aggression=True
        )

    def test_propose_requires_leadership(self):
        outsider = PersonaFactory()
        with self.assertRaises(HousesServiceError):
            propose_org_pact(
                kind=self.compact, proposer=outsider, party_a=self.org_a, party_b=self.org_b
            )

    def test_ratified_pact_feeds_allied_stature(self):
        _kin(self.org_b.family, rating=4)
        pact = propose_org_pact(
            kind=self.compact, proposer=self.leader_a, party_a=self.org_a, party_b=self.org_b
        )
        self.assertEqual(compute_components(self.org_a, **NO_LEGEND).allied, 0)
        ratify_org_pact(pact, ratifier=self.leader_b)
        parts = compute_components(self.org_a, **NO_LEGEND)
        self.assertGreater(parts.allied, 0)

    def test_ratify_mints_tithe_obligation(self):
        trade = PactKind.objects.create(name="Trade Agreement", income_share_pct=10)
        pact = propose_org_pact(
            kind=trade, proposer=self.leader_a, party_a=self.org_a, party_b=self.org_b
        )
        ratify_org_pact(pact, ratifier=self.leader_b)
        pact.refresh_from_db()
        self.assertIsNotNone(pact.obligation)
        self.assertEqual(pact.obligation.percent, 10)
        self.assertTrue(pact.obligation.active)

    def test_betrayal_burns_prestige_and_deactivates_obligation(self):
        pact = propose_org_pact(
            kind=self.compact, proposer=self.leader_a, party_a=self.org_a, party_b=self.org_b
        )
        ratify_org_pact(pact, ratifier=self.leader_b)
        before = self.org_a.accumulated_prestige
        dissolve_org_pact(pact, reason=OrgPactDissolutionReason.BETRAYAL, betrayer=self.org_a)
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.accumulated_prestige, before - SCANDAL_PRESTIGE_PENALTY)

    def test_flag_betrayal_between_partners(self):
        pact = propose_org_pact(
            kind=self.compact, proposer=self.leader_a, party_a=self.org_a, party_b=self.org_b
        )
        ratify_org_pact(pact, ratifier=self.leader_b)
        count = flag_betrayal_between(self.org_a, self.org_b)
        self.assertEqual(count, 1)
        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, OrgPactDissolutionReason.BETRAYAL)


class BetrothalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.senior, cls.leader = _house("Crown")
        cls.junior, _ = _house("Vale")
        cls.bride = _kin(cls.senior.family, name="Bride")
        cls.groom = _kin(cls.junior.family, rating=4, name="Groom")

    def _betroth(self, terms=None):
        return propose_betrothal(
            proposer=self.leader,
            kinsperson_a=self.bride,
            kinsperson_b=self.groom,
            senior_house=self.senior,
            junior_house=self.junior,
            terms=terms,
        )

    def test_betrothal_previews_partner_at_fraction(self):
        self._betroth()
        parts = compute_components(self.senior, **NO_LEGEND)
        expected = round(4 * GIFTED_RATING_RENOWN * BETROTHAL_STATURE_SHARE_PCT / 100)
        self.assertEqual(parts.renown, expected)

    def test_double_promise_refused(self):
        self._betroth()
        other = _kin(self.junior.family, name="Other")
        with self.assertRaises(HousesServiceError):
            propose_betrothal(
                proposer=self.leader,
                kinsperson_a=self.bride,
                kinsperson_b=other,
                senior_house=self.senior,
                junior_house=self.junior,
            )

    def test_breaking_costs_standing(self):
        betrothal = self._betroth()
        before = self.junior.accumulated_prestige
        break_betrothal(betrothal, breaking_house=self.junior)
        self.junior.refresh_from_db()
        self.assertLess(self.junior.accumulated_prestige, before)
        betrothal.refresh_from_db()
        self.assertIsNotNone(betrothal.broken_at)

    def test_wedding_solemnizes_union_pact_and_terms(self):
        UnionKind.objects.create(name="Marriage Universal", confers_wedlock=True)
        betrothal = self._betroth(
            terms=[CommitmentSpec(kind="custom", notes="PLACEHOLDER a sworn promise")]
        )
        pact = solemnize_wedding(betrothal)
        betrothal.refresh_from_db()
        self.assertIsNotNone(betrothal.wed_at)
        self.assertTrue(
            Union.objects.filter(members=self.bride).filter(members=self.groom).exists()
        )
        self.assertEqual(pact.senior_house, self.senior)
        self.assertEqual(pact.commitments.count(), 1)
        # The wedded spouse now counts at FULL weight (marriage both ways).
        parts = compute_components(self.senior, **NO_LEGEND)
        self.assertEqual(parts.renown, 4 * GIFTED_RATING_RENOWN)

    def test_wedding_refused_after_break(self):
        betrothal = self._betroth()
        break_betrothal(betrothal, breaking_house=self.junior)
        with self.assertRaises(HousesServiceError):
            solemnize_wedding(betrothal)


class DossierTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.leader = _house("Dossier")
        cls.rival, cls.rival_leader = _house("Rival")
        HouseStature.objects.create(
            organization=cls.org, true_total=9_000, perceived_total=8_000, prestige_rank=3
        )

    def test_dossier_carries_stature_and_pacts(self):
        kind = PactKind.objects.create(name="Non-Aggression Pact", non_aggression=True)
        pact = propose_org_pact(
            kind=kind, proposer=self.leader, party_a=self.org, party_b=self.rival
        )
        ratify_org_pact(pact, ratifier=self.rival_leader)
        payload = build_dossier(self.org, viewer=None)
        self.assertEqual(payload["name"], "House Dossier")
        self.assertEqual(payload["perceived_total"], 8_000)
        self.assertEqual(payload["prestige_rank"], 3)
        kinds = [row["kind"] for row in payload["pacts"]]
        self.assertIn("Non-Aggression Pact", kinds)

    def test_dossier_lists_marriages_and_betrothals(self):
        bride = _kin(self.org.family, name="Heir")
        groom = _kin(self.rival.family, name="Match")
        propose_betrothal(
            proposer=self.leader,
            kinsperson_a=bride,
            kinsperson_b=groom,
            senior_house=self.org,
            junior_house=self.rival,
        )
        payload = build_dossier(self.org, viewer=None)
        self.assertEqual(len(payload["betrothals"]), 1)
        self.assertIn("Heir", payload["betrothals"][0])

    def test_marriage_pact_rows_present(self):
        kind = UnionKind.objects.create(name="Marriage Dossier", confers_wedlock=True)
        a = _kin(self.org.family, name="A")
        b = _kin(self.rival.family, name="B")
        from world.roster.services.kinship import record_union

        union = record_union(kind=kind, members=[a, b])
        from world.societies.houses.services import sign_marriage_pact

        sign_marriage_pact(union=union, senior_house=self.org, junior_house=self.rival)
        payload = build_dossier(self.org, viewer=None)
        kinds = [row["kind"] for row in payload["pacts"]]
        self.assertIn("Marriage", kinds)
        self.assertTrue(MarriagePact.objects.filter(senior_house=self.org).exists())


class WeddingCeremonyResolutionTests(TestCase):
    def test_active_betrothal_resolves_from_honoree_sheets(self):
        from types import SimpleNamespace

        from world.ceremonies.services import _solemnize_wedding_honorees
        from world.character_sheets.factories import CharacterSheetFactory

        UnionKind.objects.create(name="Marriage Rite", confers_wedlock=True)
        senior, leader = _house("Rite")
        junior, _ = _house("Guest")
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()
        bride = KinspersonFactory(family=senior.family, sheet=sheet_a)
        groom = KinspersonFactory(family=junior.family, sheet=sheet_b)
        FamilyMembership.objects.create(
            kinsperson=bride,
            family=senior.family,
            basis=MembershipBasis.BORN,
            started_at="2020-01-01T00:00:00Z",
        )
        propose_betrothal(
            proposer=leader,
            kinsperson_a=bride,
            kinsperson_b=groom,
            senior_house=senior,
            junior_house=junior,
        )
        honorees = [
            SimpleNamespace(honoree_sheet_id=sheet_a.pk),
            SimpleNamespace(honoree_sheet_id=sheet_b.pk),
        ]
        _solemnize_wedding_honorees(honorees)
        betrothal = Betrothal.objects.get()
        self.assertIsNotNone(betrothal.wed_at)
        self.assertTrue(OrgPact.objects.count() == 0)  # a marriage pact, not an org pact
        self.assertTrue(MarriagePact.objects.filter(senior_house=senior).exists())


class DivorceTests(TestCase):
    """Either spouse divorces unilaterally; BOTH take a prestige hit (#2358)."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory

        UnionKind.objects.create(name="Marriage Divorce", confers_wedlock=True)
        cls.senior, cls.leader = _house("Ember")
        cls.junior, _ = _house("Thorn")
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        cls.bride = KinspersonFactory(family=cls.senior.family, sheet=cls.sheet_a)
        cls.groom = KinspersonFactory(family=cls.junior.family, sheet=cls.sheet_b)
        FamilyMembership.objects.create(
            kinsperson=cls.bride,
            family=cls.senior.family,
            basis=MembershipBasis.BORN,
            started_at="2020-01-01T00:00:00Z",
        )

    def setUp(self) -> None:
        betrothal = propose_betrothal(
            proposer=self.leader,
            kinsperson_a=self.bride,
            kinsperson_b=self.groom,
            senior_house=self.senior,
            junior_house=self.junior,
        )
        solemnize_wedding(betrothal)
        self.union = Union.objects.filter(members=self.bride).filter(members=self.groom).get()

    def test_initiate_divorce_ends_union_and_dissolves_pact_as_divorce(self):
        initiate_divorce(self.sheet_a, self.union)
        self.union.refresh_from_db()
        self.assertIsNotNone(self.union.ended_at)
        pact = MarriagePact.objects.get(union=self.union)
        self.assertIsNotNone(pact.dissolved_at)
        self.assertEqual(pact.dissolution_reason, PactDissolutionReason.DIVORCE)

    def _primary_persona_prestige(self, sheet_pk: int) -> int:
        """Fresh CharacterSheet + persona lookup — never the setUpTestData deep copy.

        ``setUpTestData`` deep-copies its class attributes onto ``self`` for
        every test (Django's cross-test mutation guard); a cached_property
        (``CharacterSheet.primary_persona``) already resolved on the class
        attribute carries a stale, disconnected Persona copy through that
        deepcopy. Re-fetching the sheet by pk sidesteps it.
        """
        from world.character_sheets.models import CharacterSheet

        sheet = CharacterSheet.objects.get(pk=sheet_pk)
        return sheet.primary_persona.total_prestige

    def test_initiate_divorce_hits_both_spouses_initiator_steeper(self):
        before_a = self._primary_persona_prestige(self.sheet_a.pk)
        before_b = self._primary_persona_prestige(self.sheet_b.pk)

        initiate_divorce(self.sheet_a, self.union)

        drop_a = before_a - self._primary_persona_prestige(self.sheet_a.pk)
        drop_b = before_b - self._primary_persona_prestige(self.sheet_b.pk)
        self.assertEqual(drop_a, DIVORCE_INITIATOR_PRESTIGE_PENALTY)
        self.assertEqual(drop_b, DIVORCE_OTHER_SPOUSE_PRESTIGE_PENALTY)
        self.assertGreater(drop_a, drop_b)

    def test_double_divorce_refused(self):
        initiate_divorce(self.sheet_a, self.union)
        with self.assertRaises(HousesServiceError):
            initiate_divorce(self.sheet_b, self.union)

    def test_non_spouse_cannot_divorce(self):
        from world.character_sheets.factories import CharacterSheetFactory

        stranger_sheet = CharacterSheetFactory()
        with self.assertRaises(HousesServiceError):
            initiate_divorce(stranger_sheet, self.union)
