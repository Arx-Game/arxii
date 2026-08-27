"""Tests for tools/lint_idmapper_mutation_order.py (Apostate ruling 7, 2026-08-27).

Mirrors the harness `test_lint_objectdb_field.py` uses: load the script as a module
via `importlib`, feed it in-memory Python snippets through a temp file, and assert on
`check_file`'s findings directly rather than shelling out to the script.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class IdmapperMutationOrderLintTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_idmapper_mutation_order.py"
        spec = importlib.util.spec_from_file_location("lint_idmapper_mutation_order", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_idmapper_mutation_order module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def _findings(self, code: str) -> list[tuple[int, int, str]]:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "services.py"
            path.write_text(textwrap.dedent(code), encoding="utf-8")
            return self.lint_module.check_file(path)

    # -- positive: the exact poisoning shape ---------------------------------

    def test_flags_mutate_save_raise_in_with_block(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj.balance -= amount
                    obj.save()
                    if amount > 1000:
                        raise ValueError("too much")
            """
        self.assertEqual(len(self._findings(code)), 1)

    def test_flags_mutate_save_raise_in_decorated_function(self) -> None:
        code = """\
            from django.db import transaction

            @transaction.atomic
            def spend(obj, amount):
                obj.balance -= amount
                obj.save()
                raise ValueError("oops")
            """
        self.assertEqual(len(self._findings(code)), 1)

    def test_flags_plain_attribute_assign_not_only_augassign(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj.balance = 0
                    obj.save(update_fields=["balance"])
                    raise ValueError("oops")
            """
        self.assertEqual(len(self._findings(code)), 1)

    def test_flags_raise_nested_inside_a_later_if(self) -> None:
        """Mutation/save state from earlier siblings must carry into a nested branch."""
        code = """\
            from django.db import transaction

            def spend(obj, amount, flag):
                with transaction.atomic():
                    obj.balance -= amount
                    obj.save()
                    if flag:
                        raise ValueError("oops")
            """
        self.assertEqual(len(self._findings(code)), 1)

    def test_flags_raise_inside_try_except_after_mutate_save(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj.balance -= amount
                    obj.save()
                    try:
                        validate(obj)
                    except ValueError:
                        raise
            """
        self.assertEqual(len(self._findings(code)), 1)

    # -- negative: safe shapes ------------------------------------------------

    def test_ignores_raise_before_mutation(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    if amount > 1000:
                        raise ValueError("too much")
                    obj.balance -= amount
                    obj.save()
            """
        self.assertEqual(self._findings(code), [])

    def test_ignores_mutation_without_a_later_raise(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj.balance -= amount
                    obj.save()
            """
        self.assertEqual(self._findings(code), [])

    def test_ignores_raise_outside_any_atomic_block(self) -> None:
        code = """\
            def spend(obj, amount):
                obj.balance -= amount
                obj.save()
                if amount > 1000:
                    raise ValueError("too much")
            """
        self.assertEqual(self._findings(code), [])

    def test_ignores_mutation_and_save_on_different_names(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, other, amount):
                with transaction.atomic():
                    obj.balance -= amount
                    other.save()
                    raise ValueError("oops")
            """
        self.assertEqual(self._findings(code), [])

    def test_ignores_reassignment_of_the_name_itself(self) -> None:
        """`obj = fresh()` is not a mutation of the cached instance."""
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj = refresh(obj)
                    obj.save()
                    raise ValueError("oops")
            """
        self.assertEqual(self._findings(code), [])

    def test_ignores_raise_in_a_sibling_branch_never_reaching_mutate_save(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount, flag):
                with transaction.atomic():
                    if flag:
                        obj.balance -= amount
                        obj.save()
                    else:
                        raise ValueError("oops")
            """
        self.assertEqual(self._findings(code), [])

    # -- suppression ------------------------------------------------------------

    def test_suppression_on_the_raise_line(self) -> None:
        code = """\
            from django.db import transaction

            def spend(obj, amount):
                with transaction.atomic():
                    obj.balance -= amount
                    obj.save()
                    if amount > 1000:
                        raise ValueError("too much")  # noqa: IDMAPPER_MUTATE_ORDER - safe here
            """
        self.assertEqual(self._findings(code), [])
