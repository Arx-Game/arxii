# Generated for #2218 — pool-size difficulty scaling for the food collection mini-game.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agriculture", "0002_foodconfig_prosperity_equilibrium_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="foodconfig",
            name="pool_difficulty_threshold",
            field=models.PositiveIntegerField(
                default=50,
                help_text=(
                    "Pool size above which difficulty begins to ramp "
                    "(the first 'step' boundary). PLACEHOLDER."
                ),
            ),
        ),
        migrations.AddField(
            model_name="foodconfig",
            name="pool_difficulty_step",
            field=models.PositiveIntegerField(
                default=50,
                help_text=(
                    "Each full step of pool size above the threshold adds one "
                    "difficulty point. PLACEHOLDER."
                ),
            ),
        ),
        migrations.AddField(
            model_name="foodconfig",
            name="pool_difficulty_max_bonus",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Cap on the total difficulty bonus from pool size. PLACEHOLDER.",
            ),
        ),
    ]
