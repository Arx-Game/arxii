"""Tests for the offscreen-act gate (#3412).

Covers the pure ``offscreen_act_state()`` predicate directly (the lifecycle
matrix, the unconscious overlay, and precedence) plus its wiring into
``Action.check_availability()`` (the dead-gate absorption and a couple of
representative offscreen/non-offscreen integration checks).
"""

from django.test import TestCase
from django.utils import timezone

from actions.constants import (
    DEAD_ALLOWED_ACTION_KEYS,
    OFFSCREEN_ACT_KEYS,
    OFFSCREEN_CHANNEL_DREAM,
    OFFSCREEN_CHANNEL_SMUGGLE,
    OFFSCREEN_REASON_CAPTURED,
    OFFSCREEN_REASON_DEAD,
    OFFSCREEN_REASON_RETIRED,
    OFFSCREEN_REASON_UNCONSCIOUS,
    OFFSCREEN_REASON_UNKNOWN,
    OffscreenActState,
)
from actions.definitions.communication import EmitAction, PoseAction
from actions.definitions.perception import InventoryAction, LookAction, LookAtItemAction
from actions.definitions.personas import SetActivePersonaAction
from actions.definitions.vitals import GiveDeathKudosAction, RetireCharacterAction, WakeAction
from actions.offscreen_gate import OffscreenGateResult, offscreen_act_state
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.conditions.factories import ConditionInstanceFactory, UnconsciousConditionFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory

# A representative act per offscreen kind (journal / goal / persona), plus
# the reserved-but-inert proclamation key.
_REPRESENTATIVE_OFFSCREEN_KEYS = (
    "create_journal_entry",
    "set_character_goals",
    "set_active_persona",
    "issue_proclamation",
)

# Non-offscreen controls: one dead-whitelisted (look), one not (pose).
_NON_OFFSCREEN_KEYS = ("look", "pose")

# lifecycle_state -> (expected state, expected channel, expected reason)
_EXPECTED_BY_LIFECYCLE = {
    LifecycleState.ALIVE: (OffscreenActState.ALLOWED, None, None),
    LifecycleState.CAPTURED: (
        OffscreenActState.ROUTED,
        OFFSCREEN_CHANNEL_SMUGGLE,
        OFFSCREEN_REASON_CAPTURED,
    ),
    LifecycleState.UNKNOWN: (OffscreenActState.BLOCKED, None, OFFSCREEN_REASON_UNKNOWN),
    LifecycleState.COMA: (OffscreenActState.ALLOWED, None, None),
    LifecycleState.RETIRED: (OffscreenActState.BLOCKED, None, OFFSCREEN_REASON_RETIRED),
    LifecycleState.DEAD: (OffscreenActState.BLOCKED, None, OFFSCREEN_REASON_DEAD),
}


class OffscreenActStateMatrixTests(TestCase):
    """The full (6 lifecycle states) x (offscreen act kind) matrix."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_offscreen_act_keys_table_contents(self) -> None:
        # #3412 T3 note: issue_proclamation is reserved now, wired later.
        self.assertEqual(
            OFFSCREEN_ACT_KEYS,
            frozenset(
                {
                    "create_journal_entry",
                    "edit_journal_entry",
                    "respond_to_journal",
                    "set_journal_disposition",
                    "set_character_goals",
                    "log_goal_progress",
                    "set_active_persona",
                    "issue_proclamation",
                }
            ),
        )

    def test_lifecycle_matrix_for_every_offscreen_key(self) -> None:
        for lifecycle_state, (
            expected_state,
            expected_channel,
            expected_reason,
        ) in _EXPECTED_BY_LIFECYCLE.items():
            self.sheet.lifecycle_state = lifecycle_state
            self.sheet.save(update_fields=["lifecycle_state"])
            for action_key in _REPRESENTATIVE_OFFSCREEN_KEYS:
                with self.subTest(lifecycle_state=lifecycle_state, action_key=action_key):
                    result = offscreen_act_state(self.sheet, action_key)
                    self.assertEqual(result.state, expected_state)
                    self.assertEqual(result.channel, expected_channel)
                    self.assertEqual(result.reason, expected_reason)

    def test_non_offscreen_keys_always_allowed(self) -> None:
        for lifecycle_state in LifecycleState.values:
            self.sheet.lifecycle_state = lifecycle_state
            self.sheet.save(update_fields=["lifecycle_state"])
            for action_key in _NON_OFFSCREEN_KEYS:
                with self.subTest(lifecycle_state=lifecycle_state, action_key=action_key):
                    result = offscreen_act_state(self.sheet, action_key)
                    self.assertEqual(result, OffscreenGateResult(state=OffscreenActState.ALLOWED))

    def test_unknown_action_key_always_allowed(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        result = offscreen_act_state(self.sheet, "not_a_real_action_key")
        self.assertEqual(result, OffscreenGateResult(state=OffscreenActState.ALLOWED))

    def test_none_sheet_always_allowed(self) -> None:
        result = offscreen_act_state(None, "create_journal_entry")
        self.assertEqual(result, OffscreenGateResult(state=OffscreenActState.ALLOWED))

    def test_blocked_and_routed_reasons_are_non_empty(self) -> None:
        for lifecycle_state, (expected_state, _channel, _reason) in _EXPECTED_BY_LIFECYCLE.items():
            if expected_state == OffscreenActState.ALLOWED:
                continue
            self.sheet.lifecycle_state = lifecycle_state
            self.sheet.save(update_fields=["lifecycle_state"])
            with self.subTest(lifecycle_state=lifecycle_state):
                result = offscreen_act_state(self.sheet, "set_character_goals")
                self.assertTrue(result.reason)


class UnconsciousOverlayTests(TestCase):
    """Unconscious is an overlay independent of lifecycle_state (#3412)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.unconscious_template = UnconsciousConditionFactory()

    def _knock_out(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.unconscious_template)

    def test_unconscious_overlay_on_alive_routes_to_dream(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.ALIVE
        self.sheet.save(update_fields=["lifecycle_state"])
        self._knock_out()
        result = offscreen_act_state(self.sheet, "create_journal_entry")
        self.assertEqual(result.state, OffscreenActState.ROUTED)
        self.assertEqual(result.channel, OFFSCREEN_CHANNEL_DREAM)
        self.assertEqual(result.reason, OFFSCREEN_REASON_UNCONSCIOUS)

    def test_unconscious_overlay_on_captured_routes_to_dream_not_smuggle(self) -> None:
        # Precedence: unconscious beats CAPTURED.
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        self._knock_out()
        result = offscreen_act_state(self.sheet, "set_character_goals")
        self.assertEqual(result.state, OffscreenActState.ROUTED)
        self.assertEqual(result.channel, OFFSCREEN_CHANNEL_DREAM)

    def test_conscious_alive_is_allowed(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.ALIVE
        self.sheet.save(update_fields=["lifecycle_state"])
        result = offscreen_act_state(self.sheet, "create_journal_entry")
        self.assertEqual(result.state, OffscreenActState.ALLOWED)


class DeadPrecedenceTests(TestCase):
    """DEAD wins over everything, including a lingering Unconscious instance."""

    def test_dead_beats_unconscious(self) -> None:
        # Mirrors world.vitals.services.perceives_dreamside: a ghost watches,
        # it does not dream.
        sheet = CharacterSheetFactory(lifecycle_state=LifecycleState.DEAD)
        unconscious_template = UnconsciousConditionFactory()
        ConditionInstanceFactory(target=sheet.character, condition=unconscious_template)
        result = offscreen_act_state(sheet, "set_active_persona")
        self.assertEqual(result.state, OffscreenActState.BLOCKED)
        self.assertIsNone(result.channel)
        self.assertEqual(result.reason, OFFSCREEN_REASON_DEAD)


class DeadGateRegressionTests(TestCase):
    """The global dead-gate whitelist stays byte-identical (#2287 absorption)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        cls.character = cls.sheet.character

    def test_every_dead_allowed_key_matches_the_constant(self) -> None:
        # Guards against this test file drifting from the real whitelist.
        self.assertEqual(
            DEAD_ALLOWED_ACTION_KEYS,
            frozenset(
                {
                    "look",
                    "look_at_item",
                    "inventory",
                    "emit",
                    "pose",
                    "wake",
                    "retire",
                    "death_kudos",
                }
            ),
        )

    def test_every_dead_allowed_action_is_not_dead_gated(self) -> None:
        actions_by_key = {
            "look": LookAction(),
            "look_at_item": LookAtItemAction(),
            "inventory": InventoryAction(),
            "emit": EmitAction(),
            "pose": PoseAction(),
            "wake": WakeAction(),
            "retire": RetireCharacterAction(),
            "death_kudos": GiveDeathKudosAction(),
        }
        self.assertEqual(set(actions_by_key), DEAD_ALLOWED_ACTION_KEYS)
        for key, action_obj in actions_by_key.items():
            with self.subTest(key=key):
                availability = action_obj.check_availability(self.character)
                self.assertNotIn("The dead cannot do that.", availability.reasons)

    def test_dead_offscreen_key_gets_byte_identical_single_reason(self) -> None:
        # The critical no-double-append assertion: a dead actor attempting an
        # offscreen key gets exactly the same single reason as any other
        # non-whitelisted key — the offscreen gate must not also fire.
        availability = SetActivePersonaAction().check_availability(self.character)
        self.assertFalse(availability.available)
        self.assertEqual(availability.reasons, ["The dead cannot do that."])


class OffscreenGateCheckAvailabilityIntegrationTests(TestCase):
    """Wiring sanity: offscreen keys route/block via check_availability; others don't."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet)
        self.character = self.sheet.character

    def test_captured_offscreen_key_is_blocked_with_smuggle_reason(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        availability = SetActivePersonaAction().check_availability(self.character)
        self.assertFalse(availability.available)
        self.assertEqual(availability.reasons, [OFFSCREEN_REASON_CAPTURED])

    def test_captured_non_offscreen_key_is_untouched(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        availability = LookAction().check_availability(self.character)
        self.assertTrue(availability.available)

    def test_alive_conscious_offscreen_key_is_allowed(self) -> None:
        availability = SetActivePersonaAction().check_availability(self.character)
        self.assertTrue(availability.available)
