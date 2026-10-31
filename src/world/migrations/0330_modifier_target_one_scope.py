# Schema only (#4783). The check constraint lives in its own migration, after the
# two scope columns 0328 adds. Every existing row holds scope_maneuver_effect NULL and
# scope_effect_kind "" (the column default), so no row violates it.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0329_maneuver_effects"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="modifiertarget",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("scope_maneuver_effect__isnull", False),
                    models.Q(("scope_effect_kind", ""), _negated=True),
                    _negated=True,
                ),
                name="modifier_target_one_scope",
            ),
        ),
    ]
