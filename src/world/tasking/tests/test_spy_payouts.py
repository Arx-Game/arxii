"""Spy Job Kit payout tests (#2833)."""

from datetime import timedelta

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret, SecretGossip
from world.secrets.services import author_secret
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.tasking.constants import TaskStatus, TaskTargetKind
from world.tasking.exceptions import TargetConsentError
from world.tasking.factories import (
    OrgTaskFactory,
    TaskOutcomeRouteFactory,
    TaskTemplateFactory,
)
from world.tasking.services import assign_agent, create_task, resolve_task
from world.traits.factories import CheckOutcomeFactory


class SpyPayoutTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.assets.factories import NPCAssetFactory

        cls.org = OrganizationFactory()
        cls.win = CheckOutcomeFactory(name="spy job win", success_level=2)
        cls.asset = NPCAssetFactory()
        cls.handler = cls.asset.promoter_persona
        OrganizationMembershipFactory(organization=cls.org, persona=cls.handler)

    def _resolve(self, template, **target_kwargs):
        task = OrgTaskFactory(
            template=template, org=self.org, issued_by=self.handler, **target_kwargs
        )
        with force_check_outcome(self.win):
            assign_agent(task, self.asset, self.handler)
        with force_check_outcome(self.win):
            fulfillment = resolve_task(task)
        task.refresh_from_db()
        return task, fulfillment


class UnmaskPayoutTests(SpyPayoutTestBase):
    def test_unmask_grants_persona_link_and_discovery(self):
        from world.scenes.models import PersonaDiscovery

        mark_sheet_persona = PersonaFactory()  # ESTABLISHED — a mask
        handler_entry = RosterEntryFactory(character_sheet=self.handler.character_sheet)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, unmask_target=True)
        _, fulfillment = self._resolve(template, target_persona=mark_sheet_persona)
        self.assertIn("mask slips", fulfillment.report)
        self.assertTrue(
            PersonaDiscovery.objects.filter(discovered_by=handler_entry.character_sheet).exists()
        )

    def test_true_face_reports_clean(self):
        true_face = RosterEntryFactory().character_sheet.primary_persona
        self.assertEqual(true_face.persona_type, PersonaType.PRIMARY)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, unmask_target=True)
        _, fulfillment = self._resolve(template, target_persona=true_face)
        self.assertIn("exactly who they claim", fulfillment.report)


class MovementsPayoutTests(SpyPayoutTestBase):
    def test_quiet_mark_reports_no_public_trace(self):
        mark = PersonaFactory()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, movements_report=True)
        _, fulfillment = self._resolve(template, target_persona=mark)
        self.assertIn("kept out of public view", fulfillment.report)


class GossipPayoutTests(SpyPayoutTestBase):
    def _mark_with_gossip(self, heat=20):
        subject = RosterEntryFactory()
        secret = author_secret(
            subject_sheet=subject.character_sheet,
            provenance=SecretProvenance.GM_AUTHORED,
            level=2,
            content="PLACEHOLDER a real skeleton in a real closet.",
        )
        from world.areas.factories import AreaFactory

        gossip = SecretGossip.objects.create(secret=secret, region=AreaFactory(), heat=heat)
        return subject.character_sheet.primary_persona, gossip

    def test_whisper_campaign_raises_heat(self):
        mark, gossip = self._mark_with_gossip()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, gossip_heat_delta=15)
        self._resolve(template, target_persona=mark)
        gossip.refresh_from_db()
        self.assertEqual(gossip.heat, 35)

    def test_quash_cools_heat_and_is_not_offensive(self):
        from world.tasking.spy_payouts import template_is_offensive

        mark, gossip = self._mark_with_gossip()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, gossip_heat_delta=-15)
        self.assertFalse(template_is_offensive(template))
        self._resolve(template, target_persona=mark)
        gossip.refresh_from_db()
        self.assertEqual(gossip.heat, 5)


class SabotagePayoutTests(SpyPayoutTestBase):
    def test_sabotage_drops_building_condition(self):
        from world.areas.factories import AreaFactory
        from world.buildings.factories import BuildingFactory

        area = AreaFactory()
        room = RoomProfileFactory()
        room.area = area
        room.save(update_fields=["area"])
        building = BuildingFactory(area=area, condition_tier=3)
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ROOM)
        TaskOutcomeRouteFactory(
            template=template, outcome_tier=self.win, building_condition_delta=-1
        )
        _, fulfillment = self._resolve(template, target_room=room)
        building.refresh_from_db()
        self.assertEqual(building.condition_tier, 2)
        self.assertIn("wrecked", fulfillment.report)


class RecruitPayoutTests(SpyPayoutTestBase):
    def test_suborn_gains_org_claim_on_npc(self):
        from world.assets.models import NPCAsset

        npc_persona = PersonaFactory()  # no tenure: an NPC
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, recruit_target=True)
        self._resolve(template, target_persona=npc_persona)
        self.assertTrue(
            NPCAsset.objects.filter(promoter_org=self.org, asset_persona=npc_persona).exists()
        )

    def test_suborn_refuses_pcs(self):
        from world.seeds.consent import seed_social_consent_categories

        seed_social_consent_categories()
        pc_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=pc_entry, player_number=1)
        pc = pc_entry.character_sheet.primary_persona
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, recruit_target=True)
        # Note: recruit is offensive, so issuing against a PC needs consent —
        # this exercises the consent gate instead of the payout no-op.
        with self.assertRaises(TargetConsentError):
            create_task(template, self.org, self.handler, target_persona=pc)


class ResiduePayoutTests(SpyPayoutTestBase):
    def test_residue_mints_secret_about_the_handler(self):
        mark = PersonaFactory()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, incriminate_level=3)
        _, fulfillment = self._resolve(template, target_persona=mark)
        residue = Secret.objects.filter(subject_sheet=self.handler.character_sheet, level=3).first()
        self.assertIsNotNone(residue)
        self.assertIn("arranged", residue.content)
        # Residue is never confessed to the handler in their own report.
        self.assertNotIn("arranged", fulfillment.report)


class ConsentGateTests(SpyPayoutTestBase):
    def test_offensive_job_against_pc_refuses_at_issue(self):
        from world.seeds.consent import seed_social_consent_categories

        seed_social_consent_categories()
        pc_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=pc_entry, player_number=1)
        pc = pc_entry.character_sheet.primary_persona
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.handler.character_sheet),
            player_number=1,
        )
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, movements_report=True)
        with self.assertRaises(TargetConsentError):
            create_task(template, self.org, self.handler, target_persona=pc)

    def test_npc_target_is_ungated(self):
        npc = PersonaFactory()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.PERSONA
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, movements_report=True)
        task = create_task(template, self.org, self.handler, target_persona=npc)
        self.assertEqual(task.status, TaskStatus.OPEN)


class DomainPayoutTests(SpyPayoutTestBase):
    def _domain(self, name, **kwargs):
        from world.areas.factories import AreaFactory
        from world.societies.houses.models import Domain

        return Domain.objects.create(
            area=AreaFactory(), name=name, owner_org=OrganizationFactory(), **kwargs
        )

    def test_survey_reports_domain_state(self):
        domain = self._domain("Surveyed March", population=4200, prosperity=61, unrest=33)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.DOMAIN
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, domain_report=True)
        _, fulfillment = self._resolve(template, target_domain=domain)
        self.assertIn("4200 souls", fulfillment.report)
        self.assertIn("prosperity 61/100", fulfillment.report)
        self.assertIn("unrest 33/100", fulfillment.report)

    def test_foment_unrest_raises_and_clamps(self):
        domain = self._domain("Restless March", unrest=95)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.DOMAIN
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, domain_unrest_delta=10)
        self._resolve(template, target_domain=domain)
        domain.refresh_from_db()
        self.assertEqual(domain.unrest, 100)

    def test_soothe_unrest_is_defensive(self):
        from world.tasking.spy_payouts import template_is_offensive

        domain = self._domain("Soothed March", unrest=40)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.DOMAIN
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, domain_unrest_delta=-10)
        self.assertFalse(template_is_offensive(template))
        self._resolve(template, target_domain=domain)
        domain.refresh_from_db()
        self.assertEqual(domain.unrest, 30)


class OrgPayoutTests(SpyPayoutTestBase):
    def test_case_reports_membership_and_coffers(self):
        rival = OrganizationFactory()
        OrganizationMembershipFactory(organization=rival)
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, organization_report=True)
        _, fulfillment = self._resolve(template, target_org=rival)
        self.assertIn("1 sworn member", fulfillment.report)
        self.assertIn("coffers run empty", fulfillment.report)

    def test_assay_counts_units(self):
        from world.military.factories import MilitaryUnitFactory

        rival = OrganizationFactory()
        MilitaryUnitFactory(owner_org=rival, name="The Grey Halberds")
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, military_report=True)
        _, fulfillment = self._resolve(template, target_org=rival)
        self.assertIn("fields 1 unit(s)", fulfillment.report)
        self.assertIn("The Grey Halberds", fulfillment.report)

    def test_assay_on_bannerless_org(self):
        rival = OrganizationFactory()
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, military_report=True)
        _, fulfillment = self._resolve(template, target_org=rival)
        self.assertIn("no soldiery worth the name", fulfillment.report)

    def test_offensive_job_against_pc_led_org_refuses(self):
        from world.seeds.consent import seed_social_consent_categories

        seed_social_consent_categories()
        rival = OrganizationFactory()
        leader_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=leader_entry, player_number=1)
        OrganizationMembershipFactory(
            organization=rival,
            persona=leader_entry.character_sheet.primary_persona,
            rank=1,
        )
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, organization_report=True)
        with self.assertRaises(TargetConsentError):
            create_task(template, self.org, self.handler, target_org=rival)

    def test_npc_led_org_is_ungated(self):
        rival = OrganizationFactory()
        OrganizationMembershipFactory(organization=rival, rank=1)  # NPC leader: no tenure
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, organization_report=True)
        task = create_task(template, self.org, self.handler, target_org=rival)
        self.assertEqual(task.status, TaskStatus.OPEN)


class SeedTests(TestCase):
    def test_seed_creates_templates_when_outcomes_exist(self):
        from world.checks.factories import CheckTypeFactory
        from world.seeds.spy_tasks import ensure_spy_task_templates
        from world.tasking.models import TaskTemplate

        CheckTypeFactory(name="Stealth")
        CheckOutcomeFactory(name="seed best", success_level=3)
        CheckOutcomeFactory(name="seed worst", success_level=-2)
        self.assertEqual(ensure_spy_task_templates(), 14)
        self.assertEqual(ensure_spy_task_templates(), 0)
        sabotage = TaskTemplate.objects.get(name="Sabotage the Works")
        self.assertEqual(sabotage.target_kind, TaskTargetKind.ROOM)
        self.assertIsNotNone(sabotage.consequence_pool)
        assay = TaskTemplate.objects.get(name="Assay Their Strength")
        self.assertEqual(assay.target_kind, TaskTargetKind.ORG)


class ThreatLoopPayoutTests(SpyPayoutTestBase):
    """Sweep / counter / inflame / exploit against generated crises (#2837)."""

    def _rival_domain_crisis(self, *, valence=None):
        from world.areas.factories import AreaFactory
        from world.societies.houses.constants import (
            CrisisAudience,
            CrisisOrigin,
            CrisisValence,
        )
        from world.societies.houses.crisis_services import open_crisis
        from world.societies.houses.models import DomainCrisisType
        from world.societies.houses.services import create_domain

        rival = OrganizationFactory()
        domain = create_domain(area=AreaFactory(), name=f"Rivalvale {rival.pk}", owner_org=rival)
        ctype = DomainCrisisType.objects.create(
            name=f"Trouble {rival.pk}",
            valence=valence or CrisisValence.THREAT,
            audience=CrisisAudience.DOMAIN,
        )
        crisis = open_crisis(domain, origin=CrisisOrigin.AMBIENT, crisis_type=ctype)
        return rival, domain, crisis

    def test_sweep_reveals_covert_crisis_and_mints_intel(self):
        from world.societies.houses.models import CrisisIntel

        _rival, domain, crisis = self._rival_domain_crisis()
        self.assertFalse(crisis.is_surfaced)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.DOMAIN
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, reveal_schemes=True)
        _, fulfillment = self._resolve(template, target_domain=domain)
        self.assertIn("uncovers", fulfillment.report)
        self.assertTrue(CrisisIntel.objects.filter(crisis=crisis, org=self.org).exists())

    def test_sweep_own_org_names_hostile_tasks(self):
        from world.tasking.factories import TaskFulfillmentFactory

        rival = OrganizationFactory(name="The Watching Rival")
        hostile_template = TaskTemplateFactory(
            name="Case Our Books",
            duration=timedelta(days=1),
            target_kind=TaskTargetKind.ORG,
        )
        hostile = OrgTaskFactory(template=hostile_template, org=rival, target_org=self.org)
        TaskFulfillmentFactory(task=hostile, is_active=True)

        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, reveal_schemes=True)
        _, fulfillment = self._resolve(template, target_org=self.org)
        self.assertIn("Case Our Books", fulfillment.report)
        self.assertIn("The Watching Rival", fulfillment.report)

    def test_counter_resolves_trouble(self):
        from world.societies.houses.constants import CrisisResolution

        _, _, crisis = self._rival_domain_crisis()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.CRISIS
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, crisis_severity_delta=-1)
        self._resolve(template, target_crisis=crisis)
        crisis.refresh_from_db()
        self.assertEqual(crisis.resolution, CrisisResolution.TASK_COMPLETED)

    def test_inflame_steps_severity_up(self):
        from world.societies.houses.constants import DomainCrisisSeverity

        _, _, crisis = self._rival_domain_crisis()
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.CRISIS
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, crisis_severity_delta=1)
        self._resolve(template, target_crisis=crisis)
        crisis.refresh_from_db()
        self.assertEqual(crisis.severity, DomainCrisisSeverity.CRISIS)

    def test_exploit_pays_the_issuing_org(self):
        from world.currency.services import get_or_create_treasury
        from world.societies.houses.constants import CrisisResolution, CrisisValence

        _, _, crisis = self._rival_domain_crisis(valence=CrisisValence.OPPORTUNITY)
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.CRISIS
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, exploit_crisis=True)
        before = get_or_create_treasury(self.org).balance
        self._resolve(template, target_crisis=crisis)
        crisis.refresh_from_db()
        self.assertEqual(crisis.resolution, CrisisResolution.EXPLOITED)
        self.assertGreater(get_or_create_treasury(self.org).balance, before)

    def test_inflaming_pc_led_target_needs_consent(self):
        from world.seeds.consent import seed_social_consent_categories
        from world.societies.models import OrganizationRank

        seed_social_consent_categories()
        rival, _, crisis = self._rival_domain_crisis()
        leader_entry = RosterEntryFactory()
        RosterTenureFactory(roster_entry=leader_entry, player_number=1)
        rank = OrganizationRank.objects.filter(organization=rival, tier=1).first()
        OrganizationMembershipFactory(
            organization=rival,
            persona=leader_entry.character_sheet.primary_persona,
            rank=rank or 1,
        )
        template = TaskTemplateFactory(
            duration=timedelta(days=1), target_kind=TaskTargetKind.CRISIS
        )
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, crisis_severity_delta=1)
        with self.assertRaises(TargetConsentError):
            create_task(template, self.org, self.handler, target_crisis=crisis)


class StaturePayoutTests(SpyPayoutTestBase):
    """#3091 — true-vs-believed stature reads + whisper campaigns."""

    def _mark_org(self, true_total=10_000, perceived_total=10_000):
        from world.societies.houses.models import HouseStature

        target = OrganizationFactory(name="House Mark")
        HouseStature.objects.create(
            organization=target, true_total=true_total, perceived_total=perceived_total
        )
        return target

    def test_org_report_reads_true_vs_believed(self):
        target = self._mark_org(true_total=12_000, perceived_total=8_000)
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(template=template, outcome_tier=self.win, organization_report=True)
        _, fulfillment = self._resolve(template, target_org=target)
        self.assertIn("True stature 12000 against a repute of 8000", fulfillment.report)
        self.assertIn("stronger than the world believes", fulfillment.report)

    def test_whisper_campaign_erodes_perceived_within_bounds(self):
        from world.societies.houses.constants import STATURE_WHISPER_MAX_DISPLACEMENT
        from world.societies.houses.models import HouseStature

        target = self._mark_org()
        template = TaskTemplateFactory(duration=timedelta(days=1), target_kind=TaskTargetKind.ORG)
        TaskOutcomeRouteFactory(
            template=template, outcome_tier=self.win, whisper_stature_delta=50_000
        )
        _, fulfillment = self._resolve(template, target_org=target)
        stature = HouseStature.objects.get(organization=target)
        floor = round(10_000 * (1 - STATURE_WHISPER_MAX_DISPLACEMENT))
        self.assertEqual(stature.perceived_total, floor)
        self.assertIn("repute erodes", fulfillment.report)
