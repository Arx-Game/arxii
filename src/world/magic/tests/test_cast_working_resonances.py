"""A cast's resonance-tied power follows the one resonance it is worked in (#5231, E1).

A Gift thread holds a Primal and an Abyssal resonance. The caster wears an Abyssal-tied
touchstone, holds an Abyssal-scoped POWER modifier, and has a settled Abyssal share (her Primal
share is not settled), with more lifetime resonance earned in the Abyssal one. A cast worked in
the Primal resonance gets none of the Abyssal-tied power; the same cast worked in the Abyssal
resonance gets all of it. This is a unit test because the seam under it, the power ledger of one
real ``use_technique`` call, is not reachable from a journey's text.

Expected lines, worked by hand from the setup below:

- touchstone: a tier-3 touchstone at the default scale of 10 is 3 * 10 // 10 = 3, for the
  Abyssal resonance only.
- Abyssal-scoped POWER modifier from a distinction: rank 1 at 6 per rank = 6, Abyssal only.
- aura power: alignment bonus 20, standing bonus 1 per point earned. Abyssal: her Abyssal share
  is settled, so the full 20, plus 50 earned = 70. Primal: her Primal share is not settled and
  stands at 20 percent, so 20 percent of 20 = 4, plus 10 earned = 14.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.magic.factories import (
    AffinityFactory,
    AuraPowerConfigFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.magic.specialization.services import (
    cast_working_resonances,
    grant_gift_to_character,
)
from world.mechanics.constants import POWER_CATEGORY_NAME
from world.mechanics.effect_targets import technique_effect_context
from world.mechanics.factories import (
    CharacterEngagementFactory,
    ModifierCategoryFactory,
    ModifierTargetFactory,
)
from world.mechanics.services import create_distinction_modifiers


def _lines_of(ledger: object) -> dict[str, int]:
    """Sum of the ledger's amounts by source label."""
    lines: dict[str, int] = {}
    for entry in ledger.entries:  # type: ignore[attr-defined]
        lines[entry.source_label] = lines.get(entry.source_label, 0) + entry.amount
    return lines


class CastWorkingResonancesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.primal_resonance = ResonanceFactory(affinity=AffinityFactory(name="Primal"))
        cls.abyssal_resonance = ResonanceFactory(affinity=AffinityFactory(name="Abyssal"))
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=2)
        anima = CharacterAnimaFactory(current=50, maximum=50)
        cls.sheet = anima.character
        cls.character = cls.sheet.character
        CharacterEngagementFactory(character=cls.sheet)
        # One Gift thread, the Primal resonance leading, the Abyssal one second.
        grant_gift_to_character(
            cls.sheet,
            cls.technique.gift,
            resonances=[cls.primal_resonance, cls.abyssal_resonance],
        )
        CharacterAuraFactory(
            character=cls.sheet,
            celestial=Decimal(0),
            primal=Decimal(20),
            abyssal=Decimal(80),
        )
        for share in cls.sheet.aura.cached_shares:
            if share.affinity.name == "Primal":
                share.settled_percent = Decimal(0)
                share.save()
        AuraPowerConfigFactory(affinity_alignment_bonus=20, resonance_standing_bonus=1)
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.primal_resonance, lifetime_earned=10
        )
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.abyssal_resonance, lifetime_earned=50
        )
        # An Abyssal-tied touchstone, worn.
        template = ItemTemplateFactory(
            tied_resonance=cls.abyssal_resonance,
            resonance_tier=ResonanceTierFactory(name="Profound", tier_level=3),
        )
        EquippedItemFactory(
            character=cls.sheet, item_instance=ItemInstanceFactory(template=template)
        )
        # An Abyssal-scoped POWER modifier of 6.
        power_target = ModifierTargetFactory(
            category=ModifierCategoryFactory(name=POWER_CATEGORY_NAME),
            name="power_abyssal_pin",
            target_resonance=cls.abyssal_resonance,
        )
        distinction = DistinctionFactory(name="Abyssal Pin Potency")
        DistinctionEffectFactory(distinction=distinction, target=power_target, value_per_rank=6)
        create_distinction_modifiers(
            CharacterDistinctionFactory(character=cls.sheet, distinction=distinction, rank=1)
        )

    def _ledger_lines(self, *, worked_in: object | None) -> dict[str, int]:
        captured: dict[str, object] = {}

        def resolve_fn(*, power: int, ledger: object, extra_modifiers: int = 0) -> SimpleNamespace:
            captured["ledger"] = ledger
            return SimpleNamespace(check_result=None)

        use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=resolve_fn,
            preferred_resonance=worked_in,
        )
        return _lines_of(captured["ledger"])

    def test_a_cast_worked_in_the_primal_resonance_gets_none_of_the_abyssal_power(self) -> None:
        lines = self._ledger_lines(worked_in=None)  # the default is the leading, Primal one
        self.assertEqual(lines.get("aura power"), 14)
        self.assertNotIn("touchstone power", lines)
        self.assertNotIn("Abyssal Pin Potency", " ".join(lines))

    def test_a_cast_worked_in_the_abyssal_resonance_gets_all_of_it(self) -> None:
        lines = self._ledger_lines(worked_in=self.abyssal_resonance)
        self.assertEqual(lines.get("aura power"), 70)
        self.assertEqual(lines.get("touchstone power"), 3)
        self.assertEqual(sum(v for k, v in lines.items() if "Abyssal Pin" in k), 6)

    def test_the_helper_and_the_effect_context_follow_the_cast_resonance(self) -> None:
        both = cast_working_resonances(self.character, self.technique, None)
        self.assertEqual(
            [r.pk for r in both], [self.primal_resonance.pk, self.abyssal_resonance.pk]
        )
        one = cast_working_resonances(self.character, self.technique, self.abyssal_resonance)
        self.assertEqual([r.pk for r in one], [self.abyssal_resonance.pk])
        context = technique_effect_context(
            self.sheet, self.technique, cast_resonance=self.primal_resonance
        )
        self.assertEqual(context.resonance_ids, frozenset({self.primal_resonance.pk}))
