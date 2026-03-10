"""Update guise legend summary view to include guises with no deeds.

Changes the view to LEFT JOIN from character_sheets_guise (consistent with
the character view) instead of starting from societies_legendentry.
"""

import pathlib

from django.db import migrations

SQL_DIR = pathlib.Path(__file__).resolve().parent.parent / "sql"


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0005_alter_legendsourcetype_options_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP MATERIALIZED VIEW IF EXISTS societies_guiselegendsummary;",
                (SQL_DIR / "guise_legend_summary.sql").read_text(),
            ],
            reverse_sql=[
                "DROP MATERIALIZED VIEW IF EXISTS societies_guiselegendsummary;",
                # Original view started from societies_legendentry
                """
                CREATE MATERIALIZED VIEW IF NOT EXISTS societies_guiselegendsummary AS
                SELECT
                    le.guise_id,
                    COALESCE(SUM(
                        CASE WHEN le.is_active THEN
                            le.base_value + COALESCE(spread_totals.total_spread, 0)
                        ELSE 0 END
                    ), 0)::integer AS guise_legend
                FROM societies_legendentry le
                LEFT JOIN (
                    SELECT legend_entry_id, SUM(value_added) AS total_spread
                    FROM societies_legendspread
                    GROUP BY legend_entry_id
                ) spread_totals ON spread_totals.legend_entry_id = le.id
                GROUP BY le.guise_id;

                CREATE UNIQUE INDEX IF NOT EXISTS societies_guiselegendsummary_guise_id
                    ON societies_guiselegendsummary (guise_id);
                """,
            ],
        ),
    ]
