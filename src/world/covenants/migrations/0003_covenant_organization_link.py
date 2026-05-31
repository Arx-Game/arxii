# Generated manually for Covenant ↔ Organization linkage.
# Pre-launch: no existing Covenant rows. Adds organization as NOT NULL
# OneToOneField. Covenant.save() always populates it before super().save(),
# so the DB never sees a null. bulk_create on Covenant is therefore
# unsafe and discouraged.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("covenants", "0002_initial"),
        ("societies", "0003_create_legend_views"),
    ]

    operations = [
        migrations.AddField(
            model_name="covenant",
            name="organization",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="covenant",
                to="societies.organization",
            ),
        ),
    ]
