# Burden reflections and the settling of the Mire, part two (#5177). Schema-only: swaps the
# reflection's two-way "grant or resonance" check for "exactly one of grant, resonance or
# tether", and adds the check that a burden takes only Absolve, Condemn or Succumb while every
# other reflection takes only Embrace or Disown. 0453 added the tether column; every existing
# reflection has it null and one of Embrace or Disown, so each satisfies both checks.
# Data disposition (ADR-0237): nothing is dropped.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0455_reflect_on_the_mire_adds"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="reflection",
            name="reflection_grant_xor_resonance",
        ),
        migrations.AddConstraint(
            model_name="reflection",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("grant__isnull", False),
                        ("resonance__isnull", True),
                        ("tether__isnull", True),
                    ),
                    models.Q(
                        ("grant__isnull", True),
                        ("resonance__isnull", False),
                        ("tether__isnull", True),
                    ),
                    models.Q(
                        ("grant__isnull", True),
                        ("resonance__isnull", True),
                        ("tether__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="reflection_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="reflection",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("tether__isnull", False),
                        ("choice__in", ("ABSOLVE", "CONDEMN", "SUCCUMB")),
                    ),
                    models.Q(("tether__isnull", True), ("choice__in", ("EMBRACE", "DISOWN"))),
                    _connector="OR",
                ),
                name="reflection_choice_fits_target",
            ),
        ),
    ]
