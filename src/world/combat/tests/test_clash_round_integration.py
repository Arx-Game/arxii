"""Integration tests for the clash post-pass wired into resolve_round (Task 5.3)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    ActionCategory,
    ClashActionSlot,
    ClashStatus,
    EncounterStatus,
    OpponentTier,
    ParticipantStatus,
)
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    StrainConfigFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    Clash,
    ClashContribution,
    ClashContributionDeclaration,
    ClashRound,
    CombatEncounter,
    CombatOpponentAction,
    CombatRoundAction,
)
from world.combat.services import resolve_round
from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class ResolveRoundClashIntegrationTests(TestCase):
    """Integration tests for the clash post-pass in resolve_round.

    These tests verify that:
    - resolve_round includes clash_outcomes when clashes are active
    - detect_clash_opportunities fires during each resolve_round call
    - ClashContributionDeclaration rows are consumed and deleted per round
    - Atomic rollback works: if run_clash_round raises, the whole round rolls back
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config_strain = StrainConfigFactory()
        cls.config_clash = ClashConfigFactory()
        cls.check_type = ActionTemplateFactory().check_type
        # Seed CheckOutcome rows used by meter-band / threshold logic.
        cls.outcome_critical = CheckOutcomeFactory(name="ri_critical", success_level=3)
        cls.outcome_great = CheckOutcomeFactory(name="ri_great", success_level=2)
        cls.outcome_success = CheckOutcomeFactory(name="ri_success", success_level=1)
        cls.outcome_partial = CheckOutcomeFactory(name="ri_partial", success_level=0)
        cls.outcome_failure = CheckOutcomeFactory(name="ri_failure", success_level=-1)
        cls.outcome_botch = CheckOutcomeFactory(name="ri_botch", success_level=-2)
        from world.conditions.factories import DamageSuccessLevelMultiplierFactory

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="RI Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="RI Partial"
        )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _make_encounter(self, *, round_number: int = 1) -> CombatEncounter:
        return CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=round_number,
        )

    def _make_participant(self, encounter: CombatEncounter) -> object:
        sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=sheet.character, current=30, maximum=30)
        CharacterEngagementFactory(character=sheet.character)
        CharacterVitals.objects.create(character_sheet=sheet, health=100)
        return CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )

    def _make_technique(self) -> object:
        template = ActionTemplateFactory(check_type=self.check_type)
        return TechniqueFactory(
            intensity=5,
            control=10,
            anima_cost=3,
            action_template=template,
        )

    def _make_opponent(self, encounter: CombatEncounter) -> object:
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        return CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )

    def _add_npc_action(
        self,
        opponent: object,
        *,
        round_number: int = 1,
        clash_capable: bool = False,
    ) -> object:
        """Write a CombatOpponentAction row for the NPC."""
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(
            pool=pool,
            attack_category=ActionCategory.PHYSICAL,
            clash_capable=clash_capable,
        )
        opponent.threat_pool = pool
        opponent.save(update_fields=["threat_pool"])
        return CombatOpponentAction.objects.create(
            opponent=opponent,
            threat_entry=entry,
            round_number=round_number,
        )

    # ---------------------------------------------------------------------------
    # 1. No clashes → clash_outcomes == []
    # ---------------------------------------------------------------------------

    def test_resolve_round_with_no_clashes(self) -> None:
        """A normal resolve_round with no clashes runs without error; clash_outcomes is empty."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)
        opponent = self._make_opponent(encounter)

        # Provide an NPC action so the round can proceed.
        self._add_npc_action(opponent, round_number=1)

        # Give the PC a passive (pass) action.
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
        )

        result = resolve_round(encounter)

        self.assertEqual(result.clash_outcomes, [])

    # ---------------------------------------------------------------------------
    # 2. detect_clash_opportunities fires during resolve_round
    # ---------------------------------------------------------------------------

    def test_clash_opportunity_detected_during_resolve(self) -> None:
        """When a PC and NPC both have clash-capable actions, a Clash row is created."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)

        # Create an opponent with a clash-capable pool entry.
        pool = ThreatPoolFactory()
        npc_entry = ThreatPoolEntryFactory(
            pool=pool,
            clash_capable=True,
            base_damage=10,
        )
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        # Write the NPC action with a clash-capable entry.
        CombatOpponentAction.objects.create(
            opponent=opponent,
            threat_entry=npc_entry,
            round_number=1,
        )

        # Build a clash-capable PC technique.
        pool_consequence = ConsequencePoolFactory()
        technique = self._make_technique()
        technique.clash_capable = True
        technique.clash_resolution_pool = pool_consequence
        technique.save(update_fields=["clash_capable", "clash_resolution_pool"])

        # PC action: clash-capable technique aimed at the opponent.
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        result = resolve_round(encounter)

        # A Clash row should have been created.
        self.assertTrue(
            Clash.objects.filter(encounter=encounter, status=ClashStatus.ACTIVE).exists(),
            "Expected a Clash row to be created by detect_clash_opportunities.",
        )
        # The post-pass runs on the newly-created clash this same round.
        self.assertEqual(len(result.clash_outcomes), 1)

    # ---------------------------------------------------------------------------
    # 3. Declared contribution drives the meter
    # ---------------------------------------------------------------------------

    def test_declared_contribution_drives_meter(self) -> None:
        """An active Clash + a ClashContributionDeclaration → meter moves after resolve_round."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)
        opponent = self._make_opponent(encounter)

        self._add_npc_action(opponent, round_number=1)

        # Create an active Clash manually.
        pool_consequence = ConsequencePoolFactory()
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            status=ClashStatus.ACTIVE,
            progress=0,
            pc_win_threshold=20,
            npc_win_threshold=20,
            resolution_consequence_pool=pool_consequence,
        )

        technique = self._make_technique()

        # Create the declaration before entering the force context (no check yet).
        ClashContributionDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            clash=clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=technique,
            strain_commitment=0,
        )

        # Give the PC a regular round action so resolve_round doesn't short-circuit.
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
        )

        # Force a check outcome so the contribution has a deterministic delta.
        with force_check_outcome(self.outcome_success):
            result = resolve_round(encounter)

        # A ClashContribution row should exist (meter was driven).
        self.assertTrue(
            ClashContribution.objects.filter(
                clash_round__clash=clash,
            ).exists(),
            "Expected a ClashContribution audit row to exist after the post-pass.",
        )
        # clash_outcomes carries the result.
        self.assertEqual(len(result.clash_outcomes), 1)

        clash.refresh_from_db()
        self.assertNotEqual(clash.progress, 0, "Clash meter should have moved from 0.")

    # ---------------------------------------------------------------------------
    # 4. Declarations are deleted after the post-pass
    # ---------------------------------------------------------------------------

    def test_declarations_cleaned_up_after_post_pass(self) -> None:
        """ClashContributionDeclaration rows are deleted after round's post-pass completes."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)
        opponent = self._make_opponent(encounter)

        self._add_npc_action(opponent, round_number=1)

        pool_consequence = ConsequencePoolFactory()
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            status=ClashStatus.ACTIVE,
            progress=0,
            pc_win_threshold=20,
            npc_win_threshold=20,
            resolution_consequence_pool=pool_consequence,
        )

        technique = self._make_technique()

        ClashContributionDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            clash=clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=technique,
            strain_commitment=0,
        )

        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
        )

        with force_check_outcome(self.outcome_success):
            resolve_round(encounter)

        # All declarations for this round should have been deleted.
        remaining = ClashContributionDeclaration.objects.filter(
            encounter=encounter,
            round_number=1,
        ).count()
        self.assertEqual(remaining, 0, "All ClashContributionDeclaration rows should be deleted.")

    # ---------------------------------------------------------------------------
    # 5. Resolved clash appears in outcomes; subsequent rounds don't re-process
    # ---------------------------------------------------------------------------

    def test_resolved_clash_appears_in_outcomes(self) -> None:
        """A clash that crosses its threshold during the post-pass is RESOLVED and in outcomes."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)
        opponent = self._make_opponent(encounter)

        self._add_npc_action(opponent, round_number=1)

        pool_consequence = ConsequencePoolFactory()
        # Set pc_win_threshold=1 so a single success resolves the clash.
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            status=ClashStatus.ACTIVE,
            progress=0,
            pc_win_threshold=1,
            npc_win_threshold=1,
            resolution_consequence_pool=pool_consequence,
        )

        technique = self._make_technique()

        ClashContributionDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            clash=clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=technique,
            strain_commitment=0,
        )

        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
        )

        # Force a critical success so the clash resolves decisively.
        with force_check_outcome(self.outcome_critical):
            result = resolve_round(encounter)

        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.RESOLVED, "Clash should be RESOLVED.")
        self.assertEqual(len(result.clash_outcomes), 1)

        # --- Round 2: the resolved clash is NOT re-processed ---
        encounter.round_number = 2
        encounter.status = EncounterStatus.DECLARING
        encounter.save(update_fields=["round_number", "status"])

        opponent.health = 30
        opponent.save(update_fields=["health"])

        entry2 = ThreatPoolEntryFactory(pool=opponent.threat_pool)
        CombatOpponentAction.objects.create(
            opponent=opponent,
            threat_entry=entry2,
            round_number=2,
        )

        CombatRoundAction.objects.create(
            participant=participant,
            round_number=2,
        )

        result2 = resolve_round(encounter)
        self.assertEqual(
            result2.clash_outcomes,
            [],
            "No clash_outcomes expected for a RESOLVED clash in the next round.",
        )

    def test_resolved_clash_broadcasts_outcome_narration(self) -> None:
        """A clash resolving during the post-pass broadcasts a Narrator OUTCOME line (#644).

        The PC's bare CombatRoundAction (no technique) and the targetless NPC
        action never produce a "resolves" narration, so the clash outcome line
        is the only OUTCOME interaction matching that token.
        """
        encounter = self._make_encounter()
        encounter.scene = SceneFactory()
        encounter.save(update_fields=["scene"])
        participant = self._make_participant(encounter)
        opponent = self._make_opponent(encounter)

        self._add_npc_action(opponent, round_number=1)

        pool_consequence = ConsequencePoolFactory()
        clash = ClashFactory(
            encounter=encounter,
            npc_opponent=opponent,
            status=ClashStatus.ACTIVE,
            progress=0,
            pc_win_threshold=1,
            npc_win_threshold=1,
            resolution_consequence_pool=pool_consequence,
        )

        technique = self._make_technique()
        ClashContributionDeclaration.objects.create(
            encounter=encounter,
            round_number=1,
            participant=participant,
            clash=clash,
            action_slot=ClashActionSlot.FOCUSED,
            technique=technique,
            strain_commitment=0,
        )
        CombatRoundAction.objects.create(participant=participant, round_number=1)

        with force_check_outcome(self.outcome_critical):
            resolve_round(encounter)

        clash.refresh_from_db()
        self.assertEqual(clash.status, ClashStatus.RESOLVED, "Clash should be RESOLVED.")
        outcomes = Interaction.objects.filter(
            mode=InteractionMode.OUTCOME, content__icontains="resolves"
        )
        self.assertEqual(outcomes.count(), 1, "Expected one clash OUTCOME narration line.")

    # ---------------------------------------------------------------------------
    # 6. Atomic rollback: if run_clash_round raises, nothing persists
    # ---------------------------------------------------------------------------

    def test_atomic_rollback_on_run_clash_round_failure(self) -> None:
        """Atomic rollback: detect creates a Clash, run_clash_round raises, all rolls back."""
        encounter = self._make_encounter()
        participant = self._make_participant(encounter)

        # Create an opponent with a clash-capable pool entry.
        pool = ThreatPoolFactory()
        npc_entry = ThreatPoolEntryFactory(
            pool=pool,
            clash_capable=True,
            base_damage=10,
        )
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        # NPC action: clash-capable.
        CombatOpponentAction.objects.create(
            opponent=opponent,
            threat_entry=npc_entry,
            round_number=1,
        )

        # Build a clash-capable PC technique.
        pool_consequence = ConsequencePoolFactory()
        technique = self._make_technique()
        technique.clash_capable = True
        technique.clash_resolution_pool = pool_consequence
        technique.save(update_fields=["clash_capable", "clash_resolution_pool"])

        # PC action: clash-capable technique aimed at the opponent.
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        # Record the clash count before the failure.
        initial_clash_count = Clash.objects.count()

        # Patch run_clash_round to simulate failure AFTER detection runs.
        with patch(
            "world.combat.clash.run_clash_round",
            side_effect=RuntimeError("simulated clash failure"),
        ):
            with self.assertRaises(RuntimeError):
                resolve_round(encounter)

        # The transaction should have rolled back entirely.
        # No new Clash rows should exist (detection's creation was rolled back).
        final_clash_count = Clash.objects.count()
        self.assertEqual(
            final_clash_count,
            initial_clash_count,
            "Clash rows created by detection should be rolled back.",
        )

        # No ClashRound rows should exist.
        self.assertFalse(
            ClashRound.objects.exists(),
            "No ClashRound should be written when resolve_round rolls back.",
        )
