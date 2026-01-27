# Refactor Affinity and Resonance to use ModifierType

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Replace Affinity and Resonance FKs with ModifierType FKs.

    Affinity and Resonance models are deleted. Their functionality is now
    provided by ModifierType entries with category='affinity' or 'resonance'.
    """

    dependencies = [
        ("magic", "0010_clear_affinity_resonance_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="power",
            name="affinity",
            field=models.ForeignKey(
                help_text="The affinity of this power (must be category='affinity').",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="powers",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.AlterField(
            model_name="gift",
            name="affinity",
            field=models.ForeignKey(
                help_text="The primary affinity of this gift (must be category='affinity').",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="gifts",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.RemoveField(
            model_name="resonance",
            name="default_affinity",
        ),
        migrations.AlterField(
            model_name="threadtype",
            name="grants_resonance",
            field=models.ForeignKey(
                blank=True,
                help_text="Resonance granted by this thread type (must be category='resonance').",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="thread_type_grants",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.AlterField(
            model_name="characterresonance",
            name="resonance",
            field=models.ForeignKey(
                help_text="The resonance type (must be category='resonance').",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="character_resonance_attachments",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.AlterField(
            model_name="threadresonance",
            name="resonance",
            field=models.ForeignKey(
                help_text="The resonance type (must be category='resonance').",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="thread_resonance_attachments",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.AlterField(
            model_name="gift",
            name="resonances",
            field=models.ManyToManyField(
                blank=True,
                help_text="Resonances associated with this gift (must be category='resonance').",
                related_name="gift_resonances",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.AlterField(
            model_name="power",
            name="resonances",
            field=models.ManyToManyField(
                blank=True,
                help_text="Resonances that boost this power (must be category='resonance').",
                related_name="power_resonances",
                to="mechanics.modifiertype",
            ),
        ),
        migrations.DeleteModel(
            name="Affinity",
        ),
        migrations.DeleteModel(
            name="Resonance",
        ),
    ]
