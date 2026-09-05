"""0101_g2_partition_sql: the arxii_interaction range partition and composite FKs (ADR-0272 tail,
rendered from tools/build_schema.py's SQL_FILES by arx manage squashmigrations;
SQL-only so the DDL/DML lint needs no grandfather entry; do not edit)."""

from pathlib import Path

from django.db import migrations

from world.migrations._generations import replaced_slice

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()


class Migration(migrations.Migration):
    replaces = replaced_slice(101, 103)
    dependencies = [("arxii", "0100_g2_part_100")]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("scenes", "partition_interaction_forward.sql"),
            reverse_sql=_read_sql("scenes", "partition_interaction_reverse.sql"),
        ),
        migrations.RunSQL(
            sql=_read_sql("combat", "interaction_fk_composites_forward.sql"),
            reverse_sql=_read_sql("combat", "interaction_fk_composites_reverse.sql"),
        ),
    ]
