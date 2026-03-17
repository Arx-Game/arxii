from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestSharedMemoryLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_shared_memory.py"
        spec = importlib.util.spec_from_file_location("lint_shared_memory", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_shared_memory module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def test_flags_models_model(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(max_length=100)
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(len(errors), 1)

    def test_flags_bare_model(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db.models import Model

            class MyModel(Model):
                pass
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(len(errors), 1)

    def test_allows_shared_memory_model(self) -> None:
        code = textwrap.dedent(
            """\
            from evennia.utils.idmapper.models import SharedMemoryModel

            class MyModel(SharedMemoryModel):
                pass
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_allows_abstract_model(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db import models

            class MyAbstract(models.Model):
                class Meta:
                    abstract = True
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_suppression_token(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db import models

            class MyModel(models.Model):  # noqa: SHARED_MEMORY
                name = models.CharField(max_length=100)
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_skips_migration_files(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(max_length=100)
            """
        )
        with TemporaryDirectory() as temp_dir:
            migrations_dir = Path(temp_dir) / "migrations"
            migrations_dir.mkdir()
            path = migrations_dir / "0001_initial.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_skips_test_files(self) -> None:
        code = textwrap.dedent(
            """\
            from django.db import models

            class MyModel(models.Model):
                name = models.CharField(max_length=100)
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_something.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])

    def test_allows_other_base_class(self) -> None:
        code = textwrap.dedent(
            """\
            class MyModel(SomeOtherBase):
                pass
            """
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.py"
            path.write_text(code, encoding="utf-8")
            errors = self.lint_module.check_file(path)

        self.assertEqual(errors, [])
