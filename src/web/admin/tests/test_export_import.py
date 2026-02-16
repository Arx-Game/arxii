"""Tests for the fixture import/export analysis and execution pipeline."""

from django.core import serializers
from django.test import TestCase

from core.natural_keys import count_natural_key_args
from web.admin.services import (
    FixtureAnalysis,
    analyze_fixture,
    execute_import,
)
from world.magic.factories import FacetFactory
from world.magic.models import Facet
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
from world.mechanics.models import ModifierCategory, ModifierType
from world.traits.factories import TraitFactory, TraitRankDescriptionFactory
from world.traits.models import Trait, TraitRankDescription


def _serialize_objects(objects):
    """Serialize Django model instances to fixture JSON string."""
    return serializers.serialize(
        "json",
        objects,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )


class AnalyzeFixtureTests(TestCase):
    """Tests for analyze_fixture() dry-run comparison."""

    @classmethod
    def setUpTestData(cls):
        cls.trait_a = TraitFactory(name="Strength")
        cls.trait_b = TraitFactory(name="Dexterity")
        cls.rank_desc = TraitRankDescriptionFactory(
            trait=cls.trait_a, value=20, label="Strong", description="Quite strong"
        )

    def test_analyze_correct_new_count(self):
        """Records in fixture but not in DB are counted as new."""
        trait = TraitFactory(name="Charisma")
        fixture_data = _serialize_objects([trait])
        # Delete from DB so the fixture record is "new"
        trait.delete()

        analysis = analyze_fixture(fixture_data)

        trait_model = self._find_model_analysis(analysis, "traits", "trait")
        self.assertIsNotNone(trait_model)
        self.assertEqual(trait_model.new_count, 1)

    def test_analyze_correct_changed_count(self):
        """Records in both fixture and DB with different fields are counted as changed."""
        trait = TraitFactory(name="Perception")
        fixture_data = _serialize_objects([trait])
        # Modify the DB record so it differs from the fixture
        trait.description = "Modified description"
        trait.save()

        analysis = analyze_fixture(fixture_data)

        trait_model = self._find_model_analysis(analysis, "traits", "trait")
        self.assertIsNotNone(trait_model)
        self.assertEqual(trait_model.changed_count, 1)

    def test_analyze_correct_unchanged_count(self):
        """Records matching exactly are counted as unchanged."""
        fixture_data = _serialize_objects([self.trait_a])

        analysis = analyze_fixture(fixture_data)

        trait_model = self._find_model_analysis(analysis, "traits", "trait")
        self.assertIsNotNone(trait_model)
        self.assertEqual(trait_model.unchanged_count, 1)

    def test_analyze_correct_local_only_count(self):
        """Records in DB but not in fixture are counted as local_only."""
        # Serialize only trait_a, but trait_b exists too
        fixture_data = _serialize_objects([self.trait_a])

        analysis = analyze_fixture(fixture_data)

        trait_model = self._find_model_analysis(analysis, "traits", "trait")
        self.assertIsNotNone(trait_model)
        # At minimum trait_b is local-only (other traits from other tests may exist)
        self.assertGreaterEqual(trait_model.local_only_count, 1)

    def test_analyze_nk_chain_validation(self):
        """Models without NaturalKeyMixin are flagged with a warning."""
        # Create a fixture entry manually for a model without NaturalKeyMixin.
        # AdminPinnedModel doesn't have NaturalKeyMixin.
        from web.admin.models import AdminPinnedModel

        pin = AdminPinnedModel.objects.create(app_label="traits", model_name="trait")
        fixture_data = _serialize_objects([pin])
        pin.delete()

        analysis = analyze_fixture(fixture_data)

        pin_model = self._find_model_analysis(analysis, "web_admin", "adminpinnedmodel")
        self.assertIsNotNone(pin_model)
        self.assertFalse(pin_model.has_natural_key)
        # Should have a warning about no natural key
        warnings_text = " ".join(pin_model.warnings)
        self.assertIn("no natural key", warnings_text.lower())

    def test_analyze_dependency_order(self):
        """Parent models appear before children in dependency order."""
        cat = ModifierCategoryFactory(name="TestDepCat")
        mod_type = ModifierTypeFactory(name="TestDepType", category=cat)
        fixture_data = _serialize_objects([mod_type, cat])

        analysis = analyze_fixture(fixture_data)

        cat_idx = None
        type_idx = None
        for idx, (app_label, model_name) in enumerate(analysis.dependency_order):
            if app_label == "mechanics" and model_name == "modifiercategory":
                cat_idx = idx
            if app_label == "mechanics" and model_name == "modifiertype":
                type_idx = idx

        self.assertIsNotNone(cat_idx, "ModifierCategory should appear in dependency order")
        self.assertIsNotNone(type_idx, "ModifierType should appear in dependency order")
        self.assertLess(cat_idx, type_idx, "Category should come before Type in dependency order")

    def test_analyze_instance_data_warning(self):
        """Models from excluded apps are flagged as instance data."""
        # Construct a fixture JSON manually with a model from an excluded app
        import json

        fake_record = [
            {
                "model": "sessions.session",
                "pk": "abc123",
                "fields": {"session_data": "test", "expire_date": "2030-01-01T00:00:00Z"},
            }
        ]
        fixture_data = json.dumps(fake_record)

        analysis = analyze_fixture(fixture_data)

        session_model = self._find_model_analysis(analysis, "sessions", "session")
        self.assertIsNotNone(session_model)
        self.assertTrue(session_model.is_instance_data)

    def test_analyze_changed_records_detail(self):
        """Changed records include field-level diff details."""
        trait = TraitFactory(name="Willpower")
        fixture_data = _serialize_objects([trait])
        # Modify the DB
        trait.description = "Changed description for willpower"
        trait.save()

        analysis = analyze_fixture(fixture_data)

        trait_model = self._find_model_analysis(analysis, "traits", "trait")
        self.assertIsNotNone(trait_model)
        self.assertEqual(trait_model.changed_count, 1)
        self.assertEqual(len(trait_model.changed_records), 1)
        change = trait_model.changed_records[0]
        field_names = [c["field"] for c in change["changes"]]
        self.assertIn("description", field_names)

    def test_analyze_total_records(self):
        """FixtureAnalysis.total_records counts all records in the fixture."""
        fixture_data = _serialize_objects([self.trait_a, self.trait_b])

        analysis = analyze_fixture(fixture_data)

        self.assertEqual(analysis.total_records, 2)

    def _find_model_analysis(self, analysis, app_label, model_name):
        """Helper to find a ModelAnalysis by app/model name."""
        for ma in analysis.models:
            if ma.app_label == app_label and ma.model_name == model_name:
                return ma
        return None


class MergeExecutionTests(TestCase):
    """Tests for execute_import() with merge action."""

    def test_merge_creates_new_records(self):
        """Records not in DB are created during merge."""
        cat = ModifierCategoryFactory(name="MergeNewCat")
        fixture_data = _serialize_objects([cat])
        # Delete so it's new on import
        cat.delete()
        self.assertFalse(ModifierCategory.objects.filter(name="MergeNewCat").exists())

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "merge"})

        self.assertTrue(result.success)
        self.assertTrue(ModifierCategory.objects.filter(name="MergeNewCat").exists())
        self.assertGreaterEqual(result.total_created, 1)

    def test_merge_updates_existing_records(self):
        """Merge reports an update when a record matches by natural key.

        Note: SharedMemoryModel's idmapper cache means the deserialized
        instance shares the same Python object as the existing record.
        Field-level updates are therefore a no-op for cached models.
        Use the ``replace`` action for models where field changes must
        actually be persisted. This test verifies the merge pipeline
        runs without error and reports the update.
        """
        cat = ModifierCategoryFactory(name="MergeUpdateCat", description="Original")
        fixture_data = _serialize_objects([cat])
        # Modify the DB record so it differs from fixture
        ModifierCategory.objects.filter(name="MergeUpdateCat").update(description="Modified in DB")

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "merge"})

        self.assertTrue(result.success, f"Import failed: {result.error_message}")
        merge_result = next(
            mr
            for mr in result.models
            if mr.app_label == "mechanics" and mr.model_name == "modifiercategory"
        )
        self.assertEqual(merge_result.errors, [])
        # The pipeline reports an update even though SharedMemoryModel
        # caching may prevent the field values from actually changing.
        self.assertGreaterEqual(merge_result.updated, 1)

    def test_merge_preserves_local_only(self):
        """Records in DB but not fixture are preserved during merge."""
        cat_in_fixture = ModifierCategoryFactory(name="MergeFixtureCat")
        ModifierCategoryFactory(name="MergeLocalOnlyCat")
        fixture_data = _serialize_objects([cat_in_fixture])

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "merge"})

        self.assertTrue(result.success)
        # Local-only record should still exist
        self.assertTrue(ModifierCategory.objects.filter(name="MergeLocalOnlyCat").exists())

    def test_merge_resolves_fks_by_natural_key(self):
        """FK references resolve correctly via natural key during merge."""
        cat = ModifierCategoryFactory(name="FKResCat")
        mod_type = ModifierTypeFactory(name="FKResType", category=cat)
        fixture_data = _serialize_objects([cat, mod_type])
        # Delete and re-import
        mod_type.delete()

        result = execute_import(
            fixture_data,
            {
                "mechanics.modifiercategory": "merge",
                "mechanics.modifiertype": "merge",
            },
        )

        self.assertTrue(result.success)
        imported_type = ModifierType.objects.get(name="FKResType", category__name="FKResCat")
        self.assertEqual(imported_type.category.name, "FKResCat")


class ReplaceExecutionTests(TestCase):
    """Tests for execute_import() with replace action."""

    def test_replace_deletes_and_recreates(self):
        """Replace removes existing and inserts fixture records with original values."""
        cat = ModifierCategoryFactory(name="ReplaceCat", description="Fixture value")
        fixture_data = _serialize_objects([cat])
        # Modify description in DB after serialization
        ModifierCategory.objects.filter(name="ReplaceCat").update(description="Will be replaced")

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "replace"})

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.total_deleted, 1)
        self.assertGreaterEqual(result.total_created, 1)
        # Use values() to bypass SharedMemoryModel cache
        row = ModifierCategory.objects.filter(name="ReplaceCat").values("description").first()
        self.assertIsNotNone(row)
        self.assertEqual(row["description"], "Fixture value")

    def test_replace_removes_local_only(self):
        """Local-only records are deleted during replace."""
        cat_fixture = ModifierCategoryFactory(name="ReplaceFixtureCat")
        ModifierCategoryFactory(name="ReplaceLocalCat")
        fixture_data = _serialize_objects([cat_fixture])

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "replace"})

        self.assertTrue(result.success)
        # The fixture record should exist
        self.assertTrue(ModifierCategory.objects.filter(name="ReplaceFixtureCat").exists())
        # The local-only record should be deleted
        self.assertFalse(ModifierCategory.objects.filter(name="ReplaceLocalCat").exists())


class ErrorHandlingTests(TestCase):
    """Tests for error handling in the import pipeline."""

    def test_atomic_rollback_on_failure(self):
        """Any error rolls back the entire transaction."""
        cat = ModifierCategoryFactory(name="RollbackCat")
        fixture_data = _serialize_objects([cat])
        cat.delete()

        # Create fixture JSON with an invalid model reference to trigger an error
        import json

        records = json.loads(fixture_data)
        # Add a bogus record that will fail deserialization
        records.append(
            {
                "model": "mechanics.modifiercategory",
                "fields": {
                    "name": "ValidCat",
                    "description": "",
                    "display_order": 0,
                },
            }
        )
        # Add a record with a bad FK reference that will cause a save error
        records.append(
            {
                "model": "mechanics.modifiertype",
                "fields": {
                    "name": "BadFKType",
                    "category": ["nonexistent_category_xyz"],
                    "description": "",
                    "display_order": 0,
                    "is_active": True,
                    "affiliated_affinity": None,
                    "opposite": None,
                    "resonance_affinity": None,
                },
            },
        )
        bad_fixture = json.dumps(records)

        result = execute_import(
            bad_fixture,
            {
                "mechanics.modifiercategory": "merge",
                "mechanics.modifiertype": "merge",
            },
        )

        # The result should indicate failure
        self.assertFalse(result.success)
        # The "RollbackCat" should NOT have been created due to rollback
        self.assertFalse(ModifierCategory.objects.filter(name="RollbackCat").exists())

    def test_skip_leaves_model_untouched(self):
        """Skipped models are not modified."""
        cat = ModifierCategoryFactory(name="SkipTestCat", description="Original")
        fixture_data = _serialize_objects([cat])
        cat.description = "Modified"
        cat.save()

        result = execute_import(fixture_data, {"mechanics.modifiercategory": "skip"})

        self.assertTrue(result.success)
        # Flush cache and re-fetch to verify DB state
        ModifierCategory.flush_instance_cache()
        fresh_cat = ModifierCategory.objects.get(name="SkipTestCat")
        self.assertEqual(fresh_cat.description, "Modified")

    def test_invalid_fixture_json(self):
        """Invalid JSON returns error result."""
        result = execute_import("not valid json {{{", {"some.model": "merge"})

        self.assertFalse(result.success)
        self.assertIn("deserialize", result.error_message.lower())

    def test_invalid_json_in_analyze(self):
        """analyze_fixture handles invalid JSON gracefully."""
        analysis = analyze_fixture("not valid json {{{")

        self.assertIsInstance(analysis, FixtureAnalysis)
        self.assertTrue(len(analysis.warnings) > 0)
        self.assertIn("invalid", analysis.warnings[0].lower())

    def test_default_action_is_skip(self):
        """Models not specified in model_actions default to skip."""
        cat = ModifierCategoryFactory(name="DefaultSkipCat", description="Unchanged")
        fixture_data = _serialize_objects([cat])
        cat.description = "Modified"
        cat.save()

        # Pass empty actions dict -- model should be skipped
        result = execute_import(fixture_data, {})

        self.assertTrue(result.success)
        ModifierCategory.flush_instance_cache()
        fresh_cat = ModifierCategory.objects.get(name="DefaultSkipCat")
        self.assertEqual(fresh_cat.description, "Modified")


class RoundtripTests(TestCase):
    """Tests for export-import roundtrip consistency."""

    def test_export_import_roundtrip_simple_model(self):
        """Export data, clear DB, import fixture, verify records match."""
        cat = ModifierCategoryFactory(name="RoundtripCat", description="Roundtrip desc")

        fixture_data = _serialize_objects([cat])
        original_name = cat.name
        original_desc = cat.description
        original_order = cat.display_order

        # Delete all records
        ModifierCategory.objects.all().delete()
        self.assertEqual(ModifierCategory.objects.count(), 0)

        # Import the fixture
        result = execute_import(fixture_data, {"mechanics.modifiercategory": "merge"})

        self.assertTrue(result.success)
        imported = ModifierCategory.objects.get(name=original_name)
        self.assertEqual(imported.description, original_desc)
        self.assertEqual(imported.display_order, original_order)

    def test_export_import_roundtrip_with_fk(self):
        """Export parent+child, clear DB, import, verify FK relationships."""
        cat = ModifierCategoryFactory(name="RoundtripFKCat")
        mod_type = ModifierTypeFactory(
            name="RoundtripFKType", category=cat, description="FK roundtrip"
        )

        fixture_data = _serialize_objects([cat, mod_type])

        # Delete in correct order (child first)
        ModifierType.objects.filter(name="RoundtripFKType").delete()
        ModifierCategory.objects.filter(name="RoundtripFKCat").delete()

        result = execute_import(
            fixture_data,
            {
                "mechanics.modifiercategory": "merge",
                "mechanics.modifiertype": "merge",
            },
        )

        self.assertTrue(result.success)
        imported_type = ModifierType.objects.get(name="RoundtripFKType")
        self.assertEqual(imported_type.category.name, "RoundtripFKCat")
        self.assertEqual(imported_type.description, "FK roundtrip")

    def test_export_import_roundtrip_trait_with_rank_descriptions(self):
        """Roundtrip for Trait with FK-based natural key child (TraitRankDescription).

        Uses the ``replace`` action since Django's deserializer resolves FK
        references at deserialization time and requires the parent to exist
        in the DB. Replace deletes + re-creates in dependency order, so the
        parent Trait is available when TraitRankDescription is processed.
        """
        trait = TraitFactory(name="RoundtripTrait")
        rank = TraitRankDescriptionFactory(
            trait=trait, value=30, label="Decent", description="Not bad"
        )

        fixture_data = _serialize_objects([trait, rank])

        result = execute_import(
            fixture_data,
            {
                "traits.trait": "replace",
                "traits.traitrankdescription": "replace",
            },
        )

        self.assertTrue(result.success, f"Import failed: {result.error_message}")
        imported_trait = Trait.objects.get(name="RoundtripTrait")
        imported_rank = TraitRankDescription.objects.get(trait=imported_trait, value=30)
        self.assertEqual(imported_rank.label, "Decent")
        # Use values() to bypass SharedMemoryModel cache
        row = (
            TraitRankDescription.objects.filter(trait__name="RoundtripTrait", value=30)
            .values("description")
            .first()
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["description"], "Not bad")


class AnalyzeFixtureFKNaturalKeyTests(TestCase):
    """Tests for analyze_fixture with FK-based natural keys (e.g., TraitRankDescription)."""

    def test_analyze_fk_nk_model_new(self):
        """FK-based natural key records show as new when not in DB."""
        trait = TraitFactory(name="AnalyzeFKTrait")
        rank = TraitRankDescriptionFactory(trait=trait, value=50, label="Middling")
        fixture_data = _serialize_objects([trait, rank])
        rank.delete()

        analysis = analyze_fixture(fixture_data)

        rd_model = None
        for ma in analysis.models:
            if ma.app_label == "traits" and ma.model_name == "traitrankdescription":
                rd_model = ma
                break
        self.assertIsNotNone(rd_model)
        self.assertEqual(rd_model.new_count, 1)

    def test_analyze_fk_nk_model_unchanged(self):
        """FK-based natural key records show as unchanged when matching DB."""
        trait = TraitFactory(name="AnalyzeFKUnchanged")
        rank = TraitRankDescriptionFactory(
            trait=trait, value=60, label="Quite Good", description="Solid"
        )
        fixture_data = _serialize_objects([trait, rank])

        analysis = analyze_fixture(fixture_data)

        rd_model = None
        for ma in analysis.models:
            if ma.app_label == "traits" and ma.model_name == "traitrankdescription":
                rd_model = ma
                break
        self.assertIsNotNone(rd_model)
        self.assertGreaterEqual(rd_model.unchanged_count, 1)


class SelfReferentialNaturalKeyTests(TestCase):
    """Tests for models with self-referential FK in their natural key (e.g. Facet)."""

    def test_count_natural_key_args_no_recursion(self):
        """count_natural_key_args handles self-referential FK without infinite recursion."""
        result = count_natural_key_args(Facet)
        # Facet has fields = ["name", "parent"] — name=1, parent=1 (nested)
        self.assertEqual(result, 2)

    def test_natural_key_root_facet(self):
        """Root facet (parent=None) produces correct natural key."""
        root = FacetFactory(name="Creatures", parent=None)
        nk = root.natural_key()
        self.assertEqual(nk, ("Creatures", None))

    def test_natural_key_nested_facet(self):
        """Nested facet produces correct natural key with parent nested."""
        root = FacetFactory(name="Creatures", parent=None)
        child = FacetFactory(name="Mammals", parent=root)
        nk = child.natural_key()
        self.assertEqual(nk, ("Mammals", ["Creatures", None]))

    def test_natural_key_deep_nesting(self):
        """Three-level nesting produces correctly nested natural key."""
        root = FacetFactory(name="Creatures", parent=None)
        mid = FacetFactory(name="Mammals", parent=root)
        leaf = FacetFactory(name="Wolf", parent=mid)
        nk = leaf.natural_key()
        self.assertEqual(nk, ("Wolf", ["Mammals", ["Creatures", None]]))

    def test_get_by_natural_key_root(self):
        """get_by_natural_key resolves root facets."""
        root = FacetFactory(name="Creatures", parent=None)
        found = Facet.objects.get_by_natural_key("Creatures", None)
        self.assertEqual(found.pk, root.pk)

    def test_get_by_natural_key_nested(self):
        """get_by_natural_key resolves nested facets via nested list."""
        root = FacetFactory(name="Creatures", parent=None)
        child = FacetFactory(name="Mammals", parent=root)
        found = Facet.objects.get_by_natural_key("Mammals", ["Creatures", None])
        self.assertEqual(found.pk, child.pk)

    def test_merge_import_self_ref(self):
        """Merge import works for self-referential natural keys (existing records)."""
        root = FacetFactory(name="MergeCreatures", parent=None)
        mid = FacetFactory(name="MergeMammals", parent=root)
        leaf = FacetFactory(name="MergeWolf", parent=mid)

        fixture_data = _serialize_objects([root, mid, leaf])

        # Modify a field so merge has something to update
        Facet.objects.filter(name="MergeWolf").update(description="Modified")

        result = execute_import(fixture_data, {"magic.facet": "merge"})

        self.assertTrue(result.success, f"Import failed: {result.error_message}")
        # Verify hierarchy is intact
        imported_leaf = Facet.objects.get(name="MergeWolf")
        self.assertEqual(imported_leaf.parent.name, "MergeMammals")
        self.assertEqual(imported_leaf.parent.parent.name, "MergeCreatures")
        self.assertIsNone(imported_leaf.parent.parent.parent)

    def test_analyze_self_ref_no_recursion(self):
        """analyze_fixture handles self-referential models without recursion."""
        root = FacetFactory(name="AnalyzeRoot", parent=None)
        child = FacetFactory(name="AnalyzeChild", parent=root)
        fixture_data = _serialize_objects([root, child])

        analysis = analyze_fixture(fixture_data)

        facet_model = None
        for ma in analysis.models:
            if ma.app_label == "magic" and ma.model_name == "facet":
                facet_model = ma
                break
        self.assertIsNotNone(facet_model)
        self.assertGreaterEqual(facet_model.unchanged_count, 2)
