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


def test_sql_files_parsed_without_importing_build_schema():
    assert sql_files_from_build_schema(BUILD_SCHEMA_SRC) == [
        "world/scenes/sql/partition_interaction_forward.sql",
        "world/areas/sql/areaclosure.sql",
    ]


def test_migration_references_are_collected_per_module():
    sources = {
        "0101_views.py": '_read_sql("areas", "areaclosure.sql")',
        "0108_part.py": (
            '_read_sql("scenes", "partition_interaction_forward.sql")\n'
            '_read_sql("scenes", "partition_interaction_reverse.sql")'
        ),
    }
    assert sql_names_referenced_by_migrations(sources) == {
        "areaclosure.sql": {"0101_views.py"},
        "partition_interaction_forward.sql": {"0108_part.py"},
        "partition_interaction_reverse.sql": {"0108_part.py"},
    }


def test_passes_when_both_directions_are_satisfied():
    sources = {
        "0101_views.py": '_read_sql("areas", "areaclosure.sql")',
        "0108_part.py": (
            '_read_sql("scenes", "partition_interaction_forward.sql")\n'
            '_read_sql("scenes", "partition_interaction_reverse.sql")'
        ),
    }
    assert check(BUILD_SCHEMA_SRC, sources) == []


def test_fails_when_a_sql_file_is_in_build_schema_but_no_migration():
    # This is exactly the #2906 loss: the file stayed in SQL_FILES, the RunSQL
    # that applied it was squashed away.
    sources = {"0101_views.py": '_read_sql("areas", "areaclosure.sql")'}
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert len(problems) == 1
    assert "partition_interaction_forward.sql" in problems[0]
    assert "SQL_FILES" in problems[0]


def test_fails_when_a_migration_applies_sql_missing_from_build_schema():
    sources = {
        "0101_views.py": (
            '_read_sql("areas", "areaclosure.sql")\n'
            '_read_sql("scenes", "partition_interaction_forward.sql")\n'
            '_read_sql("codex", "subjectbreadcrumb.sql")'
        ),
    }
    problems = check(BUILD_SCHEMA_SRC, sources)
    assert len(problems) == 1
    assert "subjectbreadcrumb.sql" in problems[0]


def test_reverse_sql_files_are_exempt_from_the_build_schema_direction():
    # build_schema.py is forward-only by design, so a *_reverse.sql referenced
    # by a migration must NOT be required to appear in SQL_FILES.
    sources = {
        "0108_part.py": (
            '_read_sql("scenes", "partition_interaction_forward.sql")\n'
            '_read_sql("scenes", "partition_interaction_reverse.sql")\n'
            '_read_sql("areas", "areaclosure.sql")'
        ),
    }
    assert check(BUILD_SCHEMA_SRC, sources) == []
