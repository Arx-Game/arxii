"""Drop SocietyPrestigeRanking + the underlying materialized view.

Adversarial-review fold-in: the MV + nightly cron were premature at
pre-launch scale. ``get_society_prestige_top_n`` now does a runtime
ordered query against ``scenes_persona`` filtered by membership; the
MV / unique index / CONCURRENTLY-refresh / SQLite vendor gate / cron
registration all go away. A scale-driven re-introduction can rebuild
this when persona counts actually warrant it.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0011_legendentry_archetypes"),
    ]

    operations = [
        migrations.RunSQL(
            sql=("DROP MATERIALIZED VIEW IF EXISTS societies_societyprestigeranking CASCADE;"),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.DeleteModel(
            name="SocietyPrestigeRanking",
        ),
    ]
