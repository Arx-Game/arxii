"""DomainCrisis lifecycle tests (#2238) — open, judge, resolve, tick, surface."""

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationRankFactory
from world.societies.houses.constants import (
    CrisisOrigin,
    CrisisResolution,
    CrisisResolutionKind,
    DomainCrisisSeverity,
)
from world.societies.houses.crisis_services import (
    CrisisServiceError,
    choose_crisis_option,
    crisis_wait_tick,
    open_crisis,
    resolve_crisis,
    resolve_crisis_for_mission,
)
from world.societies.houses.models import DomainCrisisType, DomainCrisisTypeOption
from world.societies.houses.services import create_domain
from world.societies.models import OrganizationMembership


class _FixedRng:
    """Injectable rng: fixed uniform value + first-candidate weighted choice."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def random(self) -> float:
        return self.value

    def choices(self, population, weights=None, k=1):  # noqa: ARG002 — rng protocol
        return [population[0]]


def _make_type(name, severity, kinds, *, mission_template=None):
    ctype = DomainCrisisType.objects.create(name=name, default_severity=severity)
    for kind in kinds:
        DomainCrisisTypeOption.objects.create(
            crisis_type=ctype,
            kind=kind,
            cost_coppers=1000 if kind == CrisisResolutionKind.PAY else 0,
            mission_template=(mission_template if kind == CrisisResolutionKind.MISSION else None),
            self_resolve_pct=20 if kind == CrisisResolutionKind.WAIT else 0,
            worsen_pct=30 if kind == CrisisResolutionKind.WAIT else 0,
        )
    return ctype


class CrisisLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory(name="House Test")
        cls.area = AreaFactory()
        cls.domain = create_domain(area=cls.area, name="Testvale", owner_org=cls.org)

    def _mission_template(self):
        from world.missions.factories import MissionTemplateFactory

        return MissionTemplateFactory()

    def _leader_persona(self):
        from world.societies.models import OrganizationRank

        persona = PersonaFactory()
        rank = OrganizationRank.objects.filter(organization=self.org, tier=1).first()
        if rank is None:
            rank = OrganizationRankFactory(organization=self.org, tier=1, name="Head")
        if not rank.can_manage_ranks:
            rank.can_manage_ranks = True
            rank.save(update_fields=["can_manage_ranks"])
        OrganizationMembership.objects.create(organization=self.org, persona=persona, rank=rank)
        return persona

    # -- opening -----------------------------------------------------------

    def test_automated_origin_picks_an_eligible_type(self):
        ctype = _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        self.assertEqual(crisis.crisis_type, ctype)
        self.assertEqual(crisis.severity, DomainCrisisSeverity.TROUBLE)
        self.assertEqual(crisis.origin, CrisisOrigin.UNREST)

    def test_staff_origin_never_auto_picks(self):
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.STAFF, description="Bespoke")
        self.assertIsNone(crisis.crisis_type)
        self.assertEqual(crisis.description, "Bespoke")

    def test_one_open_crisis_guard(self):
        open_crisis(self.domain, origin=CrisisOrigin.STAFF)
        self.assertIsNone(open_crisis(self.domain, origin=CrisisOrigin.STAFF))

    def test_auto_mint_rule_single_mission_option(self):
        template = self._mission_template()
        _make_type(
            "Invasion",
            DomainCrisisSeverity.CRISIS,
            [CrisisResolutionKind.MISSION],
            mission_template=template,
        )
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        self.assertIsNotNone(crisis.chosen_option)
        self.assertEqual(crisis.chosen_option.kind, CrisisResolutionKind.MISSION)

    def test_no_auto_mint_with_a_real_choice(self):
        template = self._mission_template()
        _make_type(
            "Bandits",
            DomainCrisisSeverity.CRISIS,
            [CrisisResolutionKind.PAY, CrisisResolutionKind.MISSION],
            mission_template=template,
        )
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        self.assertIsNone(crisis.chosen_option)

    # -- neutral state -----------------------------------------------------

    def test_open_crisis_scales_income_and_resolution_restores_it(self):
        base = self.domain.income_multiplier
        crisis = open_crisis(self.domain, origin=CrisisOrigin.STAFF)
        crisis.severity = DomainCrisisSeverity.CATASTROPHE
        crisis.save(update_fields=["severity"])
        self.assertAlmostEqual(self.domain.income_multiplier, base * 0.5)
        resolve_crisis(crisis, resolution=CrisisResolution.PAID)
        self.assertAlmostEqual(self.domain.income_multiplier, base)

    def test_unjudged_crisis_never_worsens(self):
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.WAIT])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        self.assertIsNone(crisis.chosen_option)  # WAIT alone doesn't auto-choose
        for _ in range(5):
            crisis_wait_tick(rng=_FixedRng(0.25))  # roll that WOULD worsen if chosen
        crisis.refresh_from_db()
        self.assertEqual(crisis.severity, DomainCrisisSeverity.TROUBLE)
        self.assertIsNone(crisis.resolved_at)

    # -- the judgment call -------------------------------------------------

    def test_wait_tick_self_resolves_and_worsens(self):
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.WAIT])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        persona = self._leader_persona()
        option = crisis.crisis_type.options.first()
        choose_crisis_option(crisis, persona, option)

        # roll 25 lands in the worsen band (20 self + 30 worsen): severity bumps.
        crisis_wait_tick(rng=_FixedRng(0.25))
        crisis.refresh_from_db()
        self.assertEqual(crisis.severity, DomainCrisisSeverity.CRISIS)

        # roll 10 lands in the self-resolve band: it blows over.
        crisis_wait_tick(rng=_FixedRng(0.10))
        crisis.refresh_from_db()
        self.assertEqual(crisis.resolution, CrisisResolution.SELF_RESOLVED)

    def test_wait_worsen_caps_at_catastrophe(self):
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.WAIT])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        choose_crisis_option(crisis, self._leader_persona(), crisis.crisis_type.options.first())
        crisis.severity = DomainCrisisSeverity.CATASTROPHE
        crisis.save(update_fields=["severity"])
        crisis_wait_tick(rng=_FixedRng(0.25))
        crisis.refresh_from_db()
        self.assertEqual(crisis.severity, DomainCrisisSeverity.CATASTROPHE)
        self.assertIsNone(crisis.resolved_at)

    def test_pay_resolves_and_debits_treasury(self):
        from world.currency.services import get_or_create_treasury

        _make_type("Protests", DomainCrisisSeverity.CRISIS, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        persona = self._leader_persona()
        treasury = get_or_create_treasury(self.org)
        treasury.balance = 5000
        treasury.save(update_fields=["balance"])

        choose_crisis_option(crisis, persona, crisis.crisis_type.options.first())
        crisis.refresh_from_db()
        treasury.refresh_from_db()
        self.assertEqual(crisis.resolution, CrisisResolution.PAID)
        # CRISIS severity doubles the 1000c base (PLACEHOLDER multipliers).
        self.assertEqual(treasury.balance, 3000)

    def test_pay_requires_funds_and_authority(self):
        from world.currency.services import get_or_create_treasury

        _make_type("Protests", DomainCrisisSeverity.CRISIS, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        option = crisis.crisis_type.options.first()

        outsider = PersonaFactory()
        with self.assertRaises(CrisisServiceError):
            choose_crisis_option(crisis, outsider, option)

        persona = self._leader_persona()
        get_or_create_treasury(self.org)  # balance defaults to 0
        with self.assertRaises(CrisisServiceError):
            choose_crisis_option(crisis, persona, option)

    def test_option_must_belong_and_choose_once(self):
        template = self._mission_template()
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.WAIT])
        other = _make_type(
            "Invasion",
            DomainCrisisSeverity.CRISIS,
            [CrisisResolutionKind.MISSION],
            mission_template=template,
        )
        crisis = open_crisis(
            self.domain,
            origin=CrisisOrigin.UNREST,
            crisis_type=DomainCrisisType.objects.get(name="Protests"),
        )
        persona = self._leader_persona()
        with self.assertRaises(CrisisServiceError):
            choose_crisis_option(crisis, persona, other.options.first())
        choose_crisis_option(crisis, persona, crisis.crisis_type.options.first())
        with self.assertRaises(CrisisServiceError):
            choose_crisis_option(crisis, persona, crisis.crisis_type.options.first())

    # -- mission + surfacing ----------------------------------------------

    def test_mission_completion_resolves_source_crisis(self):
        from world.missions.factories import MissionInstanceFactory

        crisis = open_crisis(self.domain, origin=CrisisOrigin.STAFF)
        instance = MissionInstanceFactory()
        crisis.minted_mission = instance
        crisis.save(update_fields=["minted_mission"])

        resolved = resolve_crisis_for_mission(instance)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.resolution, CrisisResolution.MISSION_COMPLETED)

    def test_house_feed_carries_open_crises(self):
        from world.tidings.services import house_feed_for

        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        # Generated crises spawn covert (#2837) — surface it for the feed check.
        crisis.surfaces_at = None
        crisis.save(update_fields=["surfaces_at"])
        items = house_feed_for(self.org)
        kinds = [item.kind for item in items]
        self.assertIn("crisis", kinds)
        crisis_item = next(item for item in items if item.kind == "crisis")
        self.assertIn("Testvale", crisis_item.headline)

    def test_serializer_helper_lists_open_crises_with_options(self):
        from world.societies.serializers import _house_open_crises

        _make_type(
            "Protests",
            DomainCrisisSeverity.TROUBLE,
            [CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT],
        )
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        # Covert until surfaced or swept (#2837): hidden even from its target.
        self.assertEqual(_house_open_crises(self.org), [])
        crisis.surfaces_at = None
        crisis.save(update_fields=["surfaces_at"])
        rows = _house_open_crises(self.org)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["domain_name"], "Testvale")
        kinds = {opt["kind"] for opt in row["options"]}
        self.assertEqual(kinds, {CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT})
        pay = next(o for o in row["options"] if o["kind"] == CrisisResolutionKind.PAY)
        self.assertEqual(pay["cost_coppers"], 1000)  # TROUBLE = 1x base


class CrisisOptionApiTests(TestCase):
    """POST /api/societies/organizations/{id}/crisis-option/ (#2238)."""

    @classmethod
    def setUpTestData(cls):
        from rest_framework.test import APIClient

        cls.APIClient = APIClient
        cls.org = OrganizationFactory(name="House Api")
        cls.area = AreaFactory()
        cls.domain = create_domain(area=cls.area, name="Apivale", owner_org=cls.org)
        _make_type("Protests", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.WAIT])
        cls.crisis = open_crisis(cls.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        # Surface it (#2837): the API card list hides covert crises.
        cls.crisis.surfaces_at = None
        cls.crisis.save(update_fields=["surfaces_at"])

    def _leader_account(self):
        """An account whose active character's persona leads the org."""
        from world.magic.services.gain import account_for_sheet
        from world.roster.factories import RosterTenureFactory
        from world.societies.models import OrganizationRank

        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        persona = sheet.primary_persona
        rank = OrganizationRank.objects.filter(organization=self.org, tier=1).first()
        if rank is None:
            rank = OrganizationRankFactory(organization=self.org, tier=1, name="Head")
        if not rank.can_manage_ranks:
            rank.can_manage_ranks = True
            rank.save(update_fields=["can_manage_ranks"])
        OrganizationMembership.objects.create(organization=self.org, persona=persona, rank=rank)
        return account_for_sheet(sheet)

    def test_leader_chooses_wait_via_api(self):
        client = self.APIClient()
        client.force_authenticate(user=self._leader_account())
        option = self.crisis.crisis_type.options.first()
        response = client.post(
            f"/api/societies/organizations/{self.org.pk}/crisis-option/",
            {"crisis": self.crisis.pk, "option": option.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.crisis.refresh_from_db()
        self.assertEqual(self.crisis.chosen_option, option)
        self.assertEqual(response.data["open_crises"][0]["chosen_kind"], "wait")

    def test_non_authority_rejected(self):
        from world.magic.services.gain import account_for_sheet
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        persona = tenure.roster_entry.character_sheet.primary_persona
        # Plain member (no leadership rank): sees the org, lacks authority.
        from world.societies.models import OrganizationRank

        rank = OrganizationRank.objects.filter(organization=self.org, tier=5).first()
        if rank is None:
            rank = OrganizationRankFactory(organization=self.org, tier=5, name="Rabble")
        OrganizationMembership.objects.create(organization=self.org, persona=persona, rank=rank)
        client = self.APIClient()
        client.force_authenticate(user=account_for_sheet(tenure.roster_entry.character_sheet))
        option = self.crisis.crisis_type.options.first()
        response = client.post(
            f"/api/societies/organizations/{self.org.pk}/crisis-option/",
            {"crisis": self.crisis.pk, "option": option.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.crisis.refresh_from_db()
        self.assertIsNone(self.crisis.chosen_option)


class ThreatLoopEngineTests(TestCase):
    """The generated threat/opportunity loop (#2837)."""

    @classmethod
    def setUpTestData(cls):
        cls.org = OrganizationFactory(name="House Loop")
        cls.area = AreaFactory()
        cls.domain = create_domain(area=cls.area, name="Loopvale", owner_org=cls.org)

    @staticmethod
    def _typed(name, *, valence, audience, severity=DomainCrisisSeverity.TROUBLE):
        from world.societies.houses.constants import CrisisResolutionKind

        ctype = DomainCrisisType.objects.create(
            name=name, default_severity=severity, valence=valence, audience=audience
        )
        DomainCrisisTypeOption.objects.create(
            crisis_type=ctype, kind=CrisisResolutionKind.WAIT, self_resolve_pct=0, worsen_pct=0
        )
        return ctype

    def test_generated_crisis_is_covert_then_intel_reveals(self):
        from world.societies.houses.constants import CrisisIntelSource
        from world.societies.houses.crisis_services import grant_crisis_intel, org_knows_of
        from world.societies.serializers import _house_open_crises

        _make_type("Quiet Trouble", DomainCrisisSeverity.TROUBLE, [CrisisResolutionKind.PAY])
        crisis = open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        self.assertIsNotNone(crisis.surfaces_at)
        self.assertFalse(crisis.is_surfaced)
        self.assertFalse(org_knows_of(crisis, self.org))
        self.assertEqual(_house_open_crises(self.org), [])
        # And its income malus has not hit the books yet.
        self.assertEqual(crisis.income_factor, 1.0)

        grant_crisis_intel(crisis, self.org, source=CrisisIntelSource.SPY_SWEEP)
        self.assertTrue(org_knows_of(crisis, self.org))
        self.assertEqual(len(_house_open_crises(self.org)), 1)

    def test_threat_and_opportunity_can_coexist_but_not_two_threats(self):
        from world.societies.houses.constants import CrisisAudience, CrisisValence

        self._typed("Windfall", valence=CrisisValence.OPPORTUNITY, audience=CrisisAudience.DOMAIN)
        threat = open_crisis(self.domain, origin=CrisisOrigin.STAFF)
        self.assertIsNotNone(threat)
        self.assertIsNone(open_crisis(self.domain, origin=CrisisOrigin.STAFF))
        opportunity = open_crisis(
            self.domain,
            origin=CrisisOrigin.AMBIENT,
            crisis_type=DomainCrisisType.objects.get(name="Windfall"),
        )
        self.assertIsNotNone(opportunity)

    def test_opportunity_expires_on_wait_tick(self):
        from datetime import timedelta

        from django.utils import timezone

        from world.societies.houses.constants import CrisisAudience, CrisisValence

        ctype = self._typed(
            "Fading Window", valence=CrisisValence.OPPORTUNITY, audience=CrisisAudience.DOMAIN
        )
        crisis = open_crisis(self.domain, origin=CrisisOrigin.AMBIENT, crisis_type=ctype)
        DomainCrisisType.objects.filter(pk=ctype.pk)  # noop keep-alive
        crisis.opened_at = timezone.now() - timedelta(days=30)
        crisis.save(update_fields=["opened_at"])
        crisis_wait_tick(rng=_FixedRng(0.99))
        crisis.refresh_from_db()
        self.assertEqual(crisis.resolution, CrisisResolution.EXPIRED)

    def test_generation_tick_spawns_for_domain_and_eligible_org(self):
        from world.currency.constants import IncomeStreamKind
        from world.currency.models import OrgIncomeStream
        from world.societies.houses.constants import CrisisAudience, CrisisValence
        from world.societies.houses.crisis_services import crisis_generation_tick
        from world.societies.houses.models import DomainCrisis

        self._typed("Domain Trouble", valence=CrisisValence.THREAT, audience=CrisisAudience.DOMAIN)
        self._typed("Org Trouble", valence=CrisisValence.THREAT, audience=CrisisAudience.ORG)
        self._typed("Org Windfall", valence=CrisisValence.OPPORTUNITY, audience=CrisisAudience.ORG)
        racket_org = OrganizationFactory(name="The Loop Syndicate")
        OrgIncomeStream.objects.create(
            organization=racket_org,
            name="river toll",
            kind=IncomeStreamKind.CRIME_KICKUP,
            gross_amount=400,
        )
        opened = crisis_generation_tick(rng=_FixedRng(0.0))
        self.assertGreaterEqual(opened, 3)
        self.assertTrue(DomainCrisis.objects.filter(domain=self.domain).exists())
        self.assertTrue(DomainCrisis.objects.filter(org=racket_org).exists())

    def test_org_threat_skims_stream_accrual_once_surfaced(self):
        from world.currency.constants import IncomeStreamKind
        from world.currency.models import OrgIncomeStream
        from world.currency.services import accrue_income_stream
        from world.societies.houses.constants import CrisisAudience, CrisisValence

        ctype = self._typed(
            "Org Squeeze", valence=CrisisValence.THREAT, audience=CrisisAudience.ORG
        )
        stream = OrgIncomeStream.objects.create(
            organization=self.org,
            name="stall rents",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=1000,
        )
        crisis = open_crisis(org=self.org, origin=CrisisOrigin.AMBIENT, crisis_type=ctype)
        # Covert: no bite yet.
        accrue_income_stream(stream)
        stream.refresh_from_db()
        self.assertEqual(stream.uncollected_pool, 1000)
        # Surfaced TROUBLE: 0.9 factor.
        crisis.surfaces_at = None
        crisis.save(update_fields=["surfaces_at"])
        accrue_income_stream(stream)
        stream.refresh_from_db()
        self.assertEqual(stream.uncollected_pool, 1900)

    def test_choose_mission_option_mints_the_mission(self):
        from world.missions.factories import MissionNodeFactory, MissionTemplateFactory

        template = MissionTemplateFactory()
        MissionNodeFactory(template=template, is_entry=True)
        ctype = _make_type(
            "Confrontable",
            DomainCrisisSeverity.TROUBLE,
            [CrisisResolutionKind.MISSION, CrisisResolutionKind.WAIT],
            mission_template=template,
        )
        crisis = open_crisis(self.domain, origin=CrisisOrigin.STAFF, crisis_type=ctype)
        persona = _leader_of(self.org)
        option = ctype.options.get(kind=CrisisResolutionKind.MISSION)
        choose_crisis_option(crisis, persona, option)
        crisis.refresh_from_db()
        self.assertIsNotNone(crisis.minted_mission_id)
        resolved = resolve_crisis_for_mission(crisis.minted_mission)
        self.assertEqual(resolved.resolution, CrisisResolution.MISSION_COMPLETED)

    def test_org_crisis_judged_by_org_leadership(self):
        from world.societies.houses.constants import CrisisAudience, CrisisValence

        ctype = self._typed("Org Matter", valence=CrisisValence.THREAT, audience=CrisisAudience.ORG)
        crisis = open_crisis(org=self.org, origin=CrisisOrigin.AMBIENT, crisis_type=ctype)
        outsider = PersonaFactory()
        option = ctype.options.first()
        with self.assertRaises(CrisisServiceError):
            choose_crisis_option(crisis, outsider, option)
        leader = _leader_of(self.org)
        chosen = choose_crisis_option(crisis, leader, option)
        self.assertIsNotNone(chosen.chosen_at)


def _leader_of(org):
    from world.societies.models import OrganizationRank

    persona = PersonaFactory()
    rank = OrganizationRank.objects.filter(organization=org, tier=1).first()
    if rank is None:
        rank = OrganizationRankFactory(organization=org, tier=1, name="Head")
    if not rank.can_manage_ranks:
        rank.can_manage_ranks = True
        rank.save(update_fields=["can_manage_ranks"])
    OrganizationMembership.objects.create(organization=org, persona=persona, rank=rank)
    return persona
