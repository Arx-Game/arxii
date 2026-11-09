"""Strike narration preserves audience and thrown-weapon wording."""

from django.test import SimpleTestCase

from world.combat.services.declarations.strike import strike_narration
from world.combat.types import StrikeWeapon


class StrikeNarrationTests(SimpleTestCase):
    def test_thrown_miss_returns_weapon_to_the_correct_hand(self):
        weapon = StrikeWeapon(None, "dagger", "Thrown", "Thrown Combat", thrown=True)
        args = {
            "actor": "Hobb",
            "target": "Bandit",
            "weapon": weapon,
            "success_level": None,
            "damage": None,
        }
        self.assertEqual(
            strike_narration(**args, second_person=True),
            "You throw your dagger at Bandit and miss. The dagger is back in your hand.",
        )
        self.assertEqual(
            strike_narration(**args),
            "Hobb throws dagger at Bandit and misses. The dagger is back in their hand.",
        )

    def test_unarmed_miss_uses_strike_wording(self):
        weapon = StrikeWeapon(None, "bare hands", "Unarmed", "Brawl")
        self.assertEqual(
            strike_narration(
                actor="Hobb", target="Bandit", weapon=weapon, success_level=None, damage=None
            ),
            "Hobb strikes at Bandit with bare hands and misses.",
        )
