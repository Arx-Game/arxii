"""Drop ``CheckRank.min_points`` (#5093).

Data disposition (ADR-0237): deliberate discard. A rank's threshold is now the CHECK lane's
level-N ``ModifierLevelBaseline``, so the stored thresholds are replaced by the rank-means-
level rulings; the rank numbers and names survive. ``0418_check_ladder_rows`` runs first and
writes the baseline and rank rows that replace them, so no database is left with ranks and no
thresholds. Schema-only: no row is read or written.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0418_check_ladder_rows"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="checkrank",
            name="arxii_check_min_poi_75ae5b_idx",
        ),
        migrations.RemoveField(
            model_name="checkrank",
            name="min_points",
        ),
        migrations.AlterField(
            model_name="checkrank",
            name="rank",
            field=models.SmallIntegerField(
                help_text="Rank level (0 = weakest, higher = stronger). Rank N starts at the level-N check baseline.",
                unique=True,
            ),
        ),
    ]
