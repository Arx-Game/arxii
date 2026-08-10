"""House Stature (#3091): component computation, perception, bands, ranks.

Legend totals ride a Postgres matview, absent on the SQLite tier — every
call injects ``legend_reader`` so these tests run fast-tier.
"""

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.currency.services import get_or_create_treasury
from world.military.factories import MilitaryUnitFactory
from world.roster.constants import MembershipBasis
from world.roster.factories import FamilyFactory, KinspersonFactory, UnionFactory
from world.roster.models import Family, FamilyMembership, UnionKind
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationTypeFactory,
)
from world.societies.houses.constants import (
    CRISIS_STATURE_PENALTIES,
    GIFTED_RATING_RENOWN,
    STATURE_ALLY_FACTOR,
    STATURE_CONVERGENCE_RATE,
    STATURE_DEATH_SHOCK_SHARE,
    STATURE_RENOWN_WEIGHT,
    STATURE_WHISPER_MAX_DISPLACEMENT,
    CrisisOrigin,
    DomainCrisisSeverity,
    StatureShiftCause,
    TitleTier,
)
from world.societies.houses.models import (
    DomainCrisis,
    HouseStature,
    MarriagePact,
    PrestigeRankBand,
    StatureBand,
    StatureShift,
    Title,
)
from world.societies.houses.services import create_domain
from world.societies.houses.stature_services import (
    apply_death_shock,
    apply_prestige_prosperity_drift,
    apply_whisper,
    assign_bands,
    compute_components,
    converge_perceived,
    kinsperson_renown_score,
    persona_renown_score,
    recompute_org_prestige_ranks,
    recompute_stature,
    weekly_stature_tick,
)

NO_LEGEND = {"legend_reader": lambda _persona: 0}


def _make_house(name: str):
    family = FamilyFactory(name=name, family_type=Family.FamilyType.NOBLE)
    org = OrganizationFactory(name=f"House {name}", family=family)
    return family, org


def _kin(family, rating: int = 0, name: str | None = None):
    kin = KinspersonFactory(name=name or f"{family.name} kin", family=family, gifted_rating=rating)
    FamilyMembership.objects.create(
        kinsperson=kin,
        family=family,
        basis=MembershipBasis.BORN,
        started_at="2020-01-01T00:00:00Z",
    )
    return kin


class RenownScoreTests(TestCase):
    def test_persona_score_sums_prestige_fame_and_legend(self):
        persona = PersonaFactory(total_prestige=1_000, fame_points=500)
        score = persona_renown_score(persona, legend_reader=lambda _p: 100)
        self.assertEqual(score, 1_000 + 500 + 200)

    def test_sheetless_kin_score_uses_gifted_rating(self):
        kin = KinspersonFactory(gifted_rating=3)
        self.assertEqual(kinsperson_renown_score(kin, **NO_LEGEND), 3 * GIFTED_RATING_RENOWN)


class ComponentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family, cls.org = _make_house("Westrock")

    def test_member_personas_feed_renown_once(self):
        persona = PersonaFactory(total_prestige=2_000, fame_points=0)
        OrganizationMembershipFactory(organization=self.org, persona=persona)
        parts = compute_components(self.org, **NO_LEGEND)
        self.assertEqual(parts.renown, 2_000)

    def test_kin_gifted_rating_feeds_renown(self):
        _kin(self.family, rating=2)
        parts = compute_components(self.org, **NO_LEGEND)
        self.assertEqual(parts.renown, 2 * GIFTED_RATING_RENOWN)

    def test_deceased_kin_do_not_count(self):
        kin = _kin(self.family, rating=2)
        kin.is_deceased = True
        kin.save(update_fields=["is_deceased"])
        parts = compute_components(self.org, **NO_LEGEND)
        self.assertEqual(parts.renown, 0)

    def test_military_scales_by_quality(self):
        MilitaryUnitFactory(owner_org=self.org, strength=100, quality="elite")
        MilitaryUnitFactory(owner_org=self.org, strength=100, quality="militia")
        parts = compute_components(self.org, **NO_LEGEND)
        self.assertEqual(parts.military, 200 + 50)

    def test_economic_reads_treasury_and_streams(self):
        treasury = get_or_create_treasury(self.org)
        treasury.balance = 100_000
        treasury.save(update_fields=["balance"])
        parts = compute_components(self.org, **NO_LEGEND)
        self.assertEqual(parts.economic, 10)

    def test_crisis_penalty_bites_true_total(self):
        _kin(self.family, rating=5)
        area = AreaFactory()
        domain = create_domain(area=area, name="Westrock Vale", owner_org=self.org)
        DomainCrisis.objects.create(
            domain=domain,
            severity=DomainCrisisSeverity.CATASTROPHE,
            origin=CrisisOrigin.STAFF,
        )
        parts = compute_components(self.org, **NO_LEGEND)
        gross = round(5 * GIFTED_RATING_RENOWN * STATURE_RENOWN_WEIGHT)
        expected = round(gross * CRISIS_STATURE_PENALTIES[DomainCrisisSeverity.CATASTROPHE])
        self.assertEqual(parts.crisis_penalty, expected)
        self.assertEqual(parts.true_total, gross - expected)


class UnionWeightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family_a, cls.org_a = _make_house("Inferna")
        cls.family_b, cls.org_b = _make_house("Umbros")

    def test_marriage_counts_spouse_to_both_houses(self):
        ours = _kin(self.family_a)
        theirs = _kin(self.family_b, rating=4)
        UnionFactory(members=[ours, theirs])
        parts_a = compute_components(self.org_a, **NO_LEGEND)
        parts_b = compute_components(self.org_b, **NO_LEGEND)
        self.assertEqual(parts_a.renown, 4 * GIFTED_RATING_RENOWN)
        self.assertEqual(parts_b.renown, 4 * GIFTED_RATING_RENOWN)

    def test_paramour_kind_carries_no_weight(self):
        ours = _kin(self.family_a)
        lover = _kin(self.family_b, rating=4)
        paramour = UnionKind.objects.create(name="Paramour", stature_share_pct=0)
        UnionFactory(kind=paramour, members=[ours, lover])
        parts = compute_components(self.org_a, **NO_LEGEND)
        self.assertEqual(parts.renown, 0)

    def _consort_kind(self, cap: int | None = None) -> UnionKind:
        return UnionKind.objects.create(
            name="Consort of Inferna",
            stature_share_pct=50,
            contributes_to_origin_house=False,
            requires_landed_title=True,
            max_concurrent=cap,
        )

    def _enthrone(self, kin):
        area = AreaFactory()
        domain = create_domain(area=area, name=f"Seat of {kin.name}", owner_org=self.org_a)
        Title.objects.create(
            name=f"Principality of {kin.name}",
            tier=TitleTier.KINGDOM,
            realm=self.org_a.society.realm,
            house=self.org_a,
            holder=kin,
            seat_domain=domain,
        )

    def test_consort_counts_half_only_for_landed_title_holder(self):
        princess = _kin(self.family_a)
        consort = _kin(self.family_b, rating=4)
        UnionFactory(kind=self._consort_kind(), members=[princess, consort])
        self.assertEqual(compute_components(self.org_a, **NO_LEGEND).renown, 0)
        self._enthrone(princess)
        parts = compute_components(self.org_a, **NO_LEGEND)
        self.assertEqual(parts.renown, round(4 * GIFTED_RATING_RENOWN * 0.5))

    def test_consort_cap_limits_concurrent_contributions(self):
        princess = _kin(self.family_a)
        self._enthrone(princess)
        kind = self._consort_kind(cap=1)
        first = _kin(self.family_b, rating=2, name="First Consort")
        second = _kin(self.family_b, rating=4, name="Second Consort")
        UnionFactory(kind=kind, members=[princess, first])
        UnionFactory(kind=kind, members=[princess, second])
        parts = compute_components(self.org_a, **NO_LEGEND)
        self.assertEqual(parts.renown, round(2 * GIFTED_RATING_RENOWN * 0.5))

    def test_consort_adds_nothing_to_origin_house(self):
        princess = _kin(self.family_a)
        self._enthrone(princess)
        consort = _kin(self.family_b, rating=4)
        UnionFactory(kind=self._consort_kind(), members=[princess, consort])
        parts_b = compute_components(self.org_b, **NO_LEGEND)
        # Origin house keeps its blood member (kin channel), gains nothing more.
        self.assertEqual(parts_b.renown, 4 * GIFTED_RATING_RENOWN)


class AlliedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family_a, cls.org_a = _make_house("Alpha")
        cls.family_b, cls.org_b = _make_house("Bravo")
        cls.family_c, cls.org_c = _make_house("Charlie")

    def _pact(self, senior, junior):
        a = _kin(senior[0])
        b = _kin(junior[0])
        union = UnionFactory(members=[a, b])
        return MarriagePact.objects.create(
            union=union, senior_house=senior[1], junior_house=junior[1]
        )

    def test_allied_reads_counterpart_net_one_hop_only(self):
        _kin(self.family_b, rating=2)
        _kin(self.family_c, rating=4)
        self._pact((self.family_a, self.org_a), (self.family_b, self.org_b))
        self._pact((self.family_b, self.org_b), (self.family_c, self.org_c))
        parts = compute_components(self.org_a, **NO_LEGEND)
        # B's own net includes its kin + married-in A spouse + B->C spouse
        # channels, but NOT C's allied contribution (no transitive chains).
        b_net_kin = 2 * GIFTED_RATING_RENOWN
        self.assertGreaterEqual(parts.allied, round(b_net_kin * STATURE_RENOWN_WEIGHT * 0.5) - 1)
        # Sanity: allied is strictly less than what a transitive chain would add.
        c_gross = round(4 * GIFTED_RATING_RENOWN * STATURE_RENOWN_WEIGHT)
        b_alone_ceiling = round((b_net_kin + 4 * GIFTED_RATING_RENOWN + 0) * STATURE_RENOWN_WEIGHT)
        transitive_floor = round(
            (b_alone_ceiling + round(c_gross * STATURE_ALLY_FACTOR)) * STATURE_ALLY_FACTOR
        )
        self.assertLess(parts.allied, transitive_floor)


class PerceptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.family, cls.org = _make_house("Perception")

    def test_converge_moves_perceived_toward_true(self):
        _kin(self.family, rating=5)
        stature = recompute_stature(self.org, **NO_LEGEND)
        stature.perceived_total = 0
        stature.save(update_fields=["perceived_total"])
        delta = converge_perceived(stature)
        self.assertEqual(delta, round(stature.true_total * STATURE_CONVERGENCE_RATE))
        self.assertEqual(
            StatureShift.objects.filter(
                organization=self.org, cause=StatureShiftCause.CONVERGENCE
            ).count(),
            1,
        )

    def test_death_shock_drops_perceived_immediately(self):
        kin = _kin(self.family, rating=5)
        recompute_stature(self.org, **NO_LEGEND)
        before = HouseStature.objects.get(organization=self.org).perceived_total
        apply_death_shock(kin, **NO_LEGEND)
        after = HouseStature.objects.get(organization=self.org).perceived_total
        expected_shock = round(
            5 * GIFTED_RATING_RENOWN * STATURE_RENOWN_WEIGHT * STATURE_DEATH_SHOCK_SHARE
        )
        self.assertEqual(before - after, expected_shock)
        shift = StatureShift.objects.get(organization=self.org, cause=StatureShiftCause.DEATH)
        self.assertEqual(shift.subject_kinsperson, kin)

    def test_whisper_is_bounded_below_true(self):
        _kin(self.family, rating=5)
        stature = recompute_stature(self.org, **NO_LEGEND)
        floor = round(stature.true_total * (1 - STATURE_WHISPER_MAX_DISPLACEMENT))
        applied_total = 0
        for _ in range(10):
            applied_total += apply_whisper(self.org, 1_000)
        stature.refresh_from_db()
        self.assertEqual(stature.perceived_total, floor)
        self.assertEqual(applied_total, floor - stature.true_total)


class BandAndRankTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.noble_type = OrganizationTypeFactory(name="noble_family")
        cls.gang_type = OrganizationTypeFactory(name="gang")
        cls.low = StatureBand.objects.create(name="Imperiled", rank=2, min_percentile=0)
        cls.high = StatureBand.objects.create(name="Formidable", rank=1, min_percentile=50)

    def _landed(self, name, org_type, perceived):
        family = FamilyFactory(name=name, family_type=Family.FamilyType.NOBLE)
        org = OrganizationFactory(name=f"House {name}", family=family, org_type=org_type)
        create_domain(area=AreaFactory(), name=f"{name} Vale", owner_org=org)
        HouseStature.objects.create(
            organization=org, perceived_total=perceived, true_total=perceived
        )
        return org

    def test_bands_assign_within_category_cohorts(self):
        strong_noble = self._landed("StrongN", self.noble_type, 1_000)
        weak_noble = self._landed("WeakN", self.noble_type, 100)
        strong_gang = self._landed("StrongG", self.gang_type, 50)
        weak_gang = self._landed("WeakG", self.gang_type, 10)
        assign_bands()
        get = lambda org: HouseStature.objects.get(organization=org)  # noqa: E731
        self.assertEqual(get(strong_noble).band, self.high)
        self.assertEqual(get(weak_noble).band, self.low)
        # A gang bands against gangs: 50 perceived tops ITS cohort.
        self.assertEqual(get(strong_gang).band, self.high)
        self.assertEqual(get(weak_gang).band, self.low)

    def test_prestige_ranks_cover_all_orgs(self):
        landed = self._landed("Landed", self.noble_type, 10)
        unlanded = OrganizationFactory(name="The Forty Thieves", org_type=self.gang_type)
        landed.base_prestige = 1_000
        landed.save(update_fields=["base_prestige"])
        unlanded.base_prestige = 5_000
        unlanded.save(update_fields=["base_prestige"])
        recompute_org_prestige_ranks()
        self.assertEqual(HouseStature.objects.get(organization=landed).prestige_rank > 1, True)
        self.assertEqual(unlanded.prestige_rank_row.prestige_rank, 1)

    def test_prosperity_drift_gated_on_no_open_threats(self):
        org = self._landed("Drifty", self.noble_type, 10)
        org.base_prestige = 1_000_000
        org.save(update_fields=["base_prestige"])
        PrestigeRankBand.objects.create(
            name="Top of the World", min_rank=1, max_rank=100, prosperity_bonus=3
        )
        recompute_org_prestige_ranks()
        domain = org.domains.first()
        start = domain.prosperity
        apply_prestige_prosperity_drift()
        domain.refresh_from_db()
        self.assertEqual(domain.prosperity, start + 3)
        DomainCrisis.objects.create(
            domain=domain,
            severity=DomainCrisisSeverity.TROUBLE,
            origin=CrisisOrigin.STAFF,
        )
        apply_prestige_prosperity_drift()
        domain.refresh_from_db()
        self.assertEqual(domain.prosperity, start + 3)


class WeeklyTickTests(TestCase):
    def test_weekly_tick_runs_end_to_end(self):
        StatureBand.objects.create(name="Steady", rank=1, min_percentile=0)
        family = FamilyFactory(name="Tick", family_type=Family.FamilyType.NOBLE)
        org = OrganizationFactory(name="House Tick", family=family)
        create_domain(area=AreaFactory(), name="Tick Vale", owner_org=org)
        _kin(family, rating=3)
        summary = weekly_stature_tick(**NO_LEGEND)
        self.assertEqual(summary["recomputed"], 1)
        stature = HouseStature.objects.get(organization=org)
        self.assertGreater(stature.true_total, 0)
        self.assertIsNotNone(stature.band)
