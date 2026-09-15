# Contract step of the #3621 expand/migrate/contract sequence (ADR-0237). Schema only.
#
# Data disposition for Profile.personality (ADR-0237): restructure. 0107 carried every
# non-empty value on a sheet's true profile into that character's First Journal entry.
# Profile is alpha play state on a resettable table; the dev dump held one profile with
# the field empty.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0107_actors_sheet_carry"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="charactergoal",
            constraint=models.UniqueConstraint(
                fields=("character", "horizon", "ordinal"),
                name="goal_ordinal_unique_per_horizon",
            ),
        ),
        migrations.RemoveField(
            model_name="profile",
            name="personality",
        ),
    ]
