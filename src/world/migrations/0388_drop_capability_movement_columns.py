# Contract step of #5066: the capability row no longer says how a power moves or dodges.
#
# ADR-0237 disposition for these three authored-content columns: empty in production
# (verified at PR review by a maintainer; no repo seed sets them). Applications now carry
# the way of moving and the dodge (0387); nothing is copied across.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0387_movement_powers_through_applications"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="capabilitytype",
            name="reaction_cost_kind",
        ),
        migrations.RemoveField(
            model_name="capabilitytype",
            name="reaction_reach",
        ),
        migrations.RemoveField(
            model_name="capabilitytype",
            name="traversal",
        ),
    ]
