"""End-to-end tests for the generic crafting orchestrator (``run_crafting_recipe``).

Exercises the full pipeline — pre-validate, affordability, roll, consequence
selection, cost consumption, skill-cap clamp, attachment — through the public
``run_crafting_recipe`` entry point and the facet/style wrappers (#1031).
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.crafting.constants import CostConsumption
from world.items.exceptions import CraftingCostUnaffordable
from world.items.factories import (
    CraftingRecipeConsequenceFactory,
    CraftingSkillCapFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory


def _enchanting_trait():
    from world.traits.models import Trait

    return Trait.objects.get(name="Enchanting")


class RunCraftingRecipeTests(TestCase):
    """Integration coverage for ``run_crafting_recipe`` via the facet path."""

    def setUp(self) -> None:
        from world.items.models import QualityTier

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        # wire_enchanting_crafting seeds a Common(0-29)/Fine(30-69)/Masterwork
        # (70-9999) ladder; reuse those rows so for_score has a single ladder.
        self.common = QualityTier.objects.get(name="Common")
        self.fine = QualityTier.objects.get(name="Fine")
        self.master = QualityTier.objects.get(name="Masterwork")
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        # requires_station defaults True (#1234) — install a Lab station in the
        # crafter's room so the pre-existing pipeline tests can still craft.
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)

    def _set_skill(self, value: int) -> None:
        CharacterTraitValueFactory(
            character=self.character.sheet_data, trait=_enchanting_trait(), value=value
        )

    def _facet(self):
        from world.magic.factories import FacetFactory

        return FacetFactory()

    def _item(self, *, facet_capacity: int = 3):
        template = ItemTemplateFactory(facet_capacity=facet_capacity)
        return ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)

    def test_lucky_crit_low_skill_is_capped(self) -> None:
        """A low-skill crafter rolling a high success is clamped to their skill band."""
        # Low skill → caps at Common (numeric_max 29). Clear any seeded caps so we
        # control the ladder precisely.
        from world.items.crafting.models import CraftingSkillCap
        from world.items.services.crafting import craft_attach_facet

        CraftingSkillCap.objects.filter(recipe=self.recipe).delete()
        CraftingSkillCapFactory(recipe=self.recipe, min_skill_value=0, max_quality_tier=self.common)
        CraftingSkillCapFactory(
            recipe=self.recipe, min_skill_value=80, max_quality_tier=self.master
        )
        self._set_skill(5)  # qualifies only for the Common band
        item = self._item()
        facet = self._facet()

        # success_level 5 → big quality bonus → would land in Master without a cap.
        with force_check_outcome(CheckOutcomeFactory(name="SvcCrit", success_level=5)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=facet,
            )

        self.assertTrue(result.attached)
        self.assertEqual(result.quality_tier, self.common)

    def test_failed_craft_full_band_consumes_cost(self) -> None:
        """A failed roll whose tier consequence is FULL-band still consumes AP/anima."""
        from world.action_points.models import ActionPointPool
        from world.items.services.crafting import craft_attach_facet
        from world.magic.models import CharacterAnima

        self.recipe.action_point_cost = 3
        self.recipe.anima_cost = 2
        self.recipe.save()
        self._set_skill(50)
        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 10
        pool.save()
        anima = CharacterAnima.objects.create(character=self.character, current=10, maximum=10)

        botch = CheckOutcomeFactory(name="SvcBotch", success_level=-2)
        # A FULL-band consequence for the botch tier.
        from world.checks.factories import ConsequenceFactory

        cons = ConsequenceFactory(outcome_tier=botch, label="Spectacular Failure")
        CraftingRecipeConsequenceFactory(
            recipe=self.recipe, consequence=cons, cost_consumption=CostConsumption.FULL
        )

        item = self._item()
        with force_check_outcome(botch):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )

        self.assertFalse(result.attached)
        self.assertEqual(result.consumed["action_points"], 3)
        self.assertEqual(result.consumed["anima"], 2)
        self.assertEqual(result.consequence_label, "Spectacular Failure")
        pool.refresh_from_db()
        anima.refresh_from_db()
        self.assertEqual(pool.current, 7)
        self.assertEqual(anima.current, 8)

    def test_marginal_fail_none_band_consumes_nothing(self) -> None:
        """A NONE-band consequence consumes no AP/anima even though a roll happened."""
        from world.action_points.models import ActionPointPool
        from world.items.services.crafting import craft_attach_facet
        from world.magic.models import CharacterAnima

        self.recipe.action_point_cost = 3
        self.recipe.anima_cost = 2
        self.recipe.save()
        self._set_skill(50)
        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 10
        pool.save()
        anima = CharacterAnima.objects.create(character=self.character, current=10, maximum=10)

        near_miss = CheckOutcomeFactory(name="SvcNearMiss", success_level=0)
        from world.checks.factories import ConsequenceFactory

        cons = ConsequenceFactory(outcome_tier=near_miss, label="So Close")
        CraftingRecipeConsequenceFactory(
            recipe=self.recipe, consequence=cons, cost_consumption=CostConsumption.NONE
        )

        item = self._item()
        with force_check_outcome(near_miss):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )

        self.assertFalse(result.attached)
        self.assertEqual(result.consumed["action_points"], 0)
        self.assertEqual(result.consumed["anima"], 0)
        self.assertEqual(result.consequence_label, "So Close")
        pool.refresh_from_db()
        anima.refresh_from_db()
        self.assertEqual(pool.current, 10)
        self.assertEqual(anima.current, 10)

    def test_unaffordable_raises_before_rolling(self) -> None:
        """Insufficient AP raises ``CraftingCostUnaffordable`` before any roll/attach."""
        from world.action_points.models import ActionPointPool
        from world.items.models import ItemFacet
        from world.items.services.crafting import craft_attach_facet

        self.recipe.action_point_cost = 99
        self.recipe.save()
        self._set_skill(50)
        pool = ActionPointPool.get_or_create_for_character(self.character)
        pool.current = 1
        pool.save()

        item = self._item()
        facet = self._facet()
        with force_check_outcome(
            CheckOutcomeFactory(name="SvcShouldNotRoll", success_level=5)
        ) as capture:
            with self.assertRaises(CraftingCostUnaffordable):
                craft_attach_facet(
                    crafter_account=self.account,
                    crafter_character=self.character,
                    item_instance=item,
                    facet=facet,
                )
        # perform_check never reached; no AP spent; no row created.
        self.assertIsNone(capture.check_type)
        pool.refresh_from_db()
        self.assertEqual(pool.current, 1)
        self.assertFalse(ItemFacet.objects.filter(item_instance=item).exists())

    def test_style_wrapper_round_trips(self) -> None:
        """The style wrapper maps the generic result onto ``StyleCraftResult``."""
        from world.items.factories import StyleFactory
        from world.items.models import ItemStyle
        from world.items.services.crafting import craft_attach_style

        self._set_skill(50)
        template = ItemTemplateFactory(style_capacity=2)
        item = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        style = StyleFactory(name="SvcStyle")

        with force_check_outcome(CheckOutcomeFactory(name="SvcStyleOk", success_level=2)):
            result = craft_attach_style(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                style=style,
            )

        self.assertTrue(result.attached)
        self.assertIsNotNone(result.item_style)
        self.assertEqual(result.item_style.attachment_quality_tier, result.quality_tier)
        self.assertTrue(ItemStyle.objects.filter(item_instance=item, style=style).exists())


class CraftingStationGateTests(TestCase):
    """Station gate + wear (#1234) — the recipe's requires_station branch."""

    def setUp(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.items.crafting.models import LabStationDetails
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        self.room_profile = RoomProfileFactory()
        self.character.location = self.room_profile.objectdb
        self.character.save()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        instance = RoomFeatureInstanceFactory(
            room_profile=self.room_profile, feature_kind=kind, level=1
        )
        self.station = LabStationDetails.objects.create(
            feature_instance=instance, durability=1, max_durability=20
        )

    def _item(self, *, facet_capacity: int = 3):
        template = ItemTemplateFactory(facet_capacity=facet_capacity)
        return ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)

    def _facet(self):
        from world.magic.factories import FacetFactory

        return FacetFactory()

    def test_no_station_in_room_raises_required(self) -> None:
        from world.items.exceptions import CraftingStationRequired
        from world.items.services.crafting import craft_attach_facet

        self.station.feature_instance.delete()
        item = self._item()
        with self.assertRaises(CraftingStationRequired):
            craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )

    def test_broken_station_raises_broken(self) -> None:
        from world.items.exceptions import CraftingStationBroken
        from world.items.services.crafting import craft_attach_facet

        self.station.durability = 0
        self.station.save(update_fields=["durability"])
        item = self._item()
        with self.assertRaises(CraftingStationBroken):
            craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )

    def test_successful_attempt_decrements_station_durability(self) -> None:
        from world.items.services.crafting import craft_attach_facet

        item = self._item()
        with force_check_outcome(CheckOutcomeFactory(name="StationSuccess", success_level=2)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )
        self.assertTrue(result.attached)
        self.station.refresh_from_db()
        self.assertEqual(self.station.durability, 0)

    def test_failed_attempt_still_decrements_station_durability(self) -> None:
        """Wear fires on the roll itself, independent of success/failure (#1234)."""
        from world.checks.factories import ConsequenceFactory
        from world.items.services.crafting import craft_attach_facet

        botch = CheckOutcomeFactory(name="StationBotch", success_level=-2)
        cons = ConsequenceFactory(outcome_tier=botch, label="Station Botch")
        CraftingRecipeConsequenceFactory(
            recipe=self.recipe, consequence=cons, cost_consumption=CostConsumption.NONE
        )

        item = self._item()
        with force_check_outcome(botch):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                facet=self._facet(),
            )

        self.assertFalse(result.attached)
        self.station.refresh_from_db()
        self.assertEqual(self.station.durability, 0)

    def test_requires_station_false_bypasses_gate_entirely(self) -> None:
        from world.items.services.crafting import craft_attach_facet

        self.recipe.requires_station = False
        self.recipe.save(update_fields=["requires_station"])
        self.station.feature_instance.delete()  # no station in the room at all
        item = self._item()
        result = craft_attach_facet(
            crafter_account=self.account,
            crafter_character=self.character,
            item_instance=item,
            facet=self._facet(),
        )
        self.assertIsNotNone(result)  # ran without raising
