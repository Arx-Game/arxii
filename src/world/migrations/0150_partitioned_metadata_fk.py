"""Apply PostgreSQL composite metadata references after their model state exists."""

from pathlib import Path

from django.db import migrations

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(filename: str) -> str:
    """Read the checked-in PostgreSQL DDL used by schema build and replay."""
    return (_WORLD_DIR / "scenes" / "sql" / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [("arxii", "0149_partitioned_metadata_integrity")]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("interaction_metadata_fk_forward.sql"),
            reverse_sql=_read_sql("interaction_metadata_fk_reverse.sql"),
        ),
    ]
