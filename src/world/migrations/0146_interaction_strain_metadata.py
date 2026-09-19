from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("arxii", "0145_causal_recognition_3914")]

    operations = [
        migrations.AddField(
            model_name="interaction",
            name="strain_effective",
            field=models.PositiveIntegerField(
                default=0, help_text="Strain actually paid after non-lethal resource clamping."
            ),
        ),
        migrations.AddField(
            model_name="interaction",
            name="strain_power_bonus",
            field=models.PositiveIntegerField(
                default=0, help_text="One-time power bonus derived from effective strain."
            ),
        ),
    ]
