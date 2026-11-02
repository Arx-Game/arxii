"""The seed-data check lets a migration exempt itself with a stated reason (#4975).

An ALLOWED_MIGRATIONS entry pins a filename, and a pinned filename blocks the automatic
renumber in tools/auto_rebase_migration.py, so a backfill declares itself inside its file.
"""

from pathlib import Path

from check_migration_seed_data import ALLOW_MARKER, check_migration_file, has_allow_marker

SEEDING = """
from django.db import migrations


def carry(apps, schema_editor):
    apps.get_model("arxii", "Thing").objects.create(name="x")


class Migration(migrations.Migration):
    operations = [migrations.RunPython(carry, migrations.RunPython.noop)]
"""


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "0001_carry.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_a_migration_that_inserts_rows_is_flagged(tmp_path):
    assert check_migration_file(write(tmp_path, SEEDING))


def test_the_marker_with_a_reason_exempts_the_file(tmp_path):
    source = f"{ALLOW_MARKER} ADR-0237 restructure backfill of existing rows\n{SEEDING}"
    assert check_migration_file(write(tmp_path, source)) == []


def test_the_marker_without_a_reason_exempts_nothing(tmp_path):
    assert not has_allow_marker(f"{ALLOW_MARKER}\n")
    assert check_migration_file(write(tmp_path, f"{ALLOW_MARKER}   \n{SEEDING}"))


def test_the_marker_must_start_its_line(tmp_path):
    source = f"x = 1  {ALLOW_MARKER} because\n{SEEDING}"
    assert check_migration_file(write(tmp_path, source))
