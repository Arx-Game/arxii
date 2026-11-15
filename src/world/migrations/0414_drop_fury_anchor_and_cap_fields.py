# Contract step of the kindling expand/copy/contract (#5124). Runs after 0413 has copied the
# FuryConfig values into KindledStrengthTier and collapsed duplicate drift conversion offers.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0413_seed_kindled_strength_tiers"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="clashcontributiondeclaration",
            name="fury_anchor",
        ),
        migrations.RemoveField(
            model_name="combatroundaction",
            name="fury_anchor",
        ),
        migrations.RemoveField(
            model_name="furyconfig",
            name="bonus_scale_per_cap_point",
        ),
        migrations.RemoveField(
            model_name="furyconfig",
            name="cap_ease_per_point",
        ),
        migrations.RemoveField(
            model_name="furyconfig",
            name="provocation_cap_per_tier",
        ),
        migrations.RemoveField(
            model_name="sceneactionrequest",
            name="fury_anchor",
        ),
        migrations.AddConstraint(
            model_name="driftconversionoffer",
            constraint=models.UniqueConstraint(
                fields=("character_sheet",), name="one_drift_conversion_offer_per_sheet"
            ),
        ),
    ]
