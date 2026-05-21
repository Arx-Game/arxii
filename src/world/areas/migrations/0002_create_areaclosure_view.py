"""Create the areas_areaclosure materialized view.

This view must be created via RunSQL because it's a managed=False model.
Django's makemigrations won't auto-generate it. The SQL lives in
areas/sql/areaclosure.sql and must be re-referenced after any migration squash.
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
