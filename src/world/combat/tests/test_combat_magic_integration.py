"""Integration tests for the combat → use_technique pipeline.

These tests exercise the full round-resolution path with a real
use_technique envelope. They assert observable side effects (anima
deduction, event emission, mishap conditions, damage delivered)
rather than internal call patterns.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from flows.constants import EventName
from flows.events.payloads import TechniqueCastPayload, TechniquePreCastPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    EncounterStatus,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import resolve_combat_technique
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.constants import EffortLevel, FatigueCategory
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.vitals.models import CharacterVitals


def _setup_pc_attacking_mook(
    *,
    technique_intensity: int = 5,
    technique_control: int = 10,
    technique_anima_cost: int = 3,
    base_power: int = 20,
    opponent_health: int = 50,
):
    """Build the standard test scenario: 1 PC, 1 mook, technique ready."""
    encounter = CombatEncounterFactory(
        status=EncounterStatus.RESOLVING,
        round_number=1,
    )
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=30)
    opponent = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=opponent_health,
        max_health=opponent_health,
        threat_pool=pool,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    CharacterVitals.objects.create(
        character_sheet=sheet,
        health=100,
        max_health=100,
    )
    anima = CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
    CharacterEngagementFactory(character=sheet.character)
    room = ObjectDB.objects.create(
        db_key="TestRoom",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    sheet.character.location = room
    sheet.character.save()

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
        intensity=technique_intensity,
        control=technique_control,
        anima_cost=technique_anima_cost,
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    return participant, action, opponent, anima, technique, room


class AnimaDeductionTest(TestCase):
    """Combat-cast technique deducts anima cost from CharacterAnima.current."""

    def test_combat_cast_deducts_anima(self) -> None:
        participant, action, _opponent, anima, _technique, _ = _setup_pc_attacking_mook(
            technique_anima_cost=3,
            technique_intensity=5,
            technique_control=10,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        anima.refresh_from_db()
        # control_delta = 10 - 5 = 5; effective_cost = max(3 - 5, 0) = 0.
        self.assertEqual(anima.current, 20)

    def test_combat_cast_with_high_intensity_deducts_anima(self) -> None:
        participant, action, _opponent, anima, _technique, _ = _setup_pc_attacking_mook(
            technique_anima_cost=5,
            technique_intensity=10,
            technique_control=2,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        anima.refresh_from_db()
        # control_delta = 2 - 10 = -8; effective_cost = max(5 - (-8), 0) = 13.
        self.assertEqual(anima.current, 7)


class EventEmissionTest(TestCase):
    """PRE_CAST and CAST events fire during combat round resolution."""

    def test_pre_cast_emitted_in_combat(self) -> None:
        participant, action, _opponent, _, _, _ = _setup_pc_attacking_mook()
        captured: list = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_PRE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], TechniquePreCastPayload)
        self.assertIs(captured[0].caster, participant.character_sheet.character)

    def test_cast_emitted_in_combat(self) -> None:
        participant, action, _opponent, _, _, _ = _setup_pc_attacking_mook()
        captured: list = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        self.assertIsInstance(captured[0], TechniqueCastPayload)


class ReactiveScarCancelTest(TestCase):
    """A reactive condition on TECHNIQUE_PRE_CAST cancels the combat cast.
    No damage applied, no anima deducted, no TECHNIQUE_CAST emitted."""

    SELF_FILTER = {"path": "caster", "op": "==", "value": "self"}

    def _make_cancel_flow(self):
        from flows.consts import FlowActionChoices
        from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory

        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
        return flow

    def test_cancel_returns_zero_damage_and_no_anima_deducted(self) -> None:
        from world.conditions.factories import ReactiveConditionFactory

        participant, action, opponent, anima, _, _ = _setup_pc_attacking_mook(
            technique_anima_cost=5,
            technique_intensity=10,
            technique_control=2,
        )
        cancel_flow = self._make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=self.SELF_FILTER,
            flow_definition=cancel_flow,
            target=participant.character_sheet.character,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        opponent.refresh_from_db()
        self.assertEqual(opponent.health, opponent.max_health)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 20)
        self.assertEqual(result.damage_results, [])
        mock_perform.assert_not_called()

    def test_cancel_suppresses_technique_cast_event(self) -> None:
        from world.conditions.factories import ReactiveConditionFactory

        participant, action, _opponent, _, _, _ = _setup_pc_attacking_mook()
        cancel_flow = self._make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=self.SELF_FILTER,
            flow_definition=cancel_flow,
            target=participant.character_sheet.character,
        )
        cast_fired: list = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_CAST:
                cast_fired.append(True)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(cast_fired, [])


class MishapTest(TestCase):
    """When intensity > control, mishap rider fires after the cast."""

    def test_mishap_path_invoked_on_control_deficit(self) -> None:
        participant, action, _opponent, _, _, _ = _setup_pc_attacking_mook(
            technique_intensity=15,
            technique_control=2,
        )

        captured: list = []
        import world.magic.services.techniques as svc_mod

        original_mishap = svc_mod._resolve_mishap

        def capturing_mishap(character, pool, check_result):
            captured.append((character, pool, check_result))
            return original_mishap(character, pool, check_result)

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch.object(svc_mod, "select_mishap_pool", return_value=MagicMock()) as mock_select,
            patch.object(svc_mod, "_resolve_mishap", side_effect=capturing_mishap),
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

            mock_select.assert_called_once()
            self.assertEqual(len(captured), 1)


class FlatBonusPullCheckTest(TestCase):
    """Active FLAT_BONUS CombatPull rows feed extra_modifiers into perform_check."""

    def test_active_flat_bonus_pulls_added_to_extra_modifiers(self) -> None:
        from world.combat.factories import (
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
        )
        from world.magic.constants import EffectKind

        participant, action, _opponent, _, _, _ = _setup_pc_attacking_mook()
        pull = CombatPullFactory(
            participant=participant,
            round_number=participant.encounter.round_number,
        )
        CombatPullResolvedEffectFactory(pull=pull, kind=EffectKind.FLAT_BONUS, scaled_value=3)
        CombatPullResolvedEffectFactory(pull=pull, kind=EffectKind.FLAT_BONUS, scaled_value=1)

        participant.character_sheet.character.combat_pulls.invalidate()

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        kwargs = mock_perform.call_args.kwargs
        # 3 + 1 from pulls; effort EffortLevel.MEDIUM is 0.
        self.assertGreaterEqual(kwargs["extra_modifiers"], 4)


class FullHappyPathTest(TestCase):
    """End-to-end: damage applied, anima deducted, events emitted, no errors."""

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def test_full_happy_path(self) -> None:
        participant, action, opponent, _anima, _, _ = _setup_pc_attacking_mook(
            technique_anima_cost=2,
            technique_intensity=5,
            technique_control=10,
            base_power=20,
            opponent_health=50,
        )

        captured_events: list = []
        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            captured_events.append(name)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            with patch("world.combat.services.perform_check") as mock_perform:
                mock_perform.return_value = MagicMock(success_level=2)
                result = resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=FatigueCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(result.damage_results), 1)
        self.assertGreater(result.damage_results[0].damage_dealt, 0)

        opponent.refresh_from_db()
        self.assertLess(opponent.health, 50)

        self.assertIn(EventName.TECHNIQUE_PRE_CAST, captured_events)
        self.assertIn(EventName.TECHNIQUE_CAST, captured_events)

        self.assertTrue(result.technique_use_result.confirmed)


class IdentityIntensityModifierRaisesCombatDamageTest(TestCase):
    """Identity intensity CharacterModifier raises combat damage via injected power.

    get_runtime_technique_stats sums CharacterModifier rows on the intensity
    ModifierTarget into stats.intensity.  use_technique derives power from that
    value and injects it into the resolver.  CombatTechniqueResolver.__call__
    uses injected power (not technique.intensity) as its effective intensity seed,
    so a caster with a +N identity intensity modifier must deal strictly more
    opponent damage than an identical caster without that modifier.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from decimal import Decimal

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def _resolve_with_identity_modifier(self, *, identity_intensity_bonus: int) -> int:
        """Run one resolve_combat_technique with or without an identity intensity modifier.

        Returns the total damage dealt to the opponent.
        """
        from decimal import Decimal

        from world.distinctions.factories import (
            DistinctionEffectFactory,
            DistinctionFactory,
        )
        from world.magic.factories import TechniqueDamageProfileFactory
        from world.mechanics.constants import TECHNIQUE_STAT_CATEGORY_NAME, TECHNIQUE_STAT_INTENSITY
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
        from world.mechanics.models import CharacterModifier, ModifierSource

        # Base setup: intensity=5 so damage profile scaling is non-zero.
        participant, action, _opponent, _anima, technique, _room = _setup_pc_attacking_mook(
            technique_intensity=5,
            technique_control=10,
            technique_anima_cost=2,
            base_power=0,  # No EffectType base_power — damage comes entirely from profile.
            opponent_health=999,
        )
        # Replace the auto-seeded profile with one that has damage_intensity_multiplier=2.
        # budget = base_damage(0) + eff_intensity × 2.0
        # With identity_bonus=0: eff_intensity=5 → budget=10 → damage=10 (at SL=2, mult=1.0).
        # With identity_bonus=10: eff_intensity=15 → budget=30 → damage=30.
        technique.damage_profiles.all().delete()
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=0,
            damage_intensity_multiplier=Decimal("2.0"),
            minimum_success_level=1,
        )

        if identity_intensity_bonus > 0:
            # Create a ModifierTarget for technique_stat intensity.
            category = ModifierCategoryFactory(name=TECHNIQUE_STAT_CATEGORY_NAME)
            target = ModifierTargetFactory(name=TECHNIQUE_STAT_INTENSITY, category=category)

            # Create a DistinctionEffect pointing at that target (required by
            # get_modifier_breakdown's source.distinction_effect access).
            distinction = DistinctionFactory()
            effect = DistinctionEffectFactory(
                distinction=distinction,
                target=target,
                value_per_rank=identity_intensity_bonus,
            )
            source = ModifierSource.objects.create(distinction_effect=effect)
            CharacterModifier.objects.create(
                character=participant.character_sheet,
                target=target,
                value=identity_intensity_bonus,
                source=source,
            )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=FatigueCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        return sum(r.damage_dealt for r in result.damage_results)

    def test_identity_intensity_modifier_raises_damage(self) -> None:
        """A caster WITH a +10 identity intensity modifier deals strictly more damage."""
        damage_base = self._resolve_with_identity_modifier(identity_intensity_bonus=0)
        damage_boosted = self._resolve_with_identity_modifier(identity_intensity_bonus=10)
        self.assertGreater(
            damage_boosted,
            damage_base,
            f"Expected boosted damage ({damage_boosted}) > base damage ({damage_base}).",
        )
