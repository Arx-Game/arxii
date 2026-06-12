"""Tests for combat-owned CharacterEngagement lifecycle wiring (#872, Task 6)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import FleeConfig
from world.combat.services import (
    add_participant,
    begin_declaration_phase,
    cleanup_completed_encounter,
    declare_flee,
    join_encounter,
    remove_participant,
    resolve_round,
)
from world.covenants.factories import CovenantRoleFactory
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import CharacterEngagementFactory
from world.mechanics.services import begin_engagement
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class EngagementLifecycleWiringTests(TestCase):
    """Combat owns the CharacterEngagement lifecycle (#872)."""

    def setUp(self):
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character

    def test_add_participant_creates_combat_engagement(self):
        sheet = CharacterSheetFactory()
        add_participant(self.encounter, sheet)
        eng = CharacterEngagement.objects.get(character=sheet.character)
        self.assertEqual(eng.engagement_type, EngagementType.COMBAT)

    def test_join_encounter_creates_combat_engagement(self):
        self.encounter.status = EncounterStatus.DECLARING
        self.encounter.save(update_fields=["status"])
        sheet = CharacterSheetFactory()
        join_encounter(self.encounter, sheet)
        eng = CharacterEngagement.objects.get(character=sheet.character)
        self.assertEqual(eng.engagement_type, EngagementType.COMBAT)

    def test_begin_declaration_phase_backfills_engagements(self):
        self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        CombatOpponentFactory(encounter=self.encounter)
        CharacterEngagement.objects.filter(character=self.character).delete()

        begin_declaration_phase(self.encounter)

        eng = CharacterEngagement.objects.get(character=self.character)
        self.assertEqual(eng.engagement_type, EngagementType.COMBAT)

    def test_cleanup_deletes_combat_engagements(self):
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)

        cleanup_completed_encounter(self.encounter)

        self.assertFalse(CharacterEngagement.objects.filter(character=self.character).exists())

    def test_cleanup_preserves_noncombat_engagement(self):
        CharacterEngagementFactory(
            character=self.character, engagement_type=EngagementType.CHALLENGE
        )

        cleanup_completed_encounter(self.encounter)

        eng = CharacterEngagement.objects.get(character=self.character)
        self.assertEqual(eng.engagement_type, EngagementType.CHALLENGE)

    def test_flee_success_deletes_engagement(self):
        # Lower speed rank than NPC_SPEED_RANK (15) → the fleer resolves first.
        fast_role = CovenantRoleFactory(speed_rank=3)
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=fast_role,
        )
        begin_engagement(sheet.character, EngagementType.COMBAT, source=encounter)
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=CheckTypeFactory())
        declare_flee(participant)

        success = CheckOutcomeFactory(name="EngagementFleeSuccess", success_level=0)
        with force_check_outcome(success):
            resolve_round(encounter)

        participant.refresh_from_db()
        self.assertEqual(participant.status, ParticipantStatus.FLED)
        self.assertFalse(
            CharacterEngagement.objects.filter(character=sheet.character).exists()
        )

    def test_remove_participant_deletes_engagement(self):
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)
        remove_participant(self.participant)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, ParticipantStatus.REMOVED)
        self.assertFalse(
            CharacterEngagement.objects.filter(character=self.character).exists()
        )

    def test_flee_failure_preserves_engagement(self):
        # A failed flee (success_level < FLEE_PARTIAL_SUCCESS_LEVEL) leaves
        # the participant ACTIVE and the combat engagement intact.
        fast_role = CovenantRoleFactory(speed_rank=3)
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        CombatOpponentFactory(encounter=encounter)
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            covenant_role=fast_role,
        )
        begin_engagement(sheet.character, EngagementType.COMBAT, source=encounter)
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=CheckTypeFactory())
        declare_flee(participant)

        # success_level=-2 is below FLEE_PARTIAL_SUCCESS_LEVEL (-1) → no escape.
        failure = CheckOutcomeFactory(name="EngagementFleeFailure", success_level=-2)
        with force_check_outcome(failure):
            resolve_round(encounter)

        participant.refresh_from_db()
        self.assertEqual(participant.status, ParticipantStatus.ACTIVE)
        self.assertTrue(
            CharacterEngagement.objects.filter(character=sheet.character).exists()
        )


class EscalationRoundWiringTests(TestCase):
    """begin_declaration_phase ticks escalation + installs room spike triggers (#872)."""

    def setUp(self):
        self.curve = EscalationCurveFactory(start_round=2, intensity_step=2)
        self.encounter = CombatEncounterFactory(
            escalation_curve=self.curve, status=EncounterStatus.BETWEEN_ROUNDS
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, status=ParticipantStatus.ACTIVE
        )
        self.character = self.participant.character_sheet.character
        CombatOpponentFactory(encounter=self.encounter)

    def _seed_trigger_definitions(self):
        """Create the two TriggerDefinitions the install helper looks up.

        Task 8 ships the real seeded content; for these wiring tests a minimal
        TriggerDefinition (name + event_name + any FlowDefinition) suffices.
        """
        from flows.models import FlowDefinition, TriggerDefinition

        flow, _ = FlowDefinition.objects.get_or_create(name="escalation-test-noop-flow")
        for name, event_name in (
            ("escalation_spike_on_incapacitated", "character_incapacitated"),
            ("escalation_spike_on_killed", "character_killed"),
        ):
            TriggerDefinition.objects.get_or_create(
                name=name, defaults={"event_name": event_name, "flow_definition": flow}
            )

    def _run_rounds(self, count):
        """Drive begin_declaration_phase ``count`` times, cycling status back."""
        for _ in range(count):
            self.encounter.status = EncounterStatus.BETWEEN_ROUNDS
            self.encounter.save(update_fields=["status"])
            begin_declaration_phase(self.encounter)

    def _engagement(self):
        return CharacterEngagement.objects.get(character=self.character)

    def test_begin_declaration_phase_ticks_escalating_encounter(self):
        # Round 1 is below start_round (2): no tick. Round 2 ticks once.
        self._run_rounds(2)
        eng = self._engagement()
        self.assertEqual(eng.escalation_level, 1)
        self.assertEqual(eng.intensity_modifier, self.curve.intensity_step)

    def test_no_tick_for_non_escalating_encounter(self):
        self.encounter.escalation_curve = None
        self.encounter.save(update_fields=["escalation_curve"])
        self._run_rounds(2)
        eng = self._engagement()
        self.assertEqual(eng.escalation_level, 0)
        self.assertEqual(eng.intensity_modifier, 0)

    def test_room_trigger_installed_once(self):
        from flows.models import Trigger

        self._seed_trigger_definitions()
        self._run_rounds(2)
        room = self.encounter.room
        for name in (
            "escalation_spike_on_incapacitated",
            "escalation_spike_on_killed",
        ):
            self.assertEqual(
                Trigger.objects.filter(obj=room, trigger_definition__name=name).count(),
                1,
            )

    def test_install_noops_without_seeded_definitions(self):
        from flows.models import Trigger

        self._run_rounds(1)
        self.assertFalse(Trigger.objects.filter(obj=self.encounter.room).exists())

    def test_cleanup_removes_room_trigger(self):
        from flows.models import Trigger

        self._seed_trigger_definitions()
        self._run_rounds(1)
        self.assertTrue(Trigger.objects.filter(obj=self.encounter.room).exists())

        cleanup_completed_encounter(self.encounter)

        self.assertFalse(Trigger.objects.filter(obj=self.encounter.room).exists())

    def test_cleanup_keeps_trigger_when_room_shared(self):
        from flows.models import Trigger

        self._seed_trigger_definitions()
        self._run_rounds(1)
        room = self.encounter.room
        other = CombatEncounterFactory(
            escalation_curve=self.curve,
            room=room,
            status=EncounterStatus.BETWEEN_ROUNDS,
        )

        cleanup_completed_encounter(self.encounter)
        self.assertTrue(Trigger.objects.filter(obj=room).exists())

        # Mirror resolve_round's real ordering: the first encounter's COMPLETED
        # status is persisted before the second encounter ever cleans up.
        self.encounter.status = EncounterStatus.COMPLETED
        self.encounter.save(update_fields=["status"])

        cleanup_completed_encounter(other)
        self.assertFalse(Trigger.objects.filter(obj=room).exists())
