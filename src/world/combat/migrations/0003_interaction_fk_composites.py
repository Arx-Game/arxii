"""Add composite FK constraints from combat tables to scenes_interaction (id, timestamp).

The two combat tables (combat_combatroundaction and combat_clashcontribution)
each carry an (interaction_id, interaction_timestamp) pair that targets the
partitioned scenes_interaction table. The Django FKs are declared
db_constraint=False because Django cannot express composite FK constraints;
this migration adds them via raw SQL.

SQL lives in combat/sql/interaction_fk_composites_forward.sql and
combat/sql/interaction_fk_composites_reverse.sql so it survives future
migration churn (mirrors the pattern from
scenes/migrations/0003_partition_interaction.py).
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("combat", "0002_initial"),
        ("scenes", "0004_partition_interaction"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("interaction_fk_composites_forward.sql"),
            reverse_sql=_read_sql("interaction_fk_composites_reverse.sql"),
        ),
    ]
