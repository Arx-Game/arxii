"""Combat seed composition tests (#1706).

Covers the penetration + flee retrofits (stat + skill legs) and the resist
checks' single-stat compositions. The Melee Combat skill catalog is seeded
by ``world.seeds.combat_checks``; these tests exercise the combat factories'
compositions against it.
"""

from django.test import TestCase

from world.seeds.combat_checks import ensure_melee_combat_skill


class PenetrationFleeSkillLegTests(TestCase):
    """#1706 — penetration + flee gain a Melee Combat skill leg."""

    def test_penetration_has_skill_leg(self):
        from world.combat.factories import wire_penetration_check_type

        ensure_melee_combat_skill()  # dependency
        ct = wire_penetration_check_type()
        trait_names = {t.trait.name for t in ct.traits.all()}  # type: ignore[attr-defined]
        self.assertEqual(trait_names, {"willpower", "intellect", "Melee Combat"})

    def test_flee_has_skill_leg(self):
        from world.combat.factories import wire_flee_check_type

        ensure_melee_combat_skill()
        ct = wire_flee_check_type()
        trait_names = {t.trait.name for t in ct.traits.all()}  # type: ignore[attr-defined]
        self.assertEqual(trait_names, {"agility", "wits", "Melee Combat"})
