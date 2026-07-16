"""Tests for the content export pipeline."""

import json
from pathlib import Path
import tempfile
from unittest import mock

from django.test import TestCase

from core_management.content_export import (
    CONTENT_MODELS,
    ContentExportError,
    export_to_content_repo,
)


class ContentExportTests(TestCase):
    """End-to-end: export models to a temp dir, verify format."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_export_writes_one_file_per_model_with_rows(self) -> None:
        """Models with rows get a JSON file; models with 0 rows are skipped."""
        # Create a simple content model row so export has something to write
        from world.magic.models import EffectType

        EffectType.objects.get_or_create(
            name="Test Export Effect",
            defaults={"description": "Test effect for export."},
        )

        result = export_to_content_repo(self.root)
        # At least some files should be written
        assert len(result.written) > 0
        assert result.total_records > 0
        # Each written file should be valid JSON
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            assert len(data) > 0
        # The EffectType file should exist and contain our test record
        et_path = self.root / "fixtures" / "magic" / "effecttype.json"
        assert et_path.exists()
        et_data = json.loads(et_path.read_text(encoding="utf-8"))
        names = [r["fields"]["name"] for r in et_data]
        assert "Test Export Effect" in names

    def test_exported_files_have_no_pks(self) -> None:
        """Exported fixtures must not have pk fields (natural-key only)."""
        result = export_to_content_repo(self.root)
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data:
                assert "pk" not in record, f"{path} has pk field: {record.get('pk')}"

    def test_exported_files_use_natural_key_fk_references(self) -> None:
        """FK values should be natural-key lists, not integer pks."""
        result = export_to_content_repo(self.root)
        for path in result.written:
            data = json.loads(path.read_text(encoding="utf-8"))
            for record in data:
                fields = record.get("fields", {})
                for key, value in fields.items():
                    # A natural-key FK reference is a list (e.g. ["Category", "name"])
                    # A pk-based reference would be an integer — we should never see those
                    # (use_natural_foreign_keys=True ensures this)
                    if isinstance(value, list):
                        assert all(not isinstance(v, int) or v is None for v in value), (
                            f"{path} field {key} has integer in FK list: {value}"
                        )

    def test_export_creates_subdirectory_structure(self) -> None:
        """Files are written to fixtures/<app_label>/<model_name>.json."""
        result = export_to_content_repo(self.root)
        app_labels = {m.split(".")[0] for m in CONTENT_MODELS}
        for path in result.written:
            rel = path.relative_to(self.root / "fixtures")
            parts = rel.parts
            assert len(parts) == 2, f"Expected 2 path parts, got {parts}"
            assert parts[0] in app_labels, f"Unexpected app_label dir: {parts[0]}"

    def test_export_round_trips_through_load_entries(self) -> None:
        """Export then import = no-op (all updates, no creates)."""
        from world.magic.models import EffectType

        EffectType.objects.get_or_create(
            name="Round Trip Effect",
            defaults={"description": "Round-trip test."},
        )

        from core_management.content_fixtures import build_all, load_entries

        result = export_to_content_repo(self.root)
        assert result.errors == []

        # Now load the exported files back
        load_result = build_all(self.root)
        created, _updated = load_entries(load_result)
        # All records should already exist — 0 created, N updated
        assert created == 0, f"Round-trip created {created} new records (expected 0)"

    def test_export_raises_on_missing_content_root(self) -> None:
        """When CONTENT_REPO_PATH is not set and no arg given, raises."""
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("CONTENT_REPO_PATH", None)
            with self.assertRaises(ContentExportError):
                export_to_content_repo(None)

    def test_content_models_all_have_natural_key(self) -> None:
        """Every model in the allowlist must have NaturalKeyMixin."""
        from django.apps import apps

        from core.natural_keys import NaturalKeyMixin

        for model_label in CONTENT_MODELS:
            app_label, model_name = model_label.split(".")
            model = apps.get_model(app_label, model_name)
            assert issubclass(model, NaturalKeyMixin), f"{model_label} lacks NaturalKeyMixin"
