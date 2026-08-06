"""Round-trip coverage for the crafting recipe family's natural keys (#3006).

Before this, `CraftingRecipe`/`CraftingSkillCap`/`CraftingMaterialRequirement`/
`CraftingRecipeConsequence` carried no `NaturalKeyMixin`, so none of them could
be registered in `core_management.content_export.CONTENT_MODELS` — the recipe
family had no lore-authorable production data path at all. These tests mirror
the export -> load_entries round-trip pattern used across
`core_management/tests/test_content_export.py` (e.g.
`GearArchetypeCompatibilityContentExportTests`), scoped to the four crafting
models.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.content_export import export_to_content_repo
from core_management.content_fixtures import build_all, load_entries


class CraftingNaturalKeyRoundTripTests(TestCase):
    """Export -> load_entries is a no-op for each of the four crafting models."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _round_trip(self) -> None:
        result = export_to_content_repo(self.root)
        assert result.errors == []
        load_result = build_all(self.root)
        created, _updated, _ = load_entries(load_result)
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

    def test_crafting_recipe_round_trips_on_name(self) -> None:
        """CraftingRecipe's natural key is just `name` (already unique)."""
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.factories import CraftingRecipeFactory

        recipe = CraftingRecipeFactory(
            name="Round Trip Recipe",
            kind=CraftingRecipeKind.ITEM_CREATE,
            output_item_template=None,
        )

        self._round_trip()

        recipe_path = self.root / "fixtures" / "items" / "craftingrecipe.json"
        assert recipe_path.exists()
        records = {r["fields"]["name"]: r for r in json.loads(recipe_path.read_text())}
        record = records["Round Trip Recipe"]
        assert "pk" not in record

        recipe.refresh_from_db()
        assert recipe.name == "Round Trip Recipe"

    def test_crafting_recipe_natural_key_get_by_natural_key(self) -> None:
        """`natural_key()` / `get_by_natural_key()` agree for CraftingRecipe."""
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe
        from world.items.factories import CraftingRecipeFactory

        recipe = CraftingRecipeFactory(
            name="Direct Lookup Recipe",
            kind=CraftingRecipeKind.ITEM_CREATE,
            output_item_template=None,
        )

        key = recipe.natural_key()
        assert key == ("Direct Lookup Recipe",)
        assert CraftingRecipe.objects.get_by_natural_key(*key) == recipe

    def test_crafting_skill_cap_round_trips_on_recipe_and_min_skill(self) -> None:
        """CraftingSkillCap's natural key is (recipe, min_skill_value)."""
        from world.items.factories import CraftingRecipeFactory, CraftingSkillCapFactory

        recipe = CraftingRecipeFactory(name="Skill Cap Recipe")
        cap = CraftingSkillCapFactory(recipe=recipe, min_skill_value=25)

        self._round_trip()

        cap_path = self.root / "fixtures" / "items" / "craftingskillcap.json"
        assert cap_path.exists()
        records = json.loads(cap_path.read_text())
        record = next(r for r in records if r["fields"]["min_skill_value"] == 25)
        assert "pk" not in record
        # FK-in-NK: recipe serializes as a natural-key list, not a raw pk.
        assert record["fields"]["recipe"] == ["Skill Cap Recipe"]

        cap.refresh_from_db()
        assert cap.recipe_id == recipe.pk
        assert cap.min_skill_value == 25

    def test_crafting_recipe_consequence_round_trips_on_recipe_and_consequence(self) -> None:
        """CraftingRecipeConsequence's natural key is (recipe, consequence).

        `checks.Consequence` has no natural key of its own (#3006 caveat — same
        gap `ChallengeTemplateConsequence` already lives with), so the
        `consequence` component resolves by raw pk. That still round-trips
        within one database, which is what this test proves.
        """
        from world.items.factories import CraftingRecipeConsequenceFactory, CraftingRecipeFactory

        recipe = CraftingRecipeFactory(name="Consequence Recipe")
        row = CraftingRecipeConsequenceFactory(recipe=recipe)
        consequence_pk = row.consequence_id

        self._round_trip()

        row_path = self.root / "fixtures" / "items" / "craftingrecipeconsequence.json"
        assert row_path.exists()
        records = json.loads(row_path.read_text())
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record
        assert record["fields"]["recipe"] == ["Consequence Recipe"]
        assert record["fields"]["consequence"] == consequence_pk

        row.refresh_from_db()
        assert row.recipe_id == recipe.pk
        assert row.consequence_id == consequence_pk

    def test_material_requirement_item_template_branch_round_trips(self) -> None:
        """CraftingMaterialRequirement: item_template branch of the XOR key."""
        from world.items.factories import (
            CraftingMaterialRequirementFactory,
            CraftingRecipeFactory,
            ItemTemplateFactory,
        )

        recipe = CraftingRecipeFactory(name="Template Branch Recipe")
        template = ItemTemplateFactory(name="Round Trip Ingot")
        row = CraftingMaterialRequirementFactory(
            recipe=recipe,
            item_template=template,
            material_category=None,
        )

        self._round_trip()

        row_path = self.root / "fixtures" / "items" / "craftingmaterialrequirement.json"
        assert row_path.exists()
        records = json.loads(row_path.read_text())
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record
        assert record["fields"]["recipe"] == ["Template Branch Recipe"]
        assert record["fields"]["item_template"] == ["Round Trip Ingot"]
        assert record["fields"]["material_category"] is None

        row.refresh_from_db()
        assert row.item_template_id == template.pk
        assert row.material_category_id is None

    def test_material_requirement_material_category_branch_round_trips(self) -> None:
        """CraftingMaterialRequirement: material_category branch of the XOR key."""
        from world.items.factories import (
            CraftingMaterialRequirementFactory,
            CraftingRecipeFactory,
            MaterialCategoryFactory,
        )

        recipe = CraftingRecipeFactory(name="Category Branch Recipe")
        category = MaterialCategoryFactory(name="Round Trip Gemstones")
        row = CraftingMaterialRequirementFactory(
            recipe=recipe,
            item_template=None,
            material_category=category,
        )

        self._round_trip()

        row_path = self.root / "fixtures" / "items" / "craftingmaterialrequirement.json"
        assert row_path.exists()
        records = json.loads(row_path.read_text())
        assert len(records) == 1
        record = records[0]
        assert "pk" not in record
        assert record["fields"]["recipe"] == ["Category Branch Recipe"]
        assert record["fields"]["item_template"] is None
        assert record["fields"]["material_category"] == ["Round Trip Gemstones"]

        row.refresh_from_db()
        assert row.item_template_id is None
        assert row.material_category_id == category.pk

    def test_material_requirement_natural_key_both_branches_direct(self) -> None:
        """`natural_key()`/`get_by_natural_key()` resolve both XOR branches directly."""
        from world.items.crafting.models import CraftingMaterialRequirement
        from world.items.factories import (
            CraftingMaterialRequirementFactory,
            CraftingRecipeFactory,
            ItemTemplateFactory,
            MaterialCategoryFactory,
        )

        recipe = CraftingRecipeFactory(name="Direct XOR Recipe")
        template = ItemTemplateFactory(name="Direct XOR Ingot")
        category = MaterialCategoryFactory(name="Direct XOR Gemstones")

        template_row = CraftingMaterialRequirementFactory(
            recipe=recipe,
            item_template=template,
            material_category=None,
        )
        category_row = CraftingMaterialRequirementFactory(
            recipe=recipe,
            item_template=None,
            material_category=category,
        )

        template_key = template_row.natural_key()
        assert template_key == ("Direct XOR Recipe", "Direct XOR Ingot", None)
        assert CraftingMaterialRequirement.objects.get_by_natural_key(*template_key) == template_row

        category_key = category_row.natural_key()
        assert category_key == ("Direct XOR Recipe", None, "Direct XOR Gemstones")
        assert CraftingMaterialRequirement.objects.get_by_natural_key(*category_key) == category_row

    def test_quality_tier_natural_key_get_by_natural_key(self) -> None:
        """`natural_key()` / `get_by_natural_key()` agree for QualityTier (#3006 task 6b).

        `CraftingSkillCap.max_quality_tier` is an FK-by-name value in
        lore-authored crafting fixtures — without this, `_resolve_natural_key_fields`
        crashes with `AttributeError: 'SharedMemoryManager' object has no attribute
        'get_by_natural_key'` on a real `--load`.
        """
        from world.items.factories import QualityTierFactory
        from world.items.models import QualityTier

        tier = QualityTierFactory(name="Round Trip Tier")

        key = tier.natural_key()
        assert key == ("Round Trip Tier",)
        assert QualityTier.objects.get_by_natural_key(*key) == tier

    def test_quality_tier_round_trips_via_skill_cap(self) -> None:
        """QualityTier resolves through a real export -> load_entries round trip."""
        from world.items.factories import (
            CraftingRecipeFactory,
            CraftingSkillCapFactory,
            QualityTierFactory,
        )

        tier = QualityTierFactory(name="Masterwork Round Trip")
        recipe = CraftingRecipeFactory(name="Quality Tier Recipe")
        CraftingSkillCapFactory(recipe=recipe, min_skill_value=40, max_quality_tier=tier)

        self._round_trip()

        cap_path = self.root / "fixtures" / "items" / "craftingskillcap.json"
        records = json.loads(cap_path.read_text())
        record = next(r for r in records if r["fields"]["min_skill_value"] == 40)
        assert record["fields"]["max_quality_tier"] == ["Masterwork Round Trip"]

    def test_specialization_natural_key_get_by_natural_key(self) -> None:
        """`natural_key()` / `get_by_natural_key()` agree for Specialization (#3006 task 6b).

        `CraftingRecipe.specialization` is an FK-by-name value in lore-authored
        crafting fixtures — same failure mode as QualityTier above. Keyed on
        `(parent_skill, name)`, the model's existing `unique_together`.
        """
        from world.skills.factories import SpecializationFactory
        from world.skills.models import Specialization

        spec = SpecializationFactory(name="Round Trip Brewing")

        key = spec.natural_key()
        assert key == (spec.parent_skill.natural_key()[0], "Round Trip Brewing")
        assert Specialization.objects.get_by_natural_key(*key) == spec

    def test_specialization_round_trips_via_recipe(self) -> None:
        """Specialization resolves through a real export -> load_entries round trip."""
        from world.items.factories import CraftingRecipeFactory
        from world.skills.factories import SpecializationFactory

        spec = SpecializationFactory(name="Round Trip Enchanting")
        recipe = CraftingRecipeFactory(name="Specialization Recipe", specialization=spec)

        self._round_trip()

        recipe_path = self.root / "fixtures" / "items" / "craftingrecipe.json"
        records = {r["fields"]["name"]: r for r in json.loads(recipe_path.read_text())}
        record = records["Specialization Recipe"]
        assert record["fields"]["specialization"] == [
            spec.parent_skill.natural_key()[0],
            "Round Trip Enchanting",
        ]
        recipe.refresh_from_db()
        assert recipe.specialization_id == spec.pk

    def test_material_requirement_both_branches_same_recipe_round_trip_together(self) -> None:
        """Both XOR branches on the same recipe round-trip without collision.

        The partial UniqueConstraints (recipe, item_template) and (recipe,
        material_category) are each scoped to their own non-null branch, so a
        recipe may carry one row of each shape at once.
        """
        from world.items.factories import (
            CraftingMaterialRequirementFactory,
            CraftingRecipeFactory,
            ItemTemplateFactory,
            MaterialCategoryFactory,
        )

        recipe = CraftingRecipeFactory(name="Mixed Branch Recipe")
        template = ItemTemplateFactory(name="Mixed Branch Ingot")
        category = MaterialCategoryFactory(name="Mixed Branch Gemstones")
        template_row = CraftingMaterialRequirementFactory(
            recipe=recipe, item_template=template, material_category=None
        )
        category_row = CraftingMaterialRequirementFactory(
            recipe=recipe, item_template=None, material_category=category
        )

        self._round_trip()

        row_path = self.root / "fixtures" / "items" / "craftingmaterialrequirement.json"
        records = json.loads(row_path.read_text())
        assert len(records) == 2

        template_row.refresh_from_db()
        category_row.refresh_from_db()
        assert template_row.item_template_id == template.pk
        assert template_row.material_category_id is None
        assert category_row.item_template_id is None
        assert category_row.material_category_id == category.pk
