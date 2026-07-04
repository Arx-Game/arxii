"""E2E: a servant petitions their Court master for a permanent grant raise (#1718)."""

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import get_condition_instance
from world.covenants.constants import CovenantType
from world.covenants.court_grant import ensure_court_grant_role
from world.covenants.factories import CovenantFactory
from world.covenants.services import (
    active_court_pact_for,
    get_court_grant_config,
    swear_court_pact,
)
from world.npc_services.models import NPCStanding
from world.npc_services.services import (
    adjust_npc_affection,
    end_interaction,
    resolve_offer,
    start_interaction,
)
from world.traits.factories import CheckOutcomeFactory


class CourtGrantPetitionE2ETests(TestCase):
    def setUp(self):
        self.master_sheet = CharacterSheetFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=self.master_sheet)
        self.servant_sheet = CharacterSheetFactory()
        # CharacterSheetFactory auto-provisions a PRIMARY persona per sheet
        # (the invariant enforced by a partial unique constraint) — reuse it
        # rather than creating a second PRIMARY persona for the same sheet,
        # which would collide on that constraint.
        self.master_persona = self.master_sheet.primary_persona
        self.servant_persona = self.servant_sheet.primary_persona
        swear_court_pact(
            covenant=self.covenant, servant_sheet=self.servant_sheet, granted_pull_cap=1
        )
        # Enough affection to raise the ceiling to 1 + 30//10 = 4.
        adjust_npc_affection(self.servant_persona, self.master_persona, delta=30)
        self.role = ensure_court_grant_role(self.covenant)

    def test_successful_petition_raises_the_grant(self):
        offer = self.role.offers.get(kind="court_grant")
        success_outcome = CheckOutcomeFactory(name="petition_success", success_level=1)
        session = start_interaction(
            role=self.role,
            persona=self.servant_persona,
            character=self.servant_sheet.character,
            npc_persona=self.master_persona,
        )
        with force_check_outcome(success_outcome):
            result = resolve_offer(session, offer)
        end_interaction(session)

        pact = active_court_pact_for(covenant=self.covenant, servant_sheet=self.servant_sheet)
        # Deterministic: ceiling = base_headroom(1) + affection(30)//affection_divisor(10) = 4.
        self.assertEqual(pact.granted_pull_cap, 4)
        self.assertEqual(result.kind, "court_grant")

        standing = NPCStanding.objects.get(
            persona=self.servant_persona, npc_persona=self.master_persona
        )
        self.assertEqual(standing.consecutive_failed_petitions, 0)

    def test_failed_petition_does_not_raise_the_grant_but_records_the_outcome(self):
        offer = self.role.offers.get(kind="court_grant")
        failure_outcome = CheckOutcomeFactory(name="petition_failure", success_level=0)
        session = start_interaction(
            role=self.role,
            persona=self.servant_persona,
            character=self.servant_sheet.character,
            npc_persona=self.master_persona,
        )
        with force_check_outcome(failure_outcome):
            result = resolve_offer(session, offer)
        end_interaction(session)

        pact = active_court_pact_for(covenant=self.covenant, servant_sheet=self.servant_sheet)
        self.assertEqual(pact.granted_pull_cap, 1)
        self.assertEqual(result.kind, "court_grant")

        standing = NPCStanding.objects.get(
            persona=self.servant_persona, npc_persona=self.master_persona
        )
        self.assertEqual(standing.consecutive_failed_petitions, 1)

    def test_no_active_pact_returns_graceful_message(self):
        other_sheet = CharacterSheetFactory()
        other_persona = other_sheet.primary_persona
        offer = self.role.offers.get(kind="court_grant")
        session = start_interaction(
            role=self.role,
            persona=other_persona,
            character=other_sheet.character,
            npc_persona=self.master_persona,
        )
        result = resolve_offer(session, offer)
        end_interaction(session)

        self.assertEqual(result.kind, "court_grant")
        self.assertTrue(result.message)
        self.assertIsNone(active_court_pact_for(covenant=self.covenant, servant_sheet=other_sheet))

    def test_escalation_pool_fires_after_consecutive_failure_threshold(self):
        """Crossing the consecutive-failure threshold fires the master's escalation pool."""
        failure_outcome = CheckOutcomeFactory(name="petition_wrath_failure", success_level=0)
        condition = ConditionTemplateFactory(name="Master's Wrath")
        consequence = ConsequenceFactory(outcome_tier=failure_outcome)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            target=EffectTarget.SELF,
            condition_template=condition,
            condition_severity=1,
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        config = get_court_grant_config()
        config.petition_failure_escalation_threshold = 1
        config.escalation_consequence_pool = pool
        config.save(
            update_fields=["petition_failure_escalation_threshold", "escalation_consequence_pool"]
        )

        offer = self.role.offers.get(kind="court_grant")
        session = start_interaction(
            role=self.role,
            persona=self.servant_persona,
            character=self.servant_sheet.character,
            npc_persona=self.master_persona,
        )
        with force_check_outcome(failure_outcome):
            resolve_offer(session, offer)
        end_interaction(session)

        instance = get_condition_instance(self.servant_sheet.character, condition)
        self.assertIsNotNone(instance)
