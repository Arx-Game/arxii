"""Create the areas_areaclosure materialized view.

Ported from main's original 0002 after the 2026-05-24 migration rebuild.
This view must be created via RunSQL because it's a managed=False model.
Django's makemigrations won't auto-generate it. The SQL lives in
areas/sql/areaclosure.sql.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("areas", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("areaclosure.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS areas_areaclosure;",
        ),
    ]
