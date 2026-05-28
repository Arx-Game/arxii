# Hand-written migration — add unique constraint to MissionGiver.name.
# Dropped slug in 0005; name takes over as canonical human identifier.
# Hand-written because `arx manage migrate` hangs on the Evennia
# superuser-creation wizard in this devcontainer.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("missions", "0005_drop_slug_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="missiongiver",
            name="name",
            field=models.CharField(max_length=200, unique=True),
        ),
    ]
