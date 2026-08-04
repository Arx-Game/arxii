"""Restore the 5 materialized views dropped by the #2906 migration squash.

The single-app collapse (Task 4, #2906) regenerated every migration via a
plain ``makemigrations``, which only ever emits ``CreateModel`` operations.
Django has no concept of a materialized view - the 5 ``managed = False``
models below were always backed by a hand-written ``RunSQL`` operation
pointing at a checked-in ``.sql`` file (each file says so in its own header
comment: "After a migration squash, you must manually add a RunSQL
operation pointing at this file"). ``makemigrations`` cannot regenerate
that operation, so Task 4's squash silently dropped all 5, and any fresh
database crashes the first time code writes through one of these paths
(``CodexCategory.save()`` -> ``REFRESH MATERIALIZED VIEW
codex_subjectbreadcrumb`` -> ``relation does not exist`` on a scratch DB,
found while proving the fresh-DB reconstitution path, Task 7).

A 6th SQL file (``societies/sql/society_prestige_ranking.sql``) creates
``societies_societyprestigeranking``, but no Django model or live caller
references that view (verified via grep across ``src/``) - it is not
restored here; only the 5 views with a live ``managed = False`` model are.

Mirrors the pre-squash migrations exactly (``codex/migrations/
0005_create_subjectbreadcrumb_view.py``, ``areas/migrations/
0004_create_areaclosure_view.py``, ``societies/migrations/
0003_create_legend_views.py``, see git history predating the collapse).
"""

from pathlib import Path

from django.db import migrations

_WORLD_DIR = Path(__file__).resolve().parent.parent


def _read_sql(subpackage: str, filename: str) -> str:
    return (_WORLD_DIR / subpackage / "sql" / filename).read_text()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0001_initial"),
    ]

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
            sql=_read_sql("societies", "guise_legend_summary.sql"),
            reverse_sql="DROP MATERIALIZED VIEW IF EXISTS societies_personalegendsummary;",
        ),
        migrations.RunSQL(
            sql=_read_sql("societies", "covenant_legend_summary.sql"),
            reverse_sql=(
                "DROP MATERIALIZED VIEW IF EXISTS societies_covenantlegendsummary CASCADE;"
            ),
        ),
    ]
