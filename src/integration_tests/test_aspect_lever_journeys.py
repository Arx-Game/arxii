"""Journeys: a life card's bonus on an Aspect raises the checks that weight it (#4827).

Slice 2 of #4813.

Ysolde takes the Whisper card, ``+10 diplomacy``. A parley, which weights Diplomacy at
1.0, is worth ten points more to her than before the card through the modifier seam
every real roll uses; a haggle, which weights it at 0.5, five more; a climb, which does
not weight it, the same as before. The breakdown names the Aspect so a player can read
where the ten came from. The expected numbers come from the parent spec's slice 2
section: the card's number, times the check's own aspect weight, truncated.
"""

from __future__ import annotations

from decimal import Decimal

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckCategoryFactory, CheckTypeAspectFactory, CheckTypeFactory
from world.checks.models import CheckType
from world.checks.services import collect_check_modifiers, perform_check_with_modifiers
from world.classes.factories import AspectFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.services import ensure_aspect_target
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CharacterTraitValue, ResultChart, Trait


class AnAspectBonusFromACard(JourneyCase):
    """Ysolde, Diplomacy, and the Whisper card."""

    def setUp(self) -> None:
        super().setUp()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        CheckSystemSetupFactory.create()
        self.salon = self.make_room("The Salon")
        self.ysolde = self.make_player("Ysolde", room=self.salon)
        self.sheet = self.ysolde.sheet_data
        self.diplomacy = AspectFactory(name="Diplomacy")
        social = CheckCategoryFactory(name="Social (aspect lever)")
        self.parley = CheckTypeFactory(name="Parley", category=social)
        CheckTypeAspectFactory(check_type=self.parley, aspect=self.diplomacy, weight=Decimal("1.0"))
        self.haggle = CheckTypeFactory(name="Haggle", category=social)
        CheckTypeAspectFactory(check_type=self.haggle, aspect=self.diplomacy, weight=Decimal("0.5"))
        self.climb = CheckTypeFactory(name="Climb", category=social)

    def take_the_whisper_card(self) -> None:
        """The Whisper card, +10 diplomacy, granted through the one acquisition seam onto
        the target the Aspect admin's save and the seed make."""
        target = ensure_aspect_target(self.diplomacy)
        whisper = DistinctionFactory(name="Whisper", slug="whisper", cost_per_rank=0, max_rank=4)
        DistinctionEffectFactory(distinction=whisper, target=target, value_per_rank=10)
        grant_distinction(self.sheet, whisper, origin=DistinctionOrigin.CHARACTER_CREATION)

    def worth(self, check_type: CheckType) -> int:
        return perform_check_with_modifiers(self.ysolde, check_type).total_points

    def test_the_card_raises_the_checks_that_weight_the_aspect_by_their_weight(self) -> None:
        before = {c.name: self.worth(c) for c in (self.parley, self.haggle, self.climb)}

        self.take_the_whisper_card()
        after = {c.name: self.worth(c) for c in (self.parley, self.haggle, self.climb)}

        self.assertEqual(after["Parley"] - before["Parley"], 10, "a full-weight check")
        self.assertEqual(after["Haggle"] - before["Haggle"], 5, "a half-weight check")
        self.assertEqual(after["Climb"] - before["Climb"], 0, "a check without the Aspect")

        breakdown = collect_check_modifiers(self.sheet, self.parley)
        labels = [c.source_label for c in breakdown.contributions]
        self.assertIn("Whisper (Diplomacy)", labels)
