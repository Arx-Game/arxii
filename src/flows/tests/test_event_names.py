from django.core.exceptions import ValidationError
from django.test import TestCase

from flows.constants import EventName
from flows.filters.validator import validate_filter_schema


class EventNameTests(TestCase):
    def test_combat_event_names_defined(self) -> None:
        self.assertEqual(EventName.ATTACK_PRE_RESOLVE, "attack_pre_resolve")
        self.assertEqual(EventName.DAMAGE_APPLIED, "damage_applied")
        self.assertEqual(EventName.CHARACTER_KILLED, "character_killed")

    def test_all_mvp_events_enumerated(self) -> None:
        expected = {
            "attack_pre_resolve",
            "attack_landed",
            "attack_missed",
            "damage_pre_apply",
            "damage_applied",
            "character_incapacitated",
            "character_killed",
            "move_pre_depart",
            "moved",
            "examine_pre",
            "examined",
            "condition_pre_apply",
            "condition_applied",
            "condition_stage_changed",
            "condition_removed",
            "technique_pre_cast",
            "technique_cast",
            "technique_affected",
            "corruption_accruing",
            "corruption_accrued",
            "corruption_warning",
            "corruption_reduced",
            "protagonism_locked",
            "protagonism_restored",
            "condition_stage_advance_check_about_to_fire",
            "soul_tether_formed",
            "soul_tether_dissolved",
            "encounter_completed",
            "fell",
            "combat_round_starting",
            "engagement_lock_formed",
            "engagement_lock_broken",
            "food_pre_collect",
            "food_collected",
            "food_shortage",
            "food_pre_transfer",
            "food_transferred",
            "asset_compromised",
            "asset_lost",
            "asset_dismissed",
            "action_intent",
            "action_result",
        }
        self.assertEqual(set(EventName.values), expected)


class ActionEventFilterValidationTests(TestCase):
    def test_action_intent_filter_on_action_key_validates(self) -> None:
        validate_filter_schema(
            {"path": "action_key", "op": "==", "value": "get"},
            event_name="action_intent",
        )

    def test_action_result_filter_on_success_validates(self) -> None:
        validate_filter_schema(
            {"path": "success", "op": "==", "value": True},
            event_name="action_result",
        )

    def test_action_intent_filter_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            validate_filter_schema(
                {"path": "verb", "op": "==", "value": "get"},
                event_name="action_intent",
            )
