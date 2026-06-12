"""Tests for encounter aftermath (#876): outcome fields, rules, completion seam."""

from unittest.mock import MagicMock, patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.factories import (
    ActionTemplateFactory,
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from flows.constants import EventName
from world.achievements.models import StatDefinition
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.checks.types import CheckResult
from world.combat.achievement_counters import (
    STAT_KEY_ENCOUNTERS_FLED,
    STAT_KEY_ENCOUNTERS_LOST,
    STAT_KEY_ENCOUNTERS_WON,
)
from world.combat.constants import (
    ActionCategory,
    EncounterOutcome,
    EncounterStatus,
    OpponentStatus,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EncounterAftermathRuleFactory,
    ThreatPoolFactory,
)
from world.combat.interaction_services import render_encounter_outcome_narration
from world.combat.models import CombatEncounter, CombatParticipant, CombatRoundAction
from world.combat.services import _classify_encounter_outcome, complete_encounter, resolve_round
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class EncounterOutcomeFieldTests(TestCase):
    def test_encounter_outcome_defaults_empty(self) -> None:
        encounter = CombatEncounterFactory()
        self.assertEqual(encounter.outcome, "")
        self.assertIsNone(encounter.completed_at)


class EncounterAftermathRuleTests(TestCase):
    def test_unique_per_outcome_risk_cell(self) -> None:
        EncounterAftermathRuleFactory(outcome=EncounterOutcome.DEFEAT, risk_level=RiskLevel.LETHAL)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EncounterAftermathRuleFactory(
                outcome=EncounterOutcome.DEFEAT, risk_level=RiskLevel.LETHAL
            )


class RenderEncounterOutcomeNarrationTests(TestCase):
    def test_victory_names_victors_and_defeated(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.VICTORY,
            active_labels=["Alaric", "Bryn"],
            fled_labels=[],
            defeated_opponent_labels=["Gravewight"],
        )
        self.assertIn("victory", narration.lower())
        self.assertIn("Alaric and Bryn", narration)
        self.assertIn("Gravewight", narration)

    def test_fled_outcome_names_the_scattered(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.FLED,
            active_labels=[],
            fled_labels=["Alaric"],
            defeated_opponent_labels=[],
        )
        self.assertIn("Alaric", narration)
        self.assertIn("fled", narration.lower())

    def test_defeat_names_the_fallen(self) -> None:
        narration = render_encounter_outcome_narration(
            outcome=EncounterOutcome.DEFEAT,
            active_labels=["Alaric", "Bryn"],
            fled_labels=["Cael"],
            defeated_opponent_labels=[],
        )
        self.assertIn("Alaric and Bryn can fight no longer", narration)
        self.assertIn("Cael fled the field", narration)


class _CompletionSeamTestBase(TestCase):
    """Shared helpers for completion-seam tests (#876 Task 4)."""

    def _make_encounter(self, **overrides: object) -> CombatEncounter:
        defaults: dict[str, object] = {
            "scene": SceneFactory(),
            "status": EncounterStatus.BETWEEN_ROUNDS,
        }
        defaults.update(overrides)
        return CombatEncounterFactory(**defaults)

    def _add_pc(
        self,
        encounter: CombatEncounter,
        status: str = ParticipantStatus.ACTIVE,
    ) -> CombatParticipant:
        sheet = CharacterSheetFactory()
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        return CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=status,
        )

    def _outcome_interaction_qs(self, encounter: CombatEncounter):
        return Interaction.objects.filter(scene=encounter.scene, mode=InteractionMode.OUTCOME)


class ClassifyEncounterOutcomeTests(_CompletionSeamTestBase):
    """Tests for _classify_encounter_outcome (#876 spec §1)."""

    def test_no_active_opponents_is_victory(self) -> None:
        encounter = self._make_encounter()
        CombatOpponentFactory(encounter=encounter, status=OpponentStatus.DEFEATED)
        self._add_pc(encounter)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.VICTORY)

    def test_no_active_pcs_with_fled_is_fled(self) -> None:
        encounter = self._make_encounter()
        CombatOpponentFactory(encounter=encounter)
        self._add_pc(encounter, status=ParticipantStatus.FLED)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.FLED)

    def test_downed_active_pc_is_defeat(self) -> None:
        """An ACTIVE-status PC who cannot act (KO'd) leaves the encounter DEFEAT."""
        from world.conditions.constants import FoundationalCapability
        from world.conditions.factories import (
            CapabilityTypeFactory,
            ConditionCapabilityEffectFactory,
            UnconsciousConditionFactory,
        )
        from world.conditions.services import apply_condition

        encounter = self._make_encounter()
        CombatOpponentFactory(encounter=encounter)
        participant = self._add_pc(encounter)
        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        condition = UnconsciousConditionFactory()
        ConditionCapabilityEffectFactory(condition=condition, capability=awareness, value=-100)
        apply_condition(target=participant.character_sheet.character, condition=condition)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.DEFEAT)

    def test_all_removed_no_fled_is_defeat(self) -> None:
        encounter = self._make_encounter()
        CombatOpponentFactory(encounter=encounter)
        self._add_pc(encounter, status=ParticipantStatus.REMOVED)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.DEFEAT)


class CompleteEncounterTests(_CompletionSeamTestBase):
    """Tests for the complete_encounter seam (#876 spec §2-§7)."""

    def _seed_rule_with_pool(
        self,
        outcome: EncounterOutcome,
        risk_level: str,
        success_level: int = -1,
    ) -> tuple:
        """Seed an aftermath rule cell whose pool has one consequence at a tier."""
        tier = CheckOutcomeFactory(
            name=f"AftermathTier{outcome}{success_level}", success_level=success_level
        )
        consequence = ConsequenceFactory(outcome_tier=tier, character_loss=False)
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        rule = EncounterAftermathRuleFactory(
            outcome=outcome,
            risk_level=risk_level,
            consequence_pool=pool,
        )
        return rule, pool, consequence, tier

    def test_sets_fields_and_creates_outcome_interaction(self) -> None:
        encounter = self._make_encounter()
        participant = self._add_pc(encounter)
        CombatOpponentFactory(
            encounter=encounter, status=OpponentStatus.DEFEATED, name="Gravewight"
        )

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        encounter.refresh_from_db()
        self.assertEqual(encounter.status, EncounterStatus.COMPLETED)
        self.assertEqual(encounter.outcome, EncounterOutcome.VICTORY)
        self.assertIsNotNone(encounter.completed_at)

        interaction = self._outcome_interaction_qs(encounter).get()
        self.assertIn(participant.character_sheet.character.key, interaction.content)
        self.assertIn("Gravewight", interaction.content)

    def test_double_completion_raises(self) -> None:
        encounter = self._make_encounter()
        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)
        with self.assertRaises(ValueError):
            complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

    def test_abandoned_skips_aftermath_and_counters_but_narrates(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)
        self._seed_rule_with_pool(EncounterOutcome.ABANDONED, encounter.risk_level)

        complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)

        self.assertEqual(ConsequenceOutcome.objects.count(), 0)
        self.assertFalse(
            StatDefinition.objects.filter(
                key__in=[
                    STAT_KEY_ENCOUNTERS_WON,
                    STAT_KEY_ENCOUNTERS_LOST,
                    STAT_KEY_ENCOUNTERS_FLED,
                ]
            ).exists()
        )
        self.assertTrue(self._outcome_interaction_qs(encounter).exists())

    def test_aftermath_rule_applies_per_active_participant_on_defeat(self) -> None:
        encounter = self._make_encounter()
        pc_one = self._add_pc(encounter)
        pc_two = self._add_pc(encounter)
        self._add_pc(encounter, status=ParticipantStatus.FLED)
        rule, pool, consequence, tier = self._seed_rule_with_pool(
            EncounterOutcome.DEFEAT, encounter.risk_level
        )

        forced = CheckResult(
            check_type=rule.check_type,
            outcome=tier,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=forced,
        ):
            complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        outcomes = list(ConsequenceOutcome.objects.all())
        self.assertEqual(len(outcomes), 2)
        interaction = self._outcome_interaction_qs(encounter).get()
        for outcome_row in outcomes:
            self.assertEqual(outcome_row.combat_interaction, interaction)
            self.assertEqual(outcome_row.pool, pool)
            self.assertEqual(outcome_row.selected_consequence, consequence)
        self.assertEqual(
            {o.character for o in outcomes},
            {pc_one.character_sheet, pc_two.character_sheet},
        )

    def test_null_pool_rule_cell_records_nothing(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)
        EncounterAftermathRuleFactory(
            outcome=EncounterOutcome.DEFEAT,
            risk_level=encounter.risk_level,
            consequence_pool=None,
        )

        complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        self.assertEqual(ConsequenceOutcome.objects.count(), 0)

    def test_opponent_aftermath_pool_fires_on_victory(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)
        pool = ConsequencePoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            status=OpponentStatus.DEFEATED,
            aftermath_pool=pool,
        )

        # Capture at call time: cleanup deletes the ephemeral NPC ObjectDB
        # afterwards, which nulls the instance's pk in place.
        captured: dict[str, object] = {}

        def _capture(*, pool: object, context: object) -> list:
            captured["pool"] = pool
            captured["character_pk"] = context.character.pk
            captured["scene"] = context.scene
            return []

        with patch(
            "world.checks.consequence_resolution.apply_pool_deterministically",
            side_effect=_capture,
        ) as mock_apply:
            complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        mock_apply.assert_called_once()
        self.assertEqual(captured["pool"], pool)
        self.assertEqual(captured["character_pk"], opponent.objectdb_id)
        self.assertEqual(captured["scene"], encounter.scene)

    def test_opponent_aftermath_pool_skipped_on_defeat(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)
        pool = ConsequencePoolFactory()
        CombatOpponentFactory(
            encounter=encounter,
            status=OpponentStatus.DEFEATED,
            aftermath_pool=pool,
        )

        with patch(
            "world.checks.consequence_resolution.apply_pool_deterministically"
        ) as mock_apply:
            complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        mock_apply.assert_not_called()

    def test_counters_increment_won_and_fled_on_victory(self) -> None:
        encounter = self._make_encounter()
        active = self._add_pc(encounter)
        fled = self._add_pc(encounter, status=ParticipantStatus.FLED)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        won_def = StatDefinition.objects.get(key=STAT_KEY_ENCOUNTERS_WON)
        self.assertEqual(active.character_sheet.stats.get(won_def), 1)
        fled_def = StatDefinition.objects.get(key=STAT_KEY_ENCOUNTERS_FLED)
        self.assertEqual(fled.character_sheet.stats.get(fled_def), 1)
        self.assertFalse(StatDefinition.objects.filter(key=STAT_KEY_ENCOUNTERS_LOST).exists())

    def test_counters_increment_lost_on_defeat(self) -> None:
        encounter = self._make_encounter()
        active = self._add_pc(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        lost_def = StatDefinition.objects.get(key=STAT_KEY_ENCOUNTERS_LOST)
        self.assertEqual(active.character_sheet.stats.get(lost_def), 1)
        self.assertFalse(StatDefinition.objects.filter(key=STAT_KEY_ENCOUNTERS_WON).exists())

    def test_emits_encounter_completed(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)

        with patch("world.combat.services.emit_event") as mock_emit:
            complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        mock_emit.assert_called_once()
        event_name, payload = mock_emit.call_args.args
        self.assertEqual(event_name, EventName.ENCOUNTER_COMPLETED)
        self.assertEqual(payload.encounter, encounter)
        self.assertEqual(payload.outcome, EncounterOutcome.VICTORY.value)
        self.assertEqual(payload.scene, encounter.scene)
        self.assertEqual(payload.room, encounter.room)
        self.assertEqual(mock_emit.call_args.kwargs["location"], encounter.room)

    def test_no_room_skips_emit(self) -> None:
        encounter = self._make_encounter(room=None)
        self._add_pc(encounter)

        with patch("world.combat.services.emit_event") as mock_emit:
            complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        mock_emit.assert_not_called()


class ResolveRoundCompletionTests(TestCase):
    """resolve_round drives the completion seam end-to-end (#876)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.gift = GiftFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )

    def test_resolve_round_records_victory(self) -> None:
        """Defeating the last opponent stamps VICTORY + completed_at via resolve_round."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=10,
            max_health=10,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDB.objects.create(
            db_key="AftermathCompletionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=self.gift,
            effect_type=self.effect_attack,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent,
        )

        def mock_check_fn(*args, **kwargs):  # type: ignore[no-untyped-def]
            return MagicMock(success_level=2)

        result = resolve_round(encounter, offense_check_fn=mock_check_fn)

        self.assertTrue(result.encounter_completed)
        encounter.refresh_from_db()
        self.assertEqual(encounter.status, EncounterStatus.COMPLETED)
        self.assertEqual(encounter.outcome, EncounterOutcome.VICTORY)
        self.assertIsNotNone(encounter.completed_at)
