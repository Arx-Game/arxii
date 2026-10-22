"""The six ConditionTemplate fields behind provoke, guard, knockout and strike-back (#4584)."""

from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory, DamageTypeFactory
from world.conditions.models import ConditionTemplate


class ReactionFieldDefaultsTests(TestCase):
    def test_a_new_template_has_every_reaction_effect_off(self) -> None:
        t = ConditionTemplateFactory(name="Plain Mark 4584")
        self.assertFalse(t.forces_attack_on_source)
        self.assertFalse(t.source_guards_bearer)
        self.assertFalse(t.prevents_knockout)
        self.assertEqual(t.retaliation_damage, 0)
        self.assertIsNone(t.retaliation_damage_type)
        self.assertIsNone(t.retaliation_condition)

    def test_deleting_the_damage_type_or_condition_keeps_the_ward(self) -> None:
        dt = DamageTypeFactory(name="Thorn 4584")
        provoked = ConditionTemplateFactory(name="Called Out 4584")
        ward = ConditionTemplateFactory(
            name="Briar Ward 4584",
            retaliation_damage=5,
            retaliation_damage_type=dt,
            retaliation_condition=provoked,
        )
        dt.delete()
        provoked.delete()
        # SET_NULL writes in SQL; read the row itself, not the idmapper-cached instance.
        row = (
            ConditionTemplate.objects.filter(pk=ward.pk)
            .values("retaliation_damage_type_id", "retaliation_condition_id", "retaliation_damage")
            .get()
        )
        self.assertIsNone(row["retaliation_damage_type_id"])
        self.assertIsNone(row["retaliation_condition_id"])
        self.assertEqual(row["retaliation_damage"], 5)
