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
)
from world.combat.models import FleeConfig
from world.combat.services import (
    add_participant,
    begin_declaration_phase,
    cleanup_completed_encounter,
    declare_flee,
    join_encounter,
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
