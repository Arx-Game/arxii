"""Data only (#4122): point the Soulfray config at the Soulfray condition template.

Until now the game found Soulfray by matching a condition template's name. This sets
``SoulfrayConfig.condition`` on the existing config row to the template whose name
matches, ignoring case, the way the old lookup did. It is the last place that name is
matched. Nothing is dropped or rewritten: a config row that already has a condition is
left alone, and with no config row or no matching template the field stays unset, which
the Required content dashboard flags.

Reverse: clears the field, which is the state the previous schema expects.
"""

from django.db import migrations

_SOULFRAY_NAME = "Soulfray"


def forward(apps, schema_editor):
    SoulfrayConfig = apps.get_model("arxii", "SoulfrayConfig")
    ConditionTemplate = apps.get_model("arxii", "ConditionTemplate")

    template = ConditionTemplate.objects.filter(name__iexact=_SOULFRAY_NAME).order_by("pk").first()
    if template is None:
        return
    SoulfrayConfig.objects.filter(condition__isnull=True).update(condition=template)


def reverse(apps, schema_editor):
    SoulfrayConfig = apps.get_model("arxii", "SoulfrayConfig")
    SoulfrayConfig.objects.update(condition=None)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0235_soulfray_config_condition"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
