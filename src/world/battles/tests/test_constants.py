from django.test import TestCase

from world.battles.constants import BattleActionKind, BattleOutcome, BattleSideRole


class BattleConstantsTests(TestCase):
    def test_side_roles_present(self) -> None:
        assert set(BattleSideRole.values) == {"attacker", "defender"}

    def test_outcome_has_unresolved_default(self) -> None:
        assert BattleOutcome.UNRESOLVED == "unresolved"

    def test_action_kinds(self) -> None:
        assert set(BattleActionKind.values) == {
            "strike",
            "support",
            "rescue",
            "rout",
            "rally",
            "repel",
            "hold",
            "breach",
            "fortify",
            "set_environment",
            "reposition",
            "move",
        }

    def test_battle_action_kind_has_rescue(self) -> None:
        from world.battles.constants import BattleActionKind

        assert BattleActionKind.RESCUE == "rescue"

    def test_battle_action_kind_has_flow_actions(self) -> None:
        from world.battles.constants import BattleActionKind

        assert BattleActionKind.ROUT == "rout"
        assert BattleActionKind.RALLY == "rally"
        assert BattleActionKind.REPEL == "repel"
        assert BattleActionKind.HOLD == "hold"

    def test_morale_and_vp_tuning_constants_exist(self) -> None:
        from world.battles import constants

        assert constants.DEFAULT_MORALE == 70
        assert constants.MAX_MORALE == 100
        assert constants.ROUTED_MORALE_THRESHOLD == 25
        assert constants.ROUT_MORALE_PER_LEVEL == 15
        assert constants.RALLY_MORALE_PER_LEVEL == 15
        assert constants.ROUT_VP_PER_LEVEL == 4
        assert constants.RALLY_VP == 3
        assert constants.REPEL_VP == 4
        assert constants.HOLD_CAPTURE_VP == 8
        assert constants.HOLD_SUSTAIN_VP == 3
        assert constants.REPEL_DEFENSE_BONUS == 15


class BattleActionKindSiegeTests(TestCase):
    def test_breach_and_fortify_are_valid_choices(self) -> None:
        self.assertIn(BattleActionKind.BREACH, BattleActionKind.values)
        self.assertIn(BattleActionKind.FORTIFY, BattleActionKind.values)


class LargeScaleBattleParticipantThresholdTests(TestCase):
    def test_large_scale_battle_participant_threshold_is_ten(self) -> None:
        from world.battles.constants import LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD

        assert LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD == 10
