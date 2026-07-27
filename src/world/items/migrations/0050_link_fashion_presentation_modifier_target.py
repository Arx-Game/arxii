"""Link Fashion Presentation CheckType to its ModifierTarget (#2758)."""

from django.db import migrations


def link_fashion_presentation_modifier_target(apps, schema_editor):
    """Set ModifierTarget.target_check_type for the Fashion Presentation check.

    The CheckType is content-repo-owned; this migration no-ops when either row
    is missing (e.g. a fresh env without the content repo loaded).
    """
    CheckType = apps.get_model("checks", "CheckType")
    ModifierTarget = apps.get_model("mechanics", "ModifierTarget")

    try:
        check_type = CheckType.objects.get(name="Fashion Presentation")
    except CheckType.DoesNotExist:
        return
    try:
        target = ModifierTarget.objects.get(name="Fashion Presentation")
    except ModifierTarget.DoesNotExist:
        return
    target.target_check_type = check_type
    target.save(update_fields=["target_check_type"])


class Migration(migrations.Migration):
    dependencies = [
        ("items", "0049_alter_equippeditem_character_delete_currencybalance"),
        ("checks", "0001_initial"),
        ("mechanics", "0002_initial"),
    ]
    operations = [
        migrations.RunPython(
            link_fashion_presentation_modifier_target,
            migrations.RunPython.noop,
        ),
    ]
