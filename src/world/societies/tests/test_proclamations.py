"""Proclamation & edict tests (#2842, ADR-0178)."""

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.checks.test_helpers import force_check_outcome
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.societies.houses.services import create_domain
from world.societies.models import SocietyReputation, StanceArchetype
from world.societies.proclamations import (
    ProclamationError,
    active_edict,
    edict_weekly_tick,
    enact_edict,
    issue_proclamation,
    revoke_edict,
)
from world.traits.factories import CheckOutcomeFactory


def _stance(**axes):
    return StanceArchetype.objects.create(name=f"Stance {len(axes)}-{sorted(axes)}", **axes)


def _rep(persona, society):
    row = SocietyReputation.objects.filter(persona=persona, society=society).first()
    return row.value if row else 0


class ProclamationReceptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.checks.factories import CheckTypeFactory
        from world.roster.factories import RosterEntryFactory

        CheckTypeFactory(name="Persuasion")
        cls.win = CheckOutcomeFactory(name="proc win", success_level=2)
        cls.flop = CheckOutcomeFactory(name="proc flop", success_level=-1)
        cls.persona = RosterEntryFactory().character_sheet.primary_persona
        cls.traditionalists = SocietyFactory(change=-4)
        cls.radicals = SocietyFactory(change=4)

    def test_success_wins_support_and_softens_opposition(self):
        stance = _stance(change_delta=-2)  # a traditionalist position
        with force_check_outcome(self.win):
            issue_proclamation(self.persona, stance)
        gained = _rep(self.persona, self.traditionalists)
        lost = _rep(self.persona, self.radicals)
        self.assertGreater(gained, 0)
        self.assertLess(lost, 0)
        # Mitigation: the provocation is smaller than the (mirrored) support.
        self.assertLess(abs(lost), abs(gained))

    def test_failure_wins_nobody_and_offends_fully(self):
        stance = _stance(change_delta=-2)
        with force_check_outcome(self.flop):
            issue_proclamation(self.persona, stance)
        self.assertEqual(_rep(self.persona, self.traditionalists), 0)
        self.assertLess(_rep(self.persona, self.radicals), 0)

    def test_org_speech_requires_leadership(self):
        org = OrganizationFactory()
        OrganizationMembershipFactory(organization=org, persona=self.persona)  # plain member
        stance = _stance(mercy_delta=1)
        with self.assertRaises(ProclamationError):
            issue_proclamation(self.persona, stance, org=org)

    def test_prose_is_stored_never_required(self):
        stance = _stance(power_delta=1)
        with force_check_outcome(self.win):
            row = issue_proclamation(self.persona, stance, prose="PLACEHOLDER speech text")
        self.assertEqual(row.prose, "PLACEHOLDER speech text")
        self.assertEqual(row.check_outcome, self.win)


class EdictTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.checks.factories import CheckTypeFactory
        from world.roster.factories import RosterEntryFactory
        from world.societies.models import OrganizationRank

        CheckTypeFactory(name="Persuasion")
        cls.win = CheckOutcomeFactory(name="edict win", success_level=1)
        cls.org = OrganizationFactory(name="House Edict")
        cls.domain = create_domain(area=AreaFactory(), name="Edictvale", owner_org=cls.org)
        cls.leader = RosterEntryFactory().character_sheet.primary_persona
        rank = OrganizationRank.objects.filter(organization=cls.org, tier=1).first()
        if not rank.can_manage_ranks:
            rank.can_manage_ranks = True
            rank.save(update_fields=["can_manage_ranks"])
        OrganizationMembershipFactory(organization=cls.org, persona=cls.leader, rank=rank)

    @staticmethod
    def _kind(name, **payload):
        from world.societies.houses.models import EdictKind

        stance = StanceArchetype.objects.create(name=f"{name} Stance", change_delta=-1)
        return EdictKind.objects.create(name=name, stance=stance, **payload)

    def test_enact_proclaims_and_swaps(self):
        first = self._kind("Doubled Watch", weekly_unrest_delta=1)
        second = self._kind("Open Hand", weekly_unrest_delta=-2)
        with force_check_outcome(self.win):
            edict = enact_edict(self.domain, first, self.leader)
        self.assertIsNotNone(edict.proclamation_id)
        self.assertEqual(edict.proclamation.org, self.org)
        with force_check_outcome(self.win):
            enact_edict(self.domain, second, self.leader)
        self.assertEqual(active_edict(self.domain.pk).kind, second)
        first_edict = self.domain.edicts.get(kind=first)
        self.assertIsNotNone(first_edict.revoked_at)

    def test_outsider_cannot_enact(self):
        from world.roster.factories import RosterEntryFactory

        outsider = RosterEntryFactory().character_sheet.primary_persona
        kind = self._kind("Forbidden Rule")
        with self.assertRaises(ProclamationError):
            enact_edict(self.domain, kind, outsider)

    def test_weekly_tick_applies_unrest_and_upkeep(self):
        from world.currency.services import get_or_create_treasury

        treasury = get_or_create_treasury(self.org)
        treasury.balance = 10_000
        treasury.save(update_fields=["balance"])
        kind = self._kind("Costly Order", weekly_unrest_delta=3, weekly_upkeep_coppers=1_000)
        with force_check_outcome(self.win):
            enact_edict(self.domain, kind, self.leader)
        before_unrest = self.domain.unrest
        edict_weekly_tick()
        self.domain.refresh_from_db()
        treasury.refresh_from_db()
        self.assertEqual(self.domain.unrest, min(100, before_unrest + 3))
        self.assertEqual(treasury.balance, 9_000)

    def test_edict_scales_stream_accrual(self):
        from world.currency.services import accrue_income_stream
        from world.societies.houses.models import HoldingKind
        from world.societies.houses.services import add_holding

        holding_kind = HoldingKind.objects.create(
            name="Edict Farm", stream_kind="domain_tax", base_gross=1_000
        )
        holding = add_holding(domain=self.domain, kind=holding_kind)
        kind = self._kind("Tax Squeeze", income_gross_pct=25)
        with force_check_outcome(self.win):
            enact_edict(self.domain, kind, self.leader)
        accrue_income_stream(holding.income_stream)
        holding.income_stream.refresh_from_db()
        # base 1000 × domain income_multiplier (prosperity 50 → 1.0) × 1.25
        self.assertEqual(holding.income_stream.uncollected_pool, 1_250)

    def test_revoke_clears(self):
        kind = self._kind("Brief Rule")
        with force_check_outcome(self.win):
            enact_edict(self.domain, kind, self.leader)
        self.assertEqual(revoke_edict(self.domain, self.leader), 1)
        self.assertIsNone(active_edict(self.domain.pk))


class SeedTests(TestCase):
    def test_seed_idempotent(self):
        from world.seeds.proclamations import ensure_edict_kinds, ensure_stance_archetypes

        self.assertEqual(ensure_stance_archetypes(), 9)
        self.assertEqual(ensure_edict_kinds(), 6)
        self.assertEqual(ensure_stance_archetypes(), 0)
        self.assertEqual(ensure_edict_kinds(), 0)
