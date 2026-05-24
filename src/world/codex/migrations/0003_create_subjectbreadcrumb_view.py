"""Create the codex_subjectbreadcrumb materialized view.

Ported from main's original after the 2026-05-24 migration rebuild.
This view must be created via RunSQL because it's a managed=False model.
Django's makemigrations won't auto-generate it. The SQL lives in
codex/sql/subjectbreadcrumb.sql.
"""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("codex", "0002_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("subjectbreadcrumb.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS codex_subjectbreadcrumb;",
        ),
    ]
