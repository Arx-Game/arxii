from django.test import TestCase

from flows.constants import EventName


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
        }
        self.assertEqual(set(EventName.values), expected)
