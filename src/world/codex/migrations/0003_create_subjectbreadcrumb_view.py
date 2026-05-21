"""Create the codex_subjectbreadcrumb materialized view.

This view must be created via RunSQL because it's a managed=False model.
Django's makemigrations won't auto-generate it. The SQL lives in
codex/sql/subjectbreadcrumb.sql and must be re-referenced after any migration squash.
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
