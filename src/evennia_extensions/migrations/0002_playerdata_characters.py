from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evennia_extensions", "0001_initial"),
        ("roster", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="playerdata",
            name="characters",
            field=models.ManyToManyField(
                blank=True,
                related_name="players",
                through="roster.RosterTenure",
                through_fields=("player_data", "character"),
                to="objects.ObjectDB",
            ),
        ),
    ]
