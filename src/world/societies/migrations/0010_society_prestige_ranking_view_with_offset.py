"""#738 — Rebuild SocietyPrestigeRanking MV to apply fame_perception_offset.

The 0008 migration shipped the MV with a hard-coded multiplier lookup
that ignored ``Society.fame_perception_offset``. This migration drops
that view and recreates it from the updated SQL file, which JOINs the
society's offset into the multiplier index used for displayed_prestige.

CONCURRENTLY isn't valid inside a transaction, so the migration runs the
DROP + CREATE in the standard sequence; downstream callers should
REFRESH MATERIALIZED VIEW CONCURRENTLY thereafter once the unique
index has been seeded.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0009_rankingdisplay_societies_ranking_display_scope_matches_type"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DROP MATERIALIZED VIEW IF EXISTS "
                "societies_societyprestigeranking CASCADE;\n"
                + _read_sql("society_prestige_ranking.sql")
            ),
            reverse_sql=(
                "DROP MATERIALIZED VIEW IF EXISTS societies_societyprestigeranking CASCADE;"
            ),
        ),
    ]
