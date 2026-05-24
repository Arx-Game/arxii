"""Tests for clash-state combo prerequisites in detect_available_combos."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    ClashFlavor,
    ClashStatus,
    EncounterStatus,
)
from world.combat.factories import (
    BreakClashFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ComboSlotFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import detect_available_combos
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory


class ClashComboPrereqTests(TestCase):
    """Tests for clash-state prerequisites in detect_available_combos.

    Covers both ``required_clash_flavor`` and ``required_clash_window_condition``
    gates on ``ComboDefinition``, and verifies the two-prefetch query bound.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.effect_defense = EffectTypeFactory(name="Defense", base_power=10)
        cls.gift = GiftFactory()

    def _setup_encounter_with_actions(self) -> tuple:
        """Create an encounter with two PCs who have declared actions.

        Returns (encounter, participants, actions).
        """
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        participants = []
        actions = []
        for i in range(2):
            sheet = CharacterSheetFactory()
            p = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
            participants.append(p)
            effect = self.effect_attack if i % 2 == 0 else self.effect_defense
            technique = TechniqueFactory(gift=self.gift, effect_type=effect)
            action = CombatRoundAction.objects.create(
                participant=p,
                round_number=1,
                focused_category=ActionCategory.PHYSICAL,
                focused_action=technique,
            )
            actions.append(action)
        return encounter, participants, actions

    def _make_two_slot_combo(
        self,
        *,
        discoverable_via_combat: bool = True,
        **kwargs: object,
    ) -> object:
        """Create a ComboDefinition with Attack + Defense slots."""
        combo = ComboDefinitionFactory(
            discoverable_via_combat=discoverable_via_combat,
            **kwargs,
        )
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=self.effect_attack)
        ComboSlotFactory(combo=combo, slot_number=2, required_action_type=self.effect_defense)
        return combo

    # ------------------------------------------------------------------
    # No-prereq baseline
    # ------------------------------------------------------------------

    def test_combo_without_clash_prereq_always_eligible(self) -> None:
        """A combo with both clash fields null is unaffected by clash state."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        self._make_two_slot_combo()

        # No clashes, no conditions — combo should still be returned.
        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)

    # ------------------------------------------------------------------
    # required_clash_flavor gate
    # ------------------------------------------------------------------

    def test_combo_with_required_flavor_excluded_when_no_active_clash(self) -> None:
        """Combo requiring BREAK flavor is excluded when no clashes are active."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        self._make_two_slot_combo(required_clash_flavor=ClashFlavor.BREAK)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_combo_with_required_flavor_included_when_matching_clash_active(self) -> None:
        """Combo requiring BREAK flavor is included when a BREAK clash is active."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        self._make_two_slot_combo(required_clash_flavor=ClashFlavor.BREAK)

        BreakClashFactory(encounter=encounter, status=ClashStatus.ACTIVE)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)

    def test_combo_with_required_flavor_excluded_when_only_wrong_flavor_active(self) -> None:
        """Combo requiring BREAK is excluded when only a CLASH-flavor clash is active."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        self._make_two_slot_combo(required_clash_flavor=ClashFlavor.BREAK)

        # Create an active CLASH-flavor Clash (default flavor)
        ClashFactory(encounter=encounter, status=ClashStatus.ACTIVE)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    # ------------------------------------------------------------------
    # required_clash_window_condition gate
    # ------------------------------------------------------------------

    def test_combo_with_required_window_condition_excluded_when_no_matching_instance(
        self,
    ) -> None:
        """Combo requiring a window condition is excluded when no opponent has it."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        condition_template = ConditionTemplateFactory()
        self._make_two_slot_combo(required_clash_window_condition=condition_template)

        # Opponent exists but carries no ConditionInstance.
        CombatOpponentFactory(encounter=encounter)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_combo_with_required_window_condition_included_when_instance_present(
        self,
    ) -> None:
        """Combo requiring a window condition is included when an opponent carries it."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        condition_template = ConditionTemplateFactory()
        self._make_two_slot_combo(required_clash_window_condition=condition_template)

        opponent = CombatOpponentFactory(encounter=encounter)
        # Apply the required condition to the opponent's ObjectDB.
        ConditionInstance.objects.create(
            target_id=opponent.objectdb_id,
            condition=condition_template,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)

    # ------------------------------------------------------------------
    # Both prerequisites must match
    # ------------------------------------------------------------------

    def test_combo_with_both_requirements_both_must_match(self) -> None:
        """When both fields are set, both must be satisfied for the combo to appear."""
        encounter, _participants, _actions = self._setup_encounter_with_actions()
        condition_template = ConditionTemplateFactory()
        self._make_two_slot_combo(
            required_clash_flavor=ClashFlavor.BREAK,
            required_clash_window_condition=condition_template,
        )

        # Provide only the BREAK clash (no window condition instance).
        BreakClashFactory(encounter=encounter, status=ClashStatus.ACTIVE)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0, "Must be excluded when window condition is missing")

        # Now also add the window condition instance.
        opponent = CombatOpponentFactory(encounter=encounter)
        ConditionInstance.objects.create(
            target_id=opponent.objectdb_id,
            condition=condition_template,
        )

        available2 = detect_available_combos(encounter, 1)
        self.assertEqual(len(available2), 1, "Must be included when both requirements are met")

    # ------------------------------------------------------------------
    # Query-count bound
    # ------------------------------------------------------------------

    def test_query_count_bounded(self) -> None:
        """detect_available_combos executes a bounded number of queries regardless of N combos.

        With 5 clash-prereq-gated combos the query count must remain a small
        constant (not O(N)), because clash and condition data are prefetched once.
        """
        encounter, _participants, _actions = self._setup_encounter_with_actions()

        condition_template = ConditionTemplateFactory()
        for _ in range(5):
            self._make_two_slot_combo(
                required_clash_flavor=ClashFlavor.BREAK,
                required_clash_window_condition=condition_template,
            )

        # Measure query count; 5 combos should NOT produce 10+ queries.
        # The function performs: actions, gift_resonance, combos+prefetch,
        # known_combos, opponents, active_clashes, window_conditions = ~7 queries.
        # We allow up to 15 as a generous ceiling to guard against O(N) regression.
        with CaptureQueriesContext(connection) as ctx:
            detect_available_combos(encounter, 1)

        self.assertLess(
            len(ctx.captured_queries),
            16,
            f"Expected fewer than 16 queries for 5 combos, got {len(ctx.captured_queries)}",
        )
