"""Integration tests for the combat → use_technique pipeline.

These tests exercise the full round-resolution path with a real
use_technique envelope. They assert observable side effects (anima
deduction, event emission, mishap conditions, damage delivered)
rather than internal call patterns.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionTargetType
from evennia_extensions.factories import ObjectDBFactory
from flows.constants import EventName
from flows.events.payloads import TechniqueCastPayload, TechniquePreCastPayload
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
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
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.services.targeting import InvalidCastTarget
from world.mechanics.constants import PropertyHolder
from world.mechanics.factories import (
    AerialPropertyFactory,
    CharacterEngagementFactory,
    ObjectPropertyFactory,
    PrerequisiteFactory,
)
from world.scenes.constants import RoundStatus
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
        status=RoundStatus.RESOLVING,
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
    room = ObjectDBFactory(
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
                fatigue_category=ActionCategory.PHYSICAL,
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
                fatigue_category=ActionCategory.PHYSICAL,
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
                    fatigue_category=ActionCategory.PHYSICAL,
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
                    fatigue_category=ActionCategory.PHYSICAL,
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
                fatigue_category=ActionCategory.PHYSICAL,
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
                    fatigue_category=ActionCategory.PHYSICAL,
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
                fatigue_category=ActionCategory.PHYSICAL,
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
                fatigue_category=ActionCategory.PHYSICAL,
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
                    fatigue_category=ActionCategory.PHYSICAL,
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
                fatigue_category=ActionCategory.PHYSICAL,
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


class CombatTargetPrerequisitesTest(TestCase):
    """resolve_combat_technique enforces Technique.target_prerequisites (#1793)."""

    def test_resolve_combat_technique_raises_when_target_missing_property(self) -> None:
        participant, action, _opponent, _anima, technique, _room = _setup_pc_attacking_mook()
        prereq = PrerequisiteFactory(
            property=AerialPropertyFactory(), property_holder=PropertyHolder.TARGET
        )
        technique.target_prerequisites.add(prereq)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            with self.assertRaises(InvalidCastTarget):
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=ActionCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )

    def test_resolve_combat_technique_passes_when_target_meets_property(self) -> None:
        participant, action, opponent, _anima, technique, _room = _setup_pc_attacking_mook()
        prereq = PrerequisiteFactory(
            property=AerialPropertyFactory(), property_holder=PropertyHolder.TARGET
        )
        technique.target_prerequisites.add(prereq)
        ObjectPropertyFactory(object=opponent.objectdb, property=prereq.property)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )  # does not raise

    def test_resolve_combat_technique_self_type_raises_when_caster_missing_property(
        self,
    ) -> None:
        """target_type=SELF techniques never populate focused_opponent/ally_target — the
        real cast dispatcher's ``_target_spec_for_technique_action``
        (``actions/player_interface.py``) returns no target picker for SELF techniques,
        and ``test_affected_emitted_for_self_targeted_buff`` documents that
        ``_build_affected_targets`` returns [] for exactly this shape. This mirrors
        Task 5's non-combat SELF gap: the prerequisite must still be checked against
        the caster directly, not skipped because the target list is empty."""
        participant, action, _opponent, _anima, technique, _room = _setup_pc_attacking_mook()
        technique.target_type = ActionTargetType.SELF
        technique.save()
        action.focused_opponent_target = None
        action.save()

        prereq = PrerequisiteFactory(
            property=AerialPropertyFactory(), property_holder=PropertyHolder.TARGET
        )
        technique.target_prerequisites.add(prereq)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            with self.assertRaises(InvalidCastTarget):
                resolve_combat_technique(
                    participant=participant,
                    action=action,
                    fatigue_category=ActionCategory.PHYSICAL,
                    offense_check_type=MagicMock(),
                    offense_check_fn=None,
                )

    def test_resolve_combat_technique_self_type_passes_when_caster_meets_property(
        self,
    ) -> None:
        participant, action, _opponent, _anima, technique, _room = _setup_pc_attacking_mook()
        technique.target_type = ActionTargetType.SELF
        technique.save()
        action.focused_opponent_target = None
        action.save()

        prereq = PrerequisiteFactory(
            property=AerialPropertyFactory(), property_holder=PropertyHolder.TARGET
        )
        technique.target_prerequisites.add(prereq)
        ObjectPropertyFactory(
            object=participant.character_sheet.character, property=prereq.property
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )  # does not raise


class CombatAoETargetPrerequisitesPreFlightTest(TestCase):
    """resolve_combat_technique must not pre-flight-block a legitimate AREA cast (#1793).

    Second-pass review finding: _check_combat_target_prerequisites only ever saw
    action.focused_opponent_target — the arbitrary "first" opponent from a
    client-supplied focused_opponent_target_ids list (see
    RoundContext._resolve_focused_targets' "backward-compat" primary-opponent
    comment) — and hard-raised InvalidCastTarget if THAT one opponent failed the
    prerequisite, even though other opponents in the same AREA cast legitimately
    pass. The property is deliberately placed on the SECOND (non-primary)
    opponent to prove the pre-flight check no longer wrongly raises; the silent
    _filter_by_target_prerequisites filter (CombatTechniqueResolver) does the
    real per-opponent filtering.
    """

    def test_area_cast_does_not_raise_when_primary_opponent_lacks_property(self) -> None:
        from decimal import Decimal

        from world.magic.factories import TechniqueDamageProfileFactory

        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.0"))

        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        # opponent_a is the "primary" focused_opponent_target (the arbitrary
        # "first" resolved opponent for AoE dispatch) but does NOT carry the
        # required property.
        opponent_a = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        # opponent_b carries the property and should be the only one hit.
        opponent_b = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        room = ObjectDBFactory(db_key="TestRoom", db_typeclass_path="typeclasses.rooms.Room")
        sheet.character.location = room
        sheet.character.save()

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="AoEPrereqAttack", base_power=20),
            target_type=ActionTargetType.AREA,
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)
        prereq = PrerequisiteFactory(
            property=AerialPropertyFactory(), property_holder=PropertyHolder.TARGET
        )
        technique.target_prerequisites.add(prereq)
        ObjectPropertyFactory(object=opponent_b.objectdb, property=prereq.property)

        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent_a,  # arbitrary "first"/primary
            effort_level=EffortLevel.MEDIUM,
        )

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )  # must NOT raise InvalidCastTarget

        hit_opponent_ids = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_b.pk, hit_opponent_ids)
        self.assertNotIn(opponent_a.pk, hit_opponent_ids)


class TargetKeyedSituationalPerkCombatTest(TestCase):
    """resolve_combat_technique threads the cast's primary target's CharacterSheet
    end-to-end so a target-keyed situational perk fires for POWER_BONUS (#2536,
    Task 4 review fix — previously hard-inert, target=None always passed to
    applicable_perks regardless of the real combat target).
    """

    def test_target_favorably_disposed_perk_fires_against_persona_backed_opponent(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.factories import ThreadFactory
        from world.npc_services.factories import NPCStandingFactory

        participant, action, _opponent, _anima, _technique, _room = _setup_pc_attacking_mook(
            technique_intensity=5,
            technique_control=10,
            technique_anima_cost=2,
        )
        subject_sheet = participant.character_sheet

        # Re-target the action at a "story NPC" opponent (persona-backed) so
        # _resolve_primary_target_sheet has a real CharacterSheet to resolve.
        # Use the target sheet's own PRIMARY persona — persona_for_character
        # (which TARGET_FAVORABLY_DISPOSED's evaluator calls) always reads
        # sheet.primary_persona, not an arbitrary ESTABLISHED face.
        target_sheet = CharacterSheetFactory()
        target_persona = target_sheet.primary_persona
        target_opponent = CombatOpponentFactory(
            encounter=participant.encounter, persona=target_persona
        )
        action.focused_opponent_target = target_opponent
        action.save()

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=subject_sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_FAVORABLY_DISPOSED)
        NPCStandingFactory(
            persona=subject_sheet.primary_persona,
            npc_persona=target_persona,
            affection=1,
        )
        ThreadFactory(owner=subject_sheet, level=5)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        vow_entries = [
            entry
            for entry in result.power_ledger.entries
            if entry.source_label == "vow situational power"
        ]
        self.assertEqual(len(vow_entries), 1)
        # 5 * 20 / 10 = 10
        self.assertEqual(vow_entries[0].amount, 10)

    def test_target_favorably_disposed_perk_absent_against_bare_npc_opponent(self) -> None:
        """Same perk/thread/disposition setup, but the opponent is a bare
        (non-persona) NPC — _resolve_primary_target_sheet correctly returns
        None for it, so the target-keyed situation never holds and the ledger
        carries no 'vow situational power' contribution at all."""
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            VowSituationalPerkFactory,
            VowSituationalPerkSituationFactory,
        )
        from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
        from world.magic.factories import ThreadFactory
        from world.npc_services.factories import NPCStandingFactory
        from world.scenes.factories import PersonaFactory

        participant, action, opponent, _anima, _technique, _room = _setup_pc_attacking_mook(
            technique_intensity=5,
            technique_control=10,
            technique_anima_cost=2,
        )
        subject_sheet = participant.character_sheet
        self.assertIsNone(opponent.persona_id)  # bare NPC, no linked CharacterSheet

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=subject_sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_FAVORABLY_DISPOSED)
        # Even with a disposed target persona floating around unrelated to the
        # actual opponent, the bare NPC opponent can never resolve to it.
        NPCStandingFactory(
            persona=subject_sheet.primary_persona,
            npc_persona=PersonaFactory(),
            affection=1,
        )
        ThreadFactory(owner=subject_sheet, level=5)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=MagicMock(),
                offense_check_fn=None,
            )

        vow_entries = [
            entry
            for entry in result.power_ledger.entries
            if entry.source_label == "vow situational power"
        ]
        self.assertEqual(vow_entries, [])
