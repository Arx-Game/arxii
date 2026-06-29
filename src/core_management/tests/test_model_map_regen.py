from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class TestWriteModelMap(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "introspect_models.py"
        spec = importlib.util.spec_from_file_location("introspect_models", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load introspect_models module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.introspect_module = module

    def test_write_model_map_produces_file_with_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "MODEL_MAP.md"
            self.introspect_module.write_model_map(output_path=output_path)
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("# Arx II Model Introspection Report", content)


class TestGetFieldInfoClassification(SimpleTestCase):
    """Cross-app relation classification in the MODEL_MAP introspector (#1204).

    Uses the live ``AudereMajoraCrossing.legend_entry`` OneToOne (magic → societies, #953)
    as the canonical cross-app fixture: the forward side must read as an FK, the reverse
    accessor must read as a reverse pointer (not a forward FK — the bug this fixes), and a
    forward ManyToMany must be emitted at all (it was previously dropped entirely).
    """

    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "introspect_models.py"
        spec = importlib.util.spec_from_file_location("introspect_models", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load introspect_models module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.get_field_info = module.get_field_info

    def test_forward_one_to_one_reads_as_fk(self) -> None:
        from django.apps import apps

        field = apps.get_model("magic", "AudereMajoraCrossing")._meta.get_field("legend_entry")
        kind, info = self.get_field_info(field)
        self.assertEqual(kind, "fk")
        self.assertIn("legend_entry -> societies.LegendEntry [OneToOne]", info)

    def test_reverse_one_to_one_reads_as_reverse_not_fk(self) -> None:
        # The #1204 bug: a reverse OneToOne (one_to_one=True) fell into the forward-FK
        # branch and was emitted as a bogus FK on the target model instead of a pointer.
        from django.apps import apps

        field = apps.get_model("societies", "LegendEntry")._meta.get_field("audere_majora_crossing")
        kind, info = self.get_field_info(field)
        self.assertEqual(kind, "reverse")
        self.assertEqual(info, "audere_majora_crossing <- magic.AudereMajoraCrossing")

    def test_forward_many_to_many_is_emitted(self) -> None:
        # Forward M2M was silently dropped before (zero [M2M] edges in the whole map).
        from django.apps import apps

        field = apps.get_model("societies", "LegendEntry")._meta.get_field("societies_aware")
        kind, info = self.get_field_info(field)
        self.assertEqual(kind, "fk")
        self.assertIn("societies_aware ->", info)
        self.assertIn("[M2M]", info)


class TestMakemigrationsModelMapThread(SimpleTestCase):
    @patch("core_management.management.commands.makemigrations.MigrationLoader")
    @patch("core_management.management.commands.makemigrations.threading.Thread")
    def test_daemon_thread_spawned_when_migrations_written(
        self,
        mock_thread_cls: MagicMock,
        _mock_loader_cls: MagicMock,  # noqa: PT019
    ) -> None:
        from core_management.management.commands.makemigrations import Command

        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.SUCCESS = lambda x: x

        fake_migration = MagicMock()
        fake_migration.name = "0001_initial"
        fake_migration.dependencies = []
        changes = {"myapp": [fake_migration]}

        with patch.object(
            type(cmd).__bases__[0],
            "write_migration_files",
            return_value=None,
        ):
            cmd.write_migration_files(changes)

        mock_thread_cls.assert_called_once()
        call_kwargs = mock_thread_cls.call_args
        self.assertTrue(call_kwargs.kwargs.get("daemon", False))
        mock_thread.start.assert_called_once()

    @patch("core_management.management.commands.makemigrations.MigrationLoader")
    @patch("core_management.management.commands.makemigrations.threading.Thread")
    def test_no_thread_when_no_migrations(
        self,
        mock_thread_cls: MagicMock,
        _mock_loader_cls: MagicMock,  # noqa: PT019
    ) -> None:
        from core_management.management.commands.makemigrations import Command

        cmd = Command()
        cmd.stdout = MagicMock()
        cmd.style = MagicMock()
        cmd.style.WARNING = lambda x: x

        with patch.object(
            type(cmd).__bases__[0],
            "write_migration_files",
            return_value=None,
        ):
            cmd.write_migration_files({})

        mock_thread_cls.assert_not_called()
