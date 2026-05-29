"""Create materialized views for legend summaries (character/guise/covenant).

Ported from main's original 0002 + the RunSQL portion of 0003 after the
2026-05-24 migration rebuild. The managed=False models
(CharacterLegendSummary, PersonaLegendSummary, CovenantLegendSummary) live
in 0001_initial as Django stubs; this migration runs the SQL that creates
the actual materialized views in the DB.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0002_initial"),
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
        migrations.RunSQL(
            sql=_read_sql("covenant_legend_summary.sql"),
            reverse_sql=(
                "DROP MATERIALIZED VIEW IF EXISTS societies_covenantlegendsummary CASCADE;"
            ),
        ),
    ]
