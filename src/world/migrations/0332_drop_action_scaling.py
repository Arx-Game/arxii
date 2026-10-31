"""Drop the vow-only action scaling table and FleeConfig.cover_bonus (#4783).

Schema only. Data disposition (ADR-0237):

- CovenantRoleActionScaling: deliberate discard, owner ruling 2026-10-31 (magic and
  combat rows are placeholders). A vow now scales a maneuver with a VowStatScaling row on
  a maneuver effect target.
- FleeConfig.cover_bonus: restructure; 0331 carried it into the "Cover: escape bonus"
  ManeuverEffect row.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0331_cover_escape_bonus_carry"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="fleeconfig",
            name="cover_bonus",
        ),
        migrations.DeleteModel(
            name="CovenantRoleActionScaling",
        ),
    ]
