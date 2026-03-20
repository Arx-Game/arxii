"""Convert scenes_interaction to a range-partitioned table (monthly on timestamp).

SQL lives in scenes/sql/partition_interaction_forward.sql and
scenes/sql/partition_interaction_reverse.sql so it survives migration squashing.

See those files for full documentation of what this migration does.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("scenes", "0002_remove_scene_is_public_scene_privacy_mode_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("partition_interaction_forward.sql"),
            reverse_sql=_read_sql("partition_interaction_reverse.sql"),
        ),
    ]
