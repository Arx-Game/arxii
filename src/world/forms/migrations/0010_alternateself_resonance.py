"""Add resonance FK to AlternateSelf (#1619).

When set, assuming this alternate self shifts the character's technique
variant resolution to this resonance. The GIFT thread's level still
determines which variant tier unlocks; only the resonance axis changes.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("forms", "0009_alternateself_thumbnail"),
        ("magic", "0101_portalanchorkind_technique_travel_anchor_kind_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="alternateself",
            name="resonance",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "When set, assuming this alternate self shifts the character's "
                    "technique variant resolution to this resonance (#1619). The GIFT "
                    "thread's level still determines which variant tier unlocks; only "
                    "the resonance axis changes. Null = no resonance shift."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="alternate_self_grants",
                to="magic.resonance",
            ),
        ),
    ]
