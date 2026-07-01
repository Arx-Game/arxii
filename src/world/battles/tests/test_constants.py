from django.test import TestCase

from world.battles.constants import BattleActionKind, BattleOutcome, BattleSideRole


class BattleConstantsTests(TestCase):
    def test_side_roles_present(self) -> None:
        assert set(BattleSideRole.values) == {"attacker", "defender"}

    def test_outcome_has_unresolved_default(self) -> None:
        assert BattleOutcome.UNRESOLVED == "unresolved"

    def test_action_kinds(self) -> None:
        assert set(BattleActionKind.values) == {"strike", "support", "rescue"}

    def test_battle_action_kind_has_rescue(self) -> None:
        from world.battles.constants import BattleActionKind

        assert BattleActionKind.RESCUE == "rescue"
