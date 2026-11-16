"""Add ``KindledStrengthTier.give_in_ease_tenths`` (#5093).

Expand step: the points column ``give_in_ease`` stays until ``0446_kindled_give_in_ease_remove``;
``0445`` carries the values across. Schema-only.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0443_drop_rescue_thread_mult"),
    ]

    operations = [
        migrations.AddField(
            model_name="kindledstrengthtier",
            name="give_in_ease_tenths",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Check difficulty reduction on the control roll at this strength, in tenths of one level's width at the Fury tier's base check level.",
            ),
        ),
    ]
