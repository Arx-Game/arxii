"""Only a major gift may hold a substance (#5125). Schema-only.

Held apart from 0447 because it pairs ``Gift.substance`` with ``kind``. The column is new
and NULL on every row, so the check holds on every row already there.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0459_substances_and_primum_add"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="gift",
            constraint=models.CheckConstraint(
                condition=models.Q(("substance__isnull", True), ("kind", "MAJOR"), _connector="OR"),
                name="magic_gift_substance_major_only",
            ),
        ),
    ]
