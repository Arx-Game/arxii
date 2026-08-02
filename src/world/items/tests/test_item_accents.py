"""Tests for #2878 Phase B: Accents — crafter-chosen per-instance style axes.

Covers:
  - ``_validate_accent_targets``: non-styleable / inactive / duplicate axes rejected.
  - ``_accent_rung_for_score``: score→rung mapping, thread cap clamp, short-ladder
    tolerance.
  - ``_resolve_accents``: a successful accent roll records an ItemAccent at a
    thread-capped level; a failed roll records nothing (the intent didn't take).
  - ``crafted_modifier_value``: accents contribute their ladder rung.
  - ``run_crafting_recipe``: accent difficulty raises the main roll's target;
    the crafted piece is credited to the maker's active persona.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.crafting.constants import (
    ACCENT_CHECK_PENALTY,
    BASE_MAX_ACCENT_LEVEL,
    CraftingRecipeKind,
)
from world.items.crafting.models import ItemAccent
from world.items.crafting.services import (
    _accent_rung_for_score,
    _resolve_accents,
    _validate_accent_targets,
    run_crafting_recipe,
)
from world.items.exceptions import InvalidAccentTarget
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.models import AccentLevel
from world.mechanics.factories import ModifierTargetFactory
from world.traits.factories import CheckOutcomeFactory


def _accent_ladder() -> None:
    for level, name in (
        (1, "slightly"),
        (2, "modestly"),
        (3, "quite"),
        (4, "very"),
        (5, "extremely"),
        (6, "amazingly"),
        (7, "legendarily"),
    ):
        AccentLevel.objects.get_or_create(level=level, defaults={"name": name})


class ValidateAccentTargetsTests(TestCase):
    def test_styleable_targets_pass(self) -> None:
        menace = ModifierTargetFactory(name="menace", is_styleable=True)
        self.assertEqual(_validate_accent_targets([menace]), [menace])
        self.assertEqual(_validate_accent_targets(None), [])

    def test_non_styleable_rejected(self) -> None:
        plain = ModifierTargetFactory(name="not-style")
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([plain])

    def test_duplicate_rejected(self) -> None:
        menace = ModifierTargetFactory(name="menace", is_styleable=True)
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([menace, menace])

    def test_inactive_rejected(self) -> None:
        dead = ModifierTargetFactory(name="dead-axis", is_styleable=True, is_active=False)
        with self.assertRaises(InvalidAccentTarget):
            _validate_accent_targets([dead])


class AccentRungForScoreTests(TestCase):
    def setUp(self) -> None:
        _accent_ladder()

    def test_below_first_rung_is_none(self) -> None:
        self.assertIsNone(_accent_rung_for_score(14, cap=7))

    def test_score_maps_to_rung(self) -> None:
        level = _accent_rung_for_score(30, cap=7)
        assert level is not None
        self.assertEqual(level.level, 2)

    def test_cap_clamps(self) -> None:
        level = _accent_rung_for_score(1000, cap=BASE_MAX_ACCENT_LEVEL)
        assert level is not None
        self.assertEqual(level.level, BASE_MAX_ACCENT_LEVEL)

    def test_short_ladder_returns_highest_available(self) -> None:
        AccentLevel.objects.filter(level__gt=2).delete()
        level = _accent_rung_for_score(1000, cap=7)
        assert level is not None
        self.assertEqual(level.level, 2)


class ResolveAccentsTests(TestCase):
    """_resolve_accents rolls one check per axis and records what realized."""

    def setUp(self) -> None:
        from world.traits.factories import CharacterTraitValueFactory
        from world.traits.models import Trait

        _accent_ladder()
        self.recipe = wire_enchanting_crafting(base_difficulty=0)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        # The −50 ambition penalty (#2886) eats an unskilled crafter's score
        # entirely — give this one real hands so a forced success realizes.
        # (Points need the seeded conversion table; wire it like production.)
        from world.traits.factories import PointConversionRangeFactory
        from world.traits.models import TraitType

        for trait_type in (TraitType.SKILL, TraitType.STAT):
            PointConversionRangeFactory(
                trait_type=trait_type, min_value=1, max_value=100, points_per_level=1
            )
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=60,
        )
        self.item = ItemInstanceFactory(
            template=ItemTemplateFactory(), holder_character_sheet=self.sheet
        )
        self.menace = ModifierTargetFactory(name="menace", is_styleable=True)

    def test_successful_roll_records_capped_accent(self) -> None:
        # success_level 5, step 10, min 1 → score ≥ 40 → rung ≥ 2, capped at 4.
        with force_check_outcome(CheckOutcomeFactory(name="AccCrit", success_level=5)):
            realized = _resolve_accents(
                recipe=self.recipe,
                crafter_character=self.character,
                target_item=self.item,
                accent_targets=[self.menace],
                difficulty=0,
            )
        self.assertEqual(len(realized), 1)
        accent = ItemAccent.objects.get(item_instance=self.item, target=self.menace)
        self.assertLessEqual(accent.level.level, BASE_MAX_ACCENT_LEVEL)
        self.assertGreaterEqual(accent.level.level, 1)

    def test_failed_roll_records_nothing(self) -> None:
        with force_check_outcome(CheckOutcomeFactory(name="AccBotch", success_level=0)):
            realized = _resolve_accents(
                recipe=self.recipe,
                crafter_character=self.character,
                target_item=self.item,
                accent_targets=[self.menace],
                difficulty=0,
            )
        self.assertEqual(realized, ())
        self.assertFalse(ItemAccent.objects.filter(item_instance=self.item).exists())

    def test_accent_feeds_crafted_modifier_value(self) -> None:
        very = AccentLevel.objects.get(level=4)
        ItemAccent.objects.create(item_instance=self.item, target=self.menace, level=very)
        # cached_crafted_recipes is prefetch-populated (CharacterEquipmentHandler);
        # outside that context, provide the empty recipe set explicitly.
        self.item.cached_crafted_recipes = []
        self.assertEqual(self.item.crafted_modifier_value(self.menace), 4)


class RunWithAccentsTests(TestCase):
    """run_crafting_recipe prices accents into difficulty and credits the maker."""

    def setUp(self) -> None:
        _accent_ladder()
        self.recipe = wire_enchanting_crafting(base_difficulty=10)
        self.sheet = CharacterSheetFactory()
        self.account = AccountFactory()
        self.character = self.sheet.character
        room_profile = RoomProfileFactory()
        self.character.location = room_profile.objectdb
        self.character.save()
        install_full_lab_station(room_profile)
        self.menace = ModifierTargetFactory(name="menace", is_styleable=True)
        self.allure = ModifierTargetFactory(name="allure", is_styleable=True)

    def _facet(self):
        from world.magic.factories import FacetFactory

        return FacetFactory()

    def test_accents_penalize_the_rolls_not_the_difficulty(self) -> None:
        from world.items.crafting.services import _accent_penalty_contributions

        item = ItemInstanceFactory(
            template=ItemTemplateFactory(facet_capacity=3), holder_character_sheet=self.sheet
        )
        with force_check_outcome(CheckOutcomeFactory(name="AccMain", success_level=3)) as capture:
            run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
                accent_targets=[self.menace, self.allure],
            )
        # Difficulty stays authored (#2886): ambition is a points penalty,
        # not the rank-quantized difficulty ladder.
        self.assertEqual(capture.target_difficulty, self.recipe.base_difficulty)
        contribs = _accent_penalty_contributions(2)
        self.assertEqual(len(contribs), 1)
        self.assertEqual(contribs[0].value, -(2 * ACCENT_CHECK_PENALTY))

    def test_invalid_accent_rejected_before_rolling(self) -> None:
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(facet_capacity=3), holder_character_sheet=self.sheet
        )
        plain = ModifierTargetFactory(name="plain")
        with self.assertRaises(InvalidAccentTarget):
            run_crafting_recipe(
                kind=CraftingRecipeKind.FACET_ATTACH,
                crafter_account=self.account,
                crafter_character=self.character,
                item_instance=item,
                target=self._facet(),
                accent_targets=[plain],
            )

    def test_created_item_carries_dual_provenance(self) -> None:
        from world.items.factories import CraftingRecipeFactory

        persona = self.sheet.primary_persona
        template = ItemTemplateFactory(is_craftable=True)
        CraftingRecipeFactory(
            kind=CraftingRecipeKind.ITEM_CREATE,
            output_item_template=template,
            requires_station=False,
            check_type=self.recipe.check_type,
            skill_trait=self.recipe.skill_trait,
            min_success_level=1,
        )
        with force_check_outcome(CheckOutcomeFactory(name="AccOk", success_level=3)):
            result = run_crafting_recipe(
                kind=CraftingRecipeKind.ITEM_CREATE,
                crafter_account=self.account,
                crafter_character=self.character,
                output_overrides={"output_template": template},
            )
        from world.items.models import ItemInstance

        assert isinstance(result.row, ItemInstance)
        self.assertEqual(result.row.crafter_persona_display, persona)
        self.assertEqual(result.row.designer_persona_display, persona)


class CraftedProvenanceLineTests(TestCase):
    """The examine layer renders ladders + credits as prose."""

    def setUp(self) -> None:
        _accent_ladder()
        from world.items.factories import QualityTierFactory

        self.divine = QualityTierFactory(
            name="Divine", numeric_min=100, numeric_max=119, sort_order=10
        )
        self.sheet = CharacterSheetFactory()
        self.item = ItemInstanceFactory(
            template=ItemTemplateFactory(),
            holder_character_sheet=self.sheet,
            quality_tier=self.divine,
        )

    def test_quality_and_accents_grammar(self) -> None:
        from world.items.services.crafted_display import crafted_provenance_line

        menace = ModifierTargetFactory(
            name="menace", is_styleable=True, styleable_adjective="menacing"
        )
        allure = ModifierTargetFactory(
            name="allure", is_styleable=True, styleable_adjective="alluring"
        )
        ItemAccent.objects.create(
            item_instance=self.item, target=menace, level=AccentLevel.objects.get(level=3)
        )
        ItemAccent.objects.create(
            item_instance=self.item, target=allure, level=AccentLevel.objects.get(level=1)
        )
        line = crafted_provenance_line(self.item)
        assert line is not None
        self.assertIn("Of divine quality", line)
        self.assertIn("quite menacing", line)
        self.assertIn("slightly alluring", line)

    def test_credits_rendered_from_dual_provenance(self) -> None:
        from world.items.services.crafted_display import crafted_provenance_line
        from world.scenes.factories import PersonaFactory

        maker = self.sheet.primary_persona
        designer = PersonaFactory()
        self.item.crafter_persona_display = maker
        self.item.designer_persona_display = designer
        self.item.save(update_fields=["crafter_persona_display", "designer_persona_display"])
        line = crafted_provenance_line(self.item)
        assert line is not None
        self.assertIn(f"Crafted by {maker.name}, designed by {designer.name}.", line)

    def test_uncrafted_item_returns_none(self) -> None:
        from world.items.services.crafted_display import crafted_provenance_line

        bare = ItemInstanceFactory(template=ItemTemplateFactory(), quality_tier=None)
        self.assertIsNone(crafted_provenance_line(bare))


class WornAccentBonusTests(TestCase):
    """Worn accent rungs flatter the fashion presentation check (#2878)."""

    def test_sum_of_worn_accent_rungs(self) -> None:
        from world.items.models import EquippedItem
        from world.items.services.fashion_presentation import _worn_accent_bonus

        _accent_ladder()
        sheet = CharacterSheetFactory()
        menace = ModifierTargetFactory(name="menace", is_styleable=True)
        item = ItemInstanceFactory(template=ItemTemplateFactory(), holder_character_sheet=sheet)
        EquippedItem.objects.create(character=sheet, item_instance=item)
        ItemAccent.objects.create(
            item_instance=item, target=menace, level=AccentLevel.objects.get(level=3)
        )
        sheet.character.equipped_items.invalidate()
        self.assertEqual(_worn_accent_bonus(sheet), 3)
