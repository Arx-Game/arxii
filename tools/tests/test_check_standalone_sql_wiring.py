"""Unit tests for the standalone-SQL wiring checker.

These exercise pure functions over fixture strings - no database, no Django.
Note that tools/tests/ is not wired into CI or pre-commit; the gate for this
checker is its pre-commit hook. These tests document behavior.
"""

from check_standalone_sql_wiring import (
    check,
    sql_files_from_build_schema,
    sql_names_referenced_by_migrations,
)

BUILD_SCHEMA_SRC = """
SQL_FILES = [
    "world/scenes/sql/partition_interaction_forward.sql",
    "world/areas/sql/areaclosure.sql",
]
"""


def _migration_module(operations_body: str) -> str:
    """Build a fixture that looks like a real migration module.

    ``operations_body`` is the source of the ``operations`` list literal,
    e.g. ``'[_read_sql("areas", "areaclosure.sql")]'``.
    """
    return f"""
from django.db import migrations


def _read_sql(subpackage, filename):
    return open(filename).read()


class Migration(migrations.Migration):
    dependencies = []

    operations = {operations_body}
"""


def test_sql_files_parsed_without_importing_build_schema():
    assert sql_files_from_build_schema(BUILD_SCHEMA_SRC) == [
        "world/scenes/sql/partition_interaction_forward.sql",
        "world/areas/sql/areaclosure.sql",
    ]


def test_migration_references_are_collected_per_module():
    sources = {
        "0101_views.py": _migration_module(
            '[migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql"))]'
        ),
        "0108_part.py": _migration_module(
            "[\n"
            "    migrations.RunSQL(\n"
            '        sql=_read_sql("scenes", "partition_interaction_forward.sql"),\n'
            '        reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),\n'
            "    ),\n"
            "]"
        ),
    }
    assert sql_names_referenced_by_migrations(sources) == {
        "areaclosure.sql": {"0101_views.py"},
        "partition_interaction_forward.sql": {"0108_part.py"},
        "partition_interaction_reverse.sql": {"0108_part.py"},
    }


def test_passes_when_both_directions_are_satisfied():
    sources = {
        "0101_views.py": _migration_module(
            '[migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql"))]'
        ),
        "0108_part.py": _migration_module(
            "[\n"
            "    migrations.RunSQL(\n"
            '        sql=_read_sql("scenes", "partition_interaction_forward.sql"),\n'
            '        reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),\n'
            "    ),\n"
            "]"
        ),
    }
    assert check(BUILD_SCHEMA_SRC, sources) == []


def test_fails_when_a_sql_file_is_in_build_schema_but_no_migration():
    # This is exactly the #2906 loss: the file stayed in SQL_FILES, the RunSQL
    # that applied it was squashed away.
    sources = {
        "0101_views.py": _migration_module(
            '[migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql"))]'
        ),
    }
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert len(problems) == 1
    assert "partition_interaction_forward.sql" in problems[0]
    assert "SQL_FILES" in problems[0]


def test_fails_when_a_migration_applies_sql_missing_from_build_schema():
    sources = {
        "0101_views.py": _migration_module(
            "[\n"
            '    migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql")),\n'
            "    migrations.RunSQL(\n"
            '        sql=_read_sql("scenes", "partition_interaction_forward.sql")\n'
            "    ),\n"
            "    migrations.RunSQL(\n"
            '        sql=_read_sql("codex", "subjectbreadcrumb.sql")\n'
            "    ),\n"
            "]"
        ),
    }
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert len(problems) == 1
    assert "subjectbreadcrumb.sql" in problems[0]


def test_reverse_sql_files_are_exempt_from_the_build_schema_direction():
    # build_schema.py is forward-only by design, so a *_reverse.sql referenced
    # by a migration must NOT be required to appear in SQL_FILES.
    sources = {
        "0108_part.py": _migration_module(
            "[\n"
            "    migrations.RunSQL(\n"
            '        sql=_read_sql("scenes", "partition_interaction_forward.sql"),\n'
            '        reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),\n'
            "    ),\n"
            '    migrations.RunSQL(sql=_read_sql("areas", "areaclosure.sql")),\n'
            "]"
        ),
    }
    assert check(BUILD_SCHEMA_SRC, sources) == []


def test_commented_out_runsql_contributes_no_reference():
    # Regression pin for the reviewer's finding (a): under the old regex over
    # raw source text, a .sql filename sitting inside a comment still matched
    # _SQL_LITERAL_RE and counted as "wired" even though the RunSQL that would
    # have applied it is disabled. Comments are not part of the AST at all, so
    # the AST-based walk sees nothing here.
    sources = {
        "0108_part.py": _migration_module(
            "[\n"
            "    # migrations.RunSQL(\n"
            '    #     sql=_read_sql("scenes", "partition_interaction_forward.sql"),\n'
            '    #     reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),\n'
            "    # ),\n"
            "]"
        ),
    }
    assert sql_names_referenced_by_migrations(sources) == {}
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert any("partition_interaction_forward.sql" in p for p in problems)


def test_module_level_constant_outside_operations_contributes_no_reference():
    # Regression pin for the reviewer's finding (b): under the old regex, a
    # _read_sql(...) call sitting in a module-level constant that operations no
    # longer references still matched, because the string was still somewhere
    # in the file. The AST walk is scoped to the operations subtree only, so a
    # sibling assignment outside it is invisible.
    sources = {
        "0108_part.py": _migration_module("[]").replace(
            "class Migration(migrations.Migration):",
            (
                "_ORPHANED_SQL = _read_sql("
                '"scenes", "partition_interaction_forward.sql")\n\n\n'
                "class Migration(migrations.Migration):"
            ),
        ),
    }
    assert sql_names_referenced_by_migrations(sources) == {}
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert any("partition_interaction_forward.sql" in p for p in problems)
