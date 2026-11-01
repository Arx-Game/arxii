"""Required-content probes for combat styles (#4884).

A style with no skill, no hit stat or no weapon kind still works, with less on its
rolls, and a Tradition that teaches no style leaves its students without one. So
these are TUNING rows that name each gap.
"""

from __future__ import annotations

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.covenants.factories import CombatStyleFactory, CombatStyleGearFactory
from world.items.constants import GearArchetype
from world.magic.factories import TraditionFactory
from world.skills.factories import MagicSkillFactory
from world.traits.factories import StatTraitFactory


def _dependency(key: str) -> rc.ContentDependency:
    """The shipped declaration itself, never a hand-copied duplicate."""
    return next(dep for dep in rc._declarations() if dep.key == key)


def _resolve(key: str) -> rc.ProbeResult:
    return _dependency(key).probe.resolve(None)


class CombatStyleProbeDeclarationTests(TestCase):
    def test_each_is_tuning_tier_with_an_admin_link(self) -> None:
        keys = (
            "combat-style-skills",
            "combat-style-hit-stats",
            "combat-style-weapon-kinds",
            "traditions-teach-a-combat-style",
        )
        for key in keys:
            dependency = _dependency(key)
            self.assertEqual(dependency.tier, rc.DependencyTier.TUNING)
            row = rc.DependencyRow(dependency, dependency.probe.resolve(None))
            self.assertIsNotNone(row.admin_url, key)


class CombatStyleSkillProbeTests(TestCase):
    def test_lists_a_style_with_no_skill_or_an_inactive_one(self) -> None:
        bare = CombatStyleFactory(name="Bare Style")
        inactive = CombatStyleFactory(
            name="Inactive Style", skill=MagicSkillFactory(is_active=False)
        )
        full = CombatStyleFactory(name="Full Style", skill=MagicSkillFactory())

        result = _resolve("combat-style-skills")

        self.assertFalse(result.present)
        self.assertIn(bare.name, result.missing)
        self.assertIn(inactive.name, result.missing)
        self.assertNotIn(full.name, result.missing)

    def test_present_when_every_style_has_a_skill(self) -> None:
        CombatStyleFactory(skill=MagicSkillFactory())
        self.assertTrue(_resolve("combat-style-skills").present)


class CombatStyleHitStatProbeTests(TestCase):
    def test_lists_a_style_with_no_hit_stat(self) -> None:
        bare = CombatStyleFactory(name="No Stat Style")
        full = CombatStyleFactory(name="Stat Style", hit_stat=StatTraitFactory())

        result = _resolve("combat-style-hit-stats")

        self.assertEqual(result.missing, (bare.name,))
        self.assertNotIn(full.name, result.missing)


class CombatStyleWeaponKindProbeTests(TestCase):
    def test_a_style_listing_only_armor_is_listed(self) -> None:
        armor_only = CombatStyleFactory(name="Armor Only")
        CombatStyleGearFactory(style=armor_only, gear_archetype=GearArchetype.HEAVY_ARMOR)
        armed = CombatStyleFactory(name="Armed")
        CombatStyleGearFactory(style=armed, gear_archetype=GearArchetype.HEAVY_ARMOR)
        CombatStyleGearFactory(style=armed, gear_archetype=GearArchetype.MELEE_TWO_HAND)
        bare_hands = CombatStyleFactory(name="Bare Hands")
        CombatStyleGearFactory(style=bare_hands, gear_archetype=GearArchetype.UNARMED)

        result = _resolve("combat-style-weapon-kinds")

        self.assertEqual(result.missing, (armor_only.name,))


class TraditionTeachesAStyleProbeTests(TestCase):
    def test_lists_an_active_tradition_teaching_no_style(self) -> None:
        silent = TraditionFactory(name="Silent Tradition")
        TraditionFactory(name="Closed Tradition", is_active=False)
        teaching = TraditionFactory(name="Teaching Tradition")
        CombatStyleFactory().taught_by.add(teaching)

        result = _resolve("traditions-teach-a-combat-style")

        self.assertEqual(result.missing, (silent.name,))
