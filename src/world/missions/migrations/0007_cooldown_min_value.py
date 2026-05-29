# Hand-written migration — add MinValueValidator(timedelta(0)) to
# MissionTemplate.cooldown so the field rejects negative durations at
# the API + clean() layer.
# Hand-written because `arx manage makemigrations` hangs on the Evennia
# superuser-creation wizard in this devcontainer.

import datetime

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0006_missiongiver_name_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="missiontemplate",
            name="cooldown",
            field=models.DurationField(
                help_text="Per-giver re-offer cooldown. Must be non-negative.",
                validators=[django.core.validators.MinValueValidator(datetime.timedelta(0))],
            ),
        ),
    ]
