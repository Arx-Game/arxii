"""Tests for the OBJECTDB_FIELD half of tools/lint_objectdb_param.py (#2608).

The field check is a ratchet: once an app's models.py is in the hook's scope,
every surviving ObjectDB relation field must carry a stated reason. A ratchet
that silently misses a field is worse than no ratchet, so the forms that could
hide one — the module-alias indirection, the ``to=`` keyword, a lowercase model
string — are pinned here explicitly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class ObjectDBFieldLintTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_objectdb_param.py"
        spec = importlib.util.spec_from_file_location("lint_objectdb_param", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_objectdb_param module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def _fields(self, code: str) -> list[tuple[int, int, str, str]]:
        """Return only the OBJECTDB_FIELD findings for a models.py snippet."""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "models.py"
            path.write_text(textwrap.dedent(code), encoding="utf-8")
            return [row for row in self.lint_module.check_file(path) if row[3] == "field"]

    def test_flags_plain_string_target(self) -> None:
        code = """\
            class Thing(models.Model):
                obj = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_flags_one_to_one_and_many_to_many(self) -> None:
        code = """\
            class Thing(models.Model):
                a = models.OneToOneField("objects.ObjectDB", on_delete=models.CASCADE)
                b = models.ManyToManyField("objects.ObjectDB")
            """
        self.assertEqual(len(self._fields(code)), 2)

    def test_flags_imported_name_target(self) -> None:
        code = """\
            from evennia.objects.models import ObjectDB

            class Thing(models.Model):
                obj = models.ForeignKey(ObjectDB, on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_resolves_module_level_alias(self) -> None:
        """The `_OBJECTDB_MODEL = "objects.ObjectDB"` dedupe must not hide a field."""
        code = """\
            _OBJECTDB_MODEL = "objects.ObjectDB"

            class Thing(models.Model):
                obj = models.ForeignKey(_OBJECTDB_MODEL, on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_flags_to_keyword_form(self) -> None:
        """Django accepts the target as `to=`; the positional-only check missed it."""
        code = """\
            class Thing(models.Model):
                obj = models.ForeignKey(to="objects.ObjectDB", on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_flags_lowercase_model_string(self) -> None:
        """Django resolves model strings case-insensitively; so must the check."""
        code = """\
            class Thing(models.Model):
                obj = models.ForeignKey("objects.objectdb", on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_ignores_narrower_targets(self) -> None:
        code = """\
            class Thing(models.Model):
                room = models.ForeignKey("evennia_extensions.RoomProfile", on_delete=CASCADE)
                sheet = models.ForeignKey("character_sheets.CharacterSheet", on_delete=CASCADE)
            """
        self.assertEqual(self._fields(code), [])

    def test_ignores_non_relation_call_with_matching_string(self) -> None:
        """Only relation fields name a target model in that position."""
        code = """\
            class Thing(models.Model):
                label = models.CharField("objects.ObjectDB", max_length=50)
            """
        self.assertEqual(self._fields(code), [])

    def test_suppression_inside_the_field(self) -> None:
        code = """\
            class Thing(models.Model):
                obj = models.ForeignKey(
                    "objects.ObjectDB",  # noqa: OBJECTDB_FIELD
                    on_delete=models.CASCADE,
                )
            """
        self.assertEqual(self._fields(code), [])

    def test_suppression_in_the_comment_block_above(self) -> None:
        """The audit writes its rationale above the field, so the token lives there."""
        code = """\
            class Thing(models.Model):
                # ObjectDB by design  noqa: OBJECTDB_FIELD
                # Attaches to any physical object.
                obj = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE)
            """
        self.assertEqual(self._fields(code), [])

    def test_suppression_does_not_leak_to_the_next_field(self) -> None:
        """A keeper's noqa must not silently excuse the field defined after it."""
        code = """\
            class Thing(models.Model):
                # noqa: OBJECTDB_FIELD
                first = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE)
                second = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE)
            """
        self.assertEqual(len(self._fields(code)), 1)

    def test_test_files_are_skipped(self) -> None:
        """Test modules may construct throwaway ObjectDB-shaped fixtures."""
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test_models.py"
            path.write_text(
                'obj = models.ForeignKey("objects.ObjectDB", on_delete=models.CASCADE)\n',
                encoding="utf-8",
            )
            self.assertEqual(self.lint_module.check_file(path), [])
