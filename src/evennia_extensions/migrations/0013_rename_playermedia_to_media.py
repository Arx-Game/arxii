from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evennia_extensions", "0012_playerdata_looking_for_table"),
        # The rename must apply AFTER every migration that references the old
        # "playermedia" name: on a fresh database the graph otherwise permits
        # this rename first, and those AddField/CreateModel operations then
        # fail with "Related model 'evennia_extensions.playermedia' cannot be
        # resolved" (fresh-DB migrate broke under server settings; the test
        # settings happened to order the plan the other way, so CI never saw
        # it).
        ("combat", "0012_combatopponent_portrait"),
        ("conditions", "0018_thumbnail_fields"),
        ("forms", "0009_alternateself_thumbnail"),
        ("items", "0002_initial"),
        ("roster", "0001_initial"),
        ("scenes", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="PlayerMedia",
            new_name="Media",
        ),
        migrations.AlterField(
            model_name="media",
            name="player_data",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.CASCADE,
                related_name="media",
                to="evennia_extensions.playerdata",
                help_text=("Owning player, for player-uploaded rows. Null for staff-authored art."),
            ),
        ),
        migrations.AddField(
            model_name="media",
            name="slug",
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                unique=True,
                help_text=(
                    "Natural-key identifier for staff-authored, content-pipeline-sourced "
                    "rows. Null for player-uploaded media (never addressed by natural key)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="media",
            name="media_type",
            field=models.CharField(
                choices=[
                    ("photo", "Photo"),
                    ("portrait", "Character Portrait"),
                    ("gallery", "Gallery Image"),
                    ("background", "Background"),
                    ("illustration", "Illustration"),
                ],
                default="photo",
                max_length=20,
            ),
        ),
    ]
