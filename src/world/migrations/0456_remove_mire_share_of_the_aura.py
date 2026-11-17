"""Remove the Mire as a share of the aura (#5177).

Schema-only. The Mire is now the corruption a Sineater carries for a Sinner
(``MireHolding``), so the share-of-the-aura bookkeeping goes.

Data disposition (ADR-0237):

* ``CharacterResonance.mire_lifetime`` is play state. The lifetime resonance it marked
  stays on the row as the character's own; only the marker, and the constraint that kept
  it within ``lifetime_earned``, are dropped. No authored content is touched.
* ``DriftConfig.mire_allowance_percent`` is one tuning number for behaviour that no
  longer exists: a deliberate discard.

The constraint is removed before the column it reads.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0455_impulses_config_and_shown"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="characterresonance",
            name="characterresonance_mire_within_lifetime",
        ),
        migrations.RemoveField(
            model_name="characterresonance",
            name="mire_lifetime",
        ),
        migrations.RemoveField(
            model_name="driftconfig",
            name="mire_allowance_percent",
        ),
    ]
