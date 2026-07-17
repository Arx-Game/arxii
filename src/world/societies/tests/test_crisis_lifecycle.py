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
        open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
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
        open_crisis(self.domain, origin=CrisisOrigin.UNREST, rng=_FixedRng())
        rows = _house_open_crises(self.org)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["domain_name"], "Testvale")
        kinds = {opt["kind"] for opt in row["options"]}
        self.assertEqual(kinds, {CrisisResolutionKind.PAY, CrisisResolutionKind.WAIT})
        pay = next(o for o in row["options"] if o["kind"] == CrisisResolutionKind.PAY)
        self.assertEqual(pay["cost_coppers"], 1000)  # TROUBLE = 1x base
