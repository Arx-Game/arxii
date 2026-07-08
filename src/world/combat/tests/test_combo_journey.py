"""E2E journey test for team finisher combo (#2017).

Tests the full journey: multi-PC declare → detect → upgrade → resolve_round
→ fused payoff (rider on every contributor) → ComboLearning written →
discovery ceremony fired → combo picker shows learned combo on next round.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    ENTITY_TYPE_PC,
    ActionCategory,
    ComboLearningMethod,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction, ComboLearning
from world.combat.services import (
    detect_available_combos,
    resolve_round,
    upgrade_action_to_combo,
)
from world.covenants.factories import CovenantRoleFactory
from world.fatigue.models import FatiguePool
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class ComboJourneyTests(TestCase):
    """E2E test: the full combo discovery + fused payoff journey."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack (Journey)", base_power=20)
        cls.effect_buff = EffectTypeFactory(name="Buff (Journey)", base_power=None)
        cls.gift = GiftFactory()

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        self.pool = ThreatPoolFactory()
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            health=1000,
            max_health=1000,
            soak_value=50,
            threat_pool=self.pool,
        )

        self.participants: list = []
        self.actions: list = []

        # Create two PCs with techniques matching different combo slots.
        self._setup_pc(effect=self.effect_attack, speed_rank=5)
        self._setup_pc(effect=self.effect_buff, speed_rank=3)

        # Create a 2-slot combo: Attack + Buff.
        achievement = AchievementFactory(
            name="Journey Combo Discovery",
            hidden=True,
        )
        self.combo = ComboDefinitionFactory(
            discoverable_via_combat=True,
            bonus_damage=50,
            bypass_soak=True,
            discovery_first_body="A new combo has been discovered in battle!",
            discovery_personal_body="You have discovered a new combo.",
        )
        self.combo.discovery_achievement = achievement
        self.combo.save()
        from world.combat.factories import ComboSlotFactory

        ComboSlotFactory(
            combo=self.combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=self.combo,
            slot_number=2,
            required_action_type=self.effect_buff,
        )

    def _setup_pc(self, *, effect: object, speed_rank: int) -> None:
        """Create a PC participant with a technique matching the given effect type."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(speed_rank=speed_rank)
        participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=sheet,
            covenant_role=role,
        )
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=50, maximum=50)
        FatiguePool.objects.create(character_sheet=sheet)
        CharacterEngagementFactory(character=sheet.character)
        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=effect,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=self.opponent,
        )
        self.participants.append(participant)
        self.actions.append(action)

    def test_full_combo_journey(self) -> None:
        """Multi-PC declare → detect → upgrade → resolve → fused payoff + discovery."""
        # 1. Detect available combos — should find our 2-slot combo.
        available = detect_available_combos(self.encounter, 1)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].combo, self.combo)
        self.assertFalse(available[0].known_by_participant)  # nobody knows it yet

        # 2. Both PCs upgrade their actions to the combo.
        for action in self.actions:
            upgrade_action_to_combo(action, self.combo)

        # 3. Resolve the round.
        result = resolve_round(self.encounter)

        # 4. Verify fused payoff: every contributor's outcome has combo_used set.
        pc_outcomes = [o for o in result.action_outcomes if o.entity_type == ENTITY_TYPE_PC]
        self.assertEqual(len(pc_outcomes), 2)
        for outcome in pc_outcomes:
            self.assertIsNotNone(outcome.combo_used)
            self.assertEqual(outcome.combo_used, self.combo)
            # Each contributor should have damage results (the combo rider at minimum).
            self.assertTrue(len(outcome.damage_results) > 0)

        # 5. Verify ComboLearning was written for each participant.
        for participant in self.participants:
            # Use values_list to bypass SharedMemoryModel identity map cache.
            learning_data = (
                ComboLearning.objects.filter(
                    combo=self.combo,
                    character_sheet=participant.character_sheet,
                )
                .values_list("learned_via", "use_count")
                .first()
            )
            self.assertIsNotNone(learning_data)
            self.assertEqual(learning_data[0], ComboLearningMethod.COMBAT)
            self.assertGreaterEqual(learning_data[1], 1)

        # 6. Verify discovery ceremony fired — achievement granted.
        for participant in self.participants:
            self.assertTrue(
                CharacterAchievement.objects.filter(
                    achievement=self.combo.discovery_achievement,
                    character_sheet=participant.character_sheet,
                ).exists()
            )

        # 7. Verify the opponent took damage (combo bonus_damage = 50, bypasses soak).
        self.opponent.refresh_from_db()
        self.assertLess(self.opponent.health, self.opponent.max_health)

    def test_learned_combo_surfaces_in_picker(self) -> None:
        """After discovery, the combo shows as known_by_participant=True."""
        # First, resolve a round with the combo to trigger discovery.
        for action in self.actions:
            upgrade_action_to_combo(action, self.combo)
        resolve_round(self.encounter)

        # Advance to round 2 — re-declare and detect.
        self.encounter.refresh_from_db()
        self.encounter.round_number = 2
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.save(update_fields=["round_number", "status"])

        # Re-declare actions for round 2.
        for participant, action in zip(self.participants, self.actions, strict=False):
            CombatRoundAction.objects.create(
                participant=participant,
                round_number=2,
                focused_category=ActionCategory.PHYSICAL,
                focused_action=action.focused_action,
                focused_opponent_target=self.opponent,
            )

        available = detect_available_combos(self.encounter, 2)
        self.assertEqual(len(available), 1)
        self.assertTrue(available[0].known_by_participant)  # now known

    def test_single_contributor_combo_still_works(self) -> None:
        """A single-PC combo still resolves (backward compatibility)."""
        # Only upgrade one PC's action.
        upgrade_action_to_combo(self.actions[0], self.combo)

        result = resolve_round(self.encounter)

        pc_outcomes = [o for o in result.action_outcomes if o.entity_type == ENTITY_TYPE_PC]
        # The upgrader should have combo_used set.
        upgrader_outcomes = [o for o in pc_outcomes if o.combo_used is not None]
        self.assertEqual(len(upgrader_outcomes), 1)

        # ComboLearning should be written for the upgrader.
        self.assertTrue(
            ComboLearning.objects.filter(
                combo=self.combo,
                character_sheet=self.participants[0].character_sheet,
            ).exists()
        )
