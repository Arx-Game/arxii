"""Relax GIFT thread unique constraint to allow multi-resonance (#1619).

The constraint ``uniq_thread_gift_active`` previously enforced one active
GIFT thread per ``(owner, target_gift)``. It now keys on
``(owner, target_gift, resonance)``, allowing a character to hold multiple
active GIFT threads on the same gift at different resonances — but still
preventing duplicates at the same resonance.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0101_portalanchorkind_technique_travel_anchor_kind_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="thread",
            name="uniq_thread_gift_active",
        ),
        migrations.AddConstraint(
            model_name="thread",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    retired_at__isnull=True,
                    target_kind="GIFT",
                ),
                fields=["owner", "target_gift", "resonance"],
                name="uniq_thread_gift_active",
            ),
        ),
    ]
