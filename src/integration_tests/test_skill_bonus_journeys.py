"""Journeys: a life card's bonus on a skill rolls and shows (slice 1 of #4813, #4820).

Rhoswen leaves creation with Sailing at 11 and the Sailor card, which gives +10 sailing.
The number a Sailing check is worth and the number her sheet shows are both 21, while
the rating the game trains is still 11: a week of training raises that to 12 and the
other two to 22. Before #4820 a skill target did not exist on production and the trait
handler folded modifiers for stats only, so the same card rolled 11 and showed 11.

The expected numbers come from the rules the skills docs state: one check point per
rating point, weekly training pays ``5 x AP x path level`` development points, and a
skill level costs ``(value - 9) x 100`` of them.
"""

from __future__ import annotations

from decimal import Decimal

from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointConfig
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    CraftedItemRecipeFactory,
    CraftingRecipeFactory,
    CraftingRecipeModifierFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.mechanics.services import ensure_skill_target
from world.skills.factories import SkillFactory
from world.skills.models import CharacterSkillValue
from world.skills.services import run_weekly_skill_cron
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitChangeSource,
    TraitType,
)


class ASkillBonusFromACard(JourneyCase):
    """Rhoswen, Sailing, and the Sailor card."""

    def setUp(self) -> None:
        super().setUp()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.quay = self.make_room("The Quay")
        self.rhoswen = self.make_player("Rhoswen", room=self.quay)
        self.sheet = self.rhoswen.sheet_data
        self.sailing = SkillFactory(trait__name="Sailing")
        set_skill_values(
            self.sheet,
            {self.sailing: 11},
            {},
            source=TraitChangeSource.CHARACTER_CREATION,
            enforce_caps=False,
        )
        check_type = CheckTypeFactory(name="Sail", category=CheckCategoryFactory(name="Sailing"))
        CheckTypeTraitFactory(
            check_type=check_type, trait=self.sailing.trait, weight=Decimal("1.0")
        )
        self.sail = check_type

    def take_the_sailor_card(self) -> None:
        """The Sailor card, +10 sailing, granted through the one acquisition seam. The
        target it needs is the one the Skill admin's save and the paste make."""
        target = ensure_skill_target(self.sailing.trait)
        sailor = DistinctionFactory(name="Sailor", slug="sailor", cost_per_rank=0, max_rank=4)
        DistinctionEffectFactory(distinction=sailor, target=target, value_per_rank=10)
        grant_distinction(self.sheet, sailor, origin=DistinctionOrigin.CHARACTER_CREATION)

    def roll_points(self) -> int:
        return perform_check(self.rhoswen, self.sail).trait_points

    def sheet_row(self) -> dict:
        response = self.api(self.account_of(self.rhoswen)).get(
            f"/api/character-sheets/{self.sheet.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        (row,) = [r for r in response.json()["skills"] if r["skill"]["id"] == self.sailing.pk]
        return row

    def stored(self) -> int:
        return CharacterSkillValue.objects.get(character=self.sheet, skill=self.sailing).value

    def test_the_card_rolls_and_shows_and_training_moves_the_rating_underneath(self) -> None:
        self.assertEqual((self.roll_points(), self.sheet_row()["value"]), (11, 11))

        self.take_the_sailor_card()
        row = self.sheet_row()
        self.assertEqual((self.roll_points(), row["value"], row["modifier"]), (21, 21, 10))
        self.assertEqual(self.stored(), 11, "the rating the game trains is unmodified")

        # 5 x 40 AP x path level 1 = 200 development points; 11 -> 12 costs 200.
        self.assertIn(
            f"Training allocation set for {self.sailing.name}.",
            self.telnet(self.rhoswen, f"training add skill={self.sailing.pk} ap=40"),
        )
        run_weekly_skill_cron()
        row = self.sheet_row()
        self.assertEqual(self.stored(), 12, "a bonus does not raise the cost of the next rank")
        self.assertEqual((self.roll_points(), row["value"], row["modifier"]), (22, 22, 10))

    def test_a_worn_pieces_bonus_shows_on_the_sheet_with_no_card(self) -> None:
        """A sea-cloak crafted with +5 sailing, worn, and no card: the roll and the sheet
        both read 16. The sheet first priced only skills with a card or condition row, so
        it showed 11 while the roll was 16."""
        recipe = CraftingRecipeFactory()
        CraftingRecipeModifierFactory(
            recipe=recipe, target=ensure_skill_target(self.sailing.trait), base_value=5
        )
        template = ItemTemplateFactory(name="Sea-cloak")
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        item = ItemInstanceFactory(
            template=template,
            game_object=ObjectDBFactory(db_key="Sea-cloak", location=self.rhoswen),
            holder_character_sheet=self.sheet,
            quality_tier=QualityTierFactory(name="Sound"),
        )
        CraftedItemRecipeFactory(item_instance=item, recipe=recipe, quality_tier=item.quality_tier)
        self.assertIn("You equip Sea-cloak.", self.telnet(self.rhoswen, "wear Sea-cloak"))

        row = self.sheet_row()
        self.assertEqual((self.roll_points(), row["value"], row["modifier"]), (16, 16, 5))
        self.assertEqual(self.stored(), 11)
