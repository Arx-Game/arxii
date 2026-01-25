# Generated manually to handle data migration
from django.db import migrations, models
import django.db.models.deletion


def fix_dual_fk_data(apps, schema_editor):
    """Set condition=NULL for all rows that have stage set.

    The stage relationship already provides access to the condition
    via stage.condition, so we don't need the redundant FK.
    """
    ConditionCapabilityEffect = apps.get_model("conditions", "ConditionCapabilityEffect")
    ConditionCheckModifier = apps.get_model("conditions", "ConditionCheckModifier")
    ConditionResistanceModifier = apps.get_model("conditions", "ConditionResistanceModifier")
    ConditionDamageOverTime = apps.get_model("conditions", "ConditionDamageOverTime")

    # For each model, set condition=NULL where stage is set
    ConditionCapabilityEffect.objects.filter(stage__isnull=False).update(condition=None)
    ConditionCheckModifier.objects.filter(stage__isnull=False).update(condition=None)
    ConditionResistanceModifier.objects.filter(stage__isnull=False).update(condition=None)
    ConditionDamageOverTime.objects.filter(stage__isnull=False).update(condition=None)


def reverse_fix_dual_fk_data(apps, schema_editor):
    """Reverse: Set condition from stage.condition for all rows that have stage set."""
    ConditionCapabilityEffect = apps.get_model("conditions", "ConditionCapabilityEffect")
    ConditionCheckModifier = apps.get_model("conditions", "ConditionCheckModifier")
    ConditionResistanceModifier = apps.get_model("conditions", "ConditionResistanceModifier")
    ConditionDamageOverTime = apps.get_model("conditions", "ConditionDamageOverTime")

    # For each model, set condition from stage.condition
    for effect in ConditionCapabilityEffect.objects.filter(stage__isnull=False):
        effect.condition = effect.stage.condition
        effect.save()
    for mod in ConditionCheckModifier.objects.filter(stage__isnull=False):
        mod.condition = mod.stage.condition
        mod.save()
    for mod in ConditionResistanceModifier.objects.filter(stage__isnull=False):
        mod.condition = mod.stage.condition
        mod.save()
    for dot in ConditionDamageOverTime.objects.filter(stage__isnull=False):
        dot.condition = dot.stage.condition
        dot.save()


class Migration(migrations.Migration):
    dependencies = [
        ("conditions", "0003_alter_damagetype_resonance"),
    ]

    operations = [
        # Step 1: Remove unique_together constraints that reference slug
        migrations.AlterUniqueTogether(
            name="conditioncapabilityeffect",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="conditioncheckmodifier",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="conditiondamageovertime",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="conditionresistancemodifier",
            unique_together=set(),
        ),
        # Step 2: Remove slug fields
        migrations.RemoveField(
            model_name="capabilitytype",
            name="slug",
        ),
        migrations.RemoveField(
            model_name="checktype",
            name="slug",
        ),
        migrations.RemoveField(
            model_name="conditioncategory",
            name="slug",
        ),
        migrations.RemoveField(
            model_name="conditiontemplate",
            name="slug",
        ),
        migrations.RemoveField(
            model_name="damagetype",
            name="slug",
        ),
        # Step 3: Make condition field nullable on stage-based models
        migrations.AlterField(
            model_name="conditioncapabilityeffect",
            name="condition",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for condition-level effects (all stages)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="capability_effects",
                to="conditions.conditiontemplate",
            ),
        ),
        migrations.AlterField(
            model_name="conditioncapabilityeffect",
            name="stage",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for stage-specific effects",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="capability_effects",
                to="conditions.conditionstage",
            ),
        ),
        migrations.AlterField(
            model_name="conditioncheckmodifier",
            name="condition",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for condition-level effects (all stages)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="check_modifiers",
                to="conditions.conditiontemplate",
            ),
        ),
        migrations.AlterField(
            model_name="conditioncheckmodifier",
            name="stage",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for stage-specific effects",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="check_modifiers",
                to="conditions.conditionstage",
            ),
        ),
        migrations.AlterField(
            model_name="conditiondamageovertime",
            name="condition",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for condition-level effects (all stages)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="damage_over_time",
                to="conditions.conditiontemplate",
            ),
        ),
        migrations.AlterField(
            model_name="conditiondamageovertime",
            name="stage",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for stage-specific effects",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="damage_over_time",
                to="conditions.conditionstage",
            ),
        ),
        migrations.AlterField(
            model_name="conditionresistancemodifier",
            name="condition",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for condition-level effects (all stages)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resistance_modifiers",
                to="conditions.conditiontemplate",
            ),
        ),
        migrations.AlterField(
            model_name="conditionresistancemodifier",
            name="stage",
            field=models.ForeignKey(
                blank=True,
                help_text="Set for stage-specific effects",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="resistance_modifiers",
                to="conditions.conditionstage",
            ),
        ),
        # Step 4: Fix data - set condition=NULL where stage is set
        migrations.RunPython(fix_dual_fk_data, reverse_fix_dual_fk_data),
        # Step 5: Add check constraints and unique constraints
        migrations.AddConstraint(
            model_name="conditioncapabilityeffect",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("condition__isnull", False), ("stage__isnull", True)),
                    models.Q(("condition__isnull", True), ("stage__isnull", False)),
                    _connector="OR",
                ),
                name="capability_effect_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditioncapabilityeffect",
            constraint=models.UniqueConstraint(
                condition=models.Q(("condition__isnull", False)),
                fields=["condition", "capability"],
                name="capability_effect_unique_condition",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditioncapabilityeffect",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stage__isnull", False)),
                fields=["stage", "capability"],
                name="capability_effect_unique_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditioncheckmodifier",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("condition__isnull", False), ("stage__isnull", True)),
                    models.Q(("condition__isnull", True), ("stage__isnull", False)),
                    _connector="OR",
                ),
                name="check_modifier_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditioncheckmodifier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("condition__isnull", False)),
                fields=["condition", "check_type"],
                name="check_modifier_unique_condition",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditioncheckmodifier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stage__isnull", False)),
                fields=["stage", "check_type"],
                name="check_modifier_unique_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditiondamageovertime",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("condition__isnull", False), ("stage__isnull", True)),
                    models.Q(("condition__isnull", True), ("stage__isnull", False)),
                    _connector="OR",
                ),
                name="damage_over_time_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditiondamageovertime",
            constraint=models.UniqueConstraint(
                condition=models.Q(("condition__isnull", False)),
                fields=["condition", "damage_type"],
                name="damage_over_time_unique_condition",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditiondamageovertime",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stage__isnull", False)),
                fields=["stage", "damage_type"],
                name="damage_over_time_unique_stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionresistancemodifier",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(("condition__isnull", False), ("stage__isnull", True)),
                    models.Q(("condition__isnull", True), ("stage__isnull", False)),
                    _connector="OR",
                ),
                name="resistance_modifier_exactly_one_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionresistancemodifier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("condition__isnull", False)),
                fields=["condition", "damage_type"],
                name="resistance_modifier_unique_condition",
            ),
        ),
        migrations.AddConstraint(
            model_name="conditionresistancemodifier",
            constraint=models.UniqueConstraint(
                condition=models.Q(("stage__isnull", False)),
                fields=["stage", "damage_type"],
                name="resistance_modifier_unique_stage",
            ),
        ),
    ]
