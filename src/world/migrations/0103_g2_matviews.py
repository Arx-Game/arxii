"""0103_g2_matviews: the managed=False materialized views (ADR-0272 tail, rendered from
tools/build_schema.py's SQL_FILES by arx manage squashmigrations; do not edit)."""

from pathlib import Path

from django.db import migrations

from world.migrations._generations import replaced_slice

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()


class Migration(migrations.Migration):
    replaces = replaced_slice(103, 103)
    dependencies = [("arxii", "0102_g2_partition_columns")]

    operations = [
        migrations.RunSQL(
            sql=_read_sql("areas", "areaclosure.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS areas_areaclosure;",
        ),
        migrations.RunSQL(
            sql=_read_sql("codex", "subjectbreadcrumb.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS codex_subjectbreadcrumb;",
        ),
        migrations.RunSQL(
            sql=_read_sql("societies", "character_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_characterlegendsummary;",
        ),
        migrations.RunSQL(
            sql=_read_sql("societies", "covenant_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_covenantlegendsummary;",
        ),
        migrations.RunSQL(
            sql=_read_sql("societies", "guise_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_personalegendsummary;",
        ),
    ]
