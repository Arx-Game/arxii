"""The migration linter separates schema operations from data operations.

A migration is one transaction. PostgreSQL queues a deferred FK trigger event per
row written and refuses ALTER TABLE while any are pending, so mixing the two dies
with "cannot ALTER TABLE ... because it has pending trigger events" - but only on a
database that has rows, which is why CI never saw it (#3617, 2026-09-04).
"""

from pathlib import Path

from lint_migration_ddl_dml import GRANDFATHERED, check_migration, classify_source

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def migration(*operations: str) -> str:
    body = "\n".join(f"        migrations.{op}," for op in operations)
    return "class Migration(migrations.Migration):\n    operations = [\n" + body + "\n    ]\n"


def test_data_then_schema_is_flagged():
    data, schema = classify_source(migration("RunPython(forwards)", "AddConstraint(x)"))
    assert data == ["RunPython"]
    assert schema == ["AddConstraint"]


def test_schema_then_data_is_flagged_too():
    """Reverse migrations replay backwards, so this order is just as broken."""
    data, schema = classify_source(migration("AddField(x)", "RunPython(forwards)"))
    assert data == ["RunPython"]
    assert schema == ["AddField"]


def test_run_sql_counts_as_data():
    data, _ = classify_source(migration("RunSQL('...')", "AlterField(x)"))
    assert data == ["RunSQL"]


def test_schema_only_migration_is_clean():
    data, schema = classify_source(migration("AddField(x)", "RemoveField(y)"))
    assert data == []
    assert schema == ["AddField", "RemoveField"]


def test_data_only_migration_is_clean():
    data, schema = classify_source(migration("RunPython(forwards, backwards)"))
    assert data == ["RunPython"]
    assert schema == []


def test_a_migration_with_no_operations_is_clean():
    assert classify_source("class Migration(migrations.Migration):\n    operations = []\n") == (
        [],
        [],
    )


def test_the_migration_that_broke_the_deploy_would_be_caught(tmp_path):
    """0220_upbringings as originally merged: a backfill, then AddConstraint."""
    path = tmp_path / "0220_upbringings.py"
    path.write_text(migration("RunPython(backfill)", "AddConstraint(c)", "RemoveField(f)"))
    message = check_migration(path)
    assert message is not None
    assert "pending trigger events" not in message  # it explains the fix, not the symptom
    assert "expand/migrate/contract" in message


def test_grandfathered_migrations_are_all_real_files():
    """The list is closed, so every entry must still name a migration that exists."""
    for relative in GRANDFATHERED:
        assert (PROJECT_ROOT / "src" / relative).is_file(), relative
