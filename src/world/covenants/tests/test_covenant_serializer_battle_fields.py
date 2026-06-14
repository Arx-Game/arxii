"""Tests for battle-state fields exposed on CovenantSerializer (#518, Task C1)."""

from django.test import TestCase, tag

from world.covenants.constants import BattleBinding, CovenantType
from world.covenants.factories import CovenantFactory
from world.covenants.serializers import CovenantSerializer


class CovenantSerializerBattleFieldDeclarationTests(TestCase):
    """SQLite-safe: assert battle-state fields are declared without serializing.

    Serializing a Covenant triggers legend_total → a PG materialized view that
    does not exist under SQLite (#758), so this guard only inspects the declared
    field set and never touches `.data`.
    """

    def test_battle_fields_declared(self) -> None:
        field_names = set(CovenantSerializer().fields.keys())
        self.assertIn("is_dormant", field_names)
        self.assertIn("battle_binding", field_names)
        self.assertIn("battle_binding_display", field_names)


@tag("postgres")  # serializes legend_total → societies_covenantlegendsummary (PG view) — #758
class CovenantSerializerBattleFieldValueTests(TestCase):
    """Verify the serialized values of the battle-state fields."""

    def test_standing_dormant_battle_covenant_values(self) -> None:
        cov = CovenantFactory(
            covenant_type=CovenantType.BATTLE,
            battle_binding=BattleBinding.STANDING,
            is_dormant=True,
        )
        data = CovenantSerializer(cov).data
        self.assertTrue(data["is_dormant"])
        self.assertEqual(data["battle_binding"], BattleBinding.STANDING)
        self.assertTrue(data["battle_binding_display"])
