"""Create materialized views for legend summaries.

The managed=False models in 0001_initial only create Django model stubs.
This migration executes the SQL to create the actual materialized views
in the database, which are required for fast legend total lookups.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("character_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_characterlegendsummary;",
        ),
        migrations.RunSQL(
            sql=_read_sql("guise_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_personalegendsummary;",
        ),
    ]
