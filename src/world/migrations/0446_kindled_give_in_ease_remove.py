"""Drop ``KindledStrengthTier.give_in_ease`` (#5093).

ADR-0237 data disposition: RESTRUCTURE. ``0445_kindled_give_in_ease_tenths_convert`` carried
every row's ease into ``give_in_ease_tenths`` (points x 2), so no authored value is lost.
Schema-only.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0445_kindled_give_in_ease_tenths_convert"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="kindledstrengthtier",
            name="give_in_ease",
        ),
    ]
