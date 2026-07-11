"""Tests for the interpose best-of-check selection helper (#2207, Task 1).

Covers the "one genuinely fiddly bit" called out by the guardian-reactions spec:
``_better_interpose_approach`` deterministically compares a guardian's pre-roll
rating in Reflexes vs Melee Defense (ADR-0019 — no dice roll in the compare) and
returns the Melee-Defense twin's shared capability name when it wins, else None
(keeping today's Reflexes-flavored default).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.areas.positioning.plummet_content import ensure_catch_content
from world.combat.interpose_content import (
    MELEE_GUARD_CAPABILITY_NAME,
    ensure_interpose_content,
)
from world.combat.services import _better_interpose_approach
from world.seeds.combat_checks import seed_combat_check_content
from world.traits.models import CharacterTraitValue, PointConversionRange, Trait, TraitType


class BetterInterposeApproachTests(TestCase):
    """_better_interpose_approach picks whichever CheckType the guardian is built for."""

    @classmethod
    def setUpTestData(cls) -> None:
        Trait.flush_instance_cache()

        # ensure_catch_content() wires the "wits" CheckTypeTrait onto the shared
        # Reflexes CheckType; ensure_interpose_content() must run AFTER
        # seed_combat_check_content() so its Melee-Defense twin approaches don't
        # get skipped (interpose_content warns + no-ops without a seeded
        # "Melee Defense" CheckType).
        ensure_catch_content()
        seed_combat_check_content()
        ensure_interpose_content()

        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

        cls.wits = Trait.objects.get(name="wits")
        cls.agility = Trait.objects.get(name="agility")
        cls.melee_combat = Trait.objects.get(name="Melee Combat")

    def setUp(self) -> None:
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()

    def test_picks_better_twin_by_build(self) -> None:
        """Duelist build → Melee-Defense twin; Reflexes build → None (today's default)."""
        # Duelist-statted guardian: high agility + Melee Combat, low wits.
        duelist = CharacterFactory()
        CharacterTraitValue.objects.create(character=duelist, trait=self.agility, value=30)
        CharacterTraitValue.objects.create(character=duelist, trait=self.melee_combat, value=30)
        CharacterTraitValue.objects.create(character=duelist, trait=self.wits, value=1)

        self.assertEqual(_better_interpose_approach(duelist), MELEE_GUARD_CAPABILITY_NAME)

        # Reflexes-statted guardian: high wits, low agility/Melee Combat.
        reflexive = CharacterFactory()
        CharacterTraitValue.objects.create(character=reflexive, trait=self.wits, value=30)
        CharacterTraitValue.objects.create(character=reflexive, trait=self.agility, value=1)
        CharacterTraitValue.objects.create(character=reflexive, trait=self.melee_combat, value=1)

        self.assertIsNone(_better_interpose_approach(reflexive))
