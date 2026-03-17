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
