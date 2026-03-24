# Hand-authored migration: add NaturalKeyMixin support and make consequence_pool nullable.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("actions", "0004_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="actiontemplate",
            name="consequence_pool",
            field=models.ForeignKey(
                blank=True,
                help_text="Consequence pool for the main resolution step. Null = check-only action.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="action_templates",
                to="actions.consequencepool",
            ),
        ),
    ]
