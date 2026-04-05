# Generated manually — adds EffectTarget.TARGET choice to ConsequenceEffect.target field.
# Cosmetic migration: choices are Python-only validation; no DB schema change in PostgreSQL.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("checks", "0005_alter_consequenceeffect_effect_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="consequenceeffect",
            name="target",
            field=models.CharField(
                choices=[
                    ("self", "Self (acting character)"),
                    ("target", "Target (recipient of social or targeted action)"),
                    ("location", "Location (challenge's room)"),
                ],
                default="self",
                max_length=20,
            ),
        ),
    ]
