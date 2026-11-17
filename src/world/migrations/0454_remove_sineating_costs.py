# Removes the Sineater's anima and fatigue costs (#5177). Schema-only. Data disposition
# (ADR-0237): the two SoulTetherConfig numbers tune behaviour that is removed, a deliberate
# discard; the Sineating and SineatingPendingOffer columns are play state.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0453_sineating_ritual_adds"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sineating",
            name="anima_cost",
        ),
        migrations.RemoveField(
            model_name="sineating",
            name="fatigue_cost",
        ),
        migrations.RemoveField(
            model_name="sineatingpendingoffer",
            name="anima_cost_per_unit",
        ),
        migrations.RemoveField(
            model_name="sineatingpendingoffer",
            name="fatigue_cost_per_unit",
        ),
        migrations.RemoveField(
            model_name="soultetherconfig",
            name="anima_cost_per_unit",
        ),
        migrations.RemoveField(
            model_name="soultetherconfig",
            name="fatigue_cost_per_unit",
        ),
    ]
