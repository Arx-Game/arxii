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


class SeedTests(TestCase):
    def test_seed_creates_templates_when_outcomes_exist(self):
        from world.checks.factories import CheckTypeFactory
        from world.seeds.spy_tasks import ensure_spy_task_templates
        from world.tasking.models import TaskTemplate

        CheckTypeFactory(name="Stealth")
        CheckOutcomeFactory(name="seed best", success_level=3)
        CheckOutcomeFactory(name="seed worst", success_level=-2)
        self.assertEqual(ensure_spy_task_templates(), 6)
        self.assertEqual(ensure_spy_task_templates(), 0)
        sabotage = TaskTemplate.objects.get(name="Sabotage the Works")
        self.assertEqual(sabotage.target_kind, TaskTargetKind.ROOM)
        self.assertIsNotNone(sabotage.consequence_pool)
