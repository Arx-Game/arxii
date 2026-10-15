"""Rename regard rules to faction rules and sparks to angles (#4354, spec item 15).

Schema only. ``RenameModel`` and ``RenameField`` keep every authored faction rule and
its angle text in place, so there is nothing to backfill. The reveal constraints name
the old field and the old ``kind`` value, so they are dropped here; the stored ``kind``
value changes in the next (data-only) migration and the constraints come back after it.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0225_scene_location_is_a_roomprofile"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="standoffreveal",
            name="standoff_reveal_fk_matches_kind",
        ),
        migrations.RemoveConstraint(
            model_name="standoffreveal",
            name="unique_standoff_reveal",
        ),
        migrations.RemoveConstraint(
            model_name="standoffsparkshare",
            name="unique_standoff_spark_share",
        ),
        migrations.RenameModel(old_name="RegardRule", new_name="FactionRule"),
        migrations.RenameModel(old_name="StandoffSparkShare", new_name="StandoffAngleShare"),
        migrations.RenameField(
            model_name="factionrule", old_name="spark_text", new_name="angle_text"
        ),
        migrations.RenameField(
            model_name="standoffreveal", old_name="regard_rule", new_name="faction_rule"
        ),
        migrations.RenameField(
            model_name="standoffangleshare", old_name="regard_rule", new_name="faction_rule"
        ),
    ]
