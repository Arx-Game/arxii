"""#676 Phase I — Materialized view for per-society prestige ranking.

Ships alongside the managed=False ``SocietyPrestigeRanking`` model from
0007; that migration creates the Django-side stub, this one runs the
SQL that creates the actual materialized view in PostgreSQL.

Refresh nightly via ``REFRESH MATERIALIZED VIEW CONCURRENTLY
societies_societyprestigeranking;`` once data exists.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0007_societyprestigeranking_rankingdisplay"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("society_prestige_ranking.sql"),
            reverse_sql=(
                "DROP MATERIALIZED VIEW IF EXISTS societies_societyprestigeranking CASCADE;"
            ),
        ),
    ]
