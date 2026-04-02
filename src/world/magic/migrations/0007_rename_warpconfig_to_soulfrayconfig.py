from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0006_alter_mishappooltier_id_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="WarpConfig",
            new_name="SoulfrayConfig",
        ),
        migrations.RenameField(
            model_name="soulfrayconfig",
            old_name="warp_threshold_ratio",
            new_name="soulfray_threshold_ratio",
        ),
        migrations.AlterModelOptions(
            name="soulfrayconfig",
            options={
                "verbose_name": "Soulfray Configuration",
                "verbose_name_plural": "Soulfray Configurations",
            },
        ),
        migrations.AlterField(
            model_name="soulfrayconfig",
            name="soulfray_threshold_ratio",
            field=models.DecimalField(
                decimal_places=2,
                help_text=(
                    "Anima ratio (current/max) below which technique use "
                    "accumulates Soulfray severity. E.g., 0.30 = below 30%%."
                ),
                max_digits=3,
            ),
        ),
        migrations.AlterField(
            model_name="soulfrayconfig",
            name="resilience_check_type",
            field=models.ForeignKey(
                help_text="Check type for Soulfray resilience (e.g., magical endurance).",
                on_delete=django.db.models.deletion.PROTECT,
                to="checks.checktype",
            ),
        ),
        migrations.AlterField(
            model_name="techniqueoutcomemodifier",
            name="modifier_value",
            field=models.IntegerField(
                help_text=(
                    "Signed modifier applied to the Soulfray resilience check. Negative = penalty."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="auderethreshold",
            name="minimum_warp_stage",
            field=models.ForeignKey(
                help_text="Soulfray must be at this stage or higher.",
                on_delete=django.db.models.deletion.PROTECT,
                to="conditions.conditionstage",
            ),
        ),
        migrations.AlterField(
            model_name="auderethreshold",
            name="warp_multiplier",
            field=models.PositiveIntegerField(
                default=2,
                help_text=(
                    "Soulfray severity increment multiplier during Audere (deprecated field name)."
                ),
            ),
        ),
    ]
