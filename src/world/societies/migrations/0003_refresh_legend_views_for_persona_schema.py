"""Rebuild legend materialized views after Persona schema refactor.

Task 15 dropped Persona.character in favor of Persona.character_sheet (which
shares pk with ObjectDB, so character_sheet_id == character_id). The
character_legend_summary materialized view referenced the dropped column, so
it is recreated here using the new FK.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0002_create_legend_materialized_views"),
        ("scenes", "0016_remove_persona_unique_primary_persona_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP MATERIALIZED VIEW IF EXISTS societies_characterlegendsummary;\n"
                + _read_sql("character_legend_summary.sql")
            ),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_characterlegendsummary;",
        ),
    ]
