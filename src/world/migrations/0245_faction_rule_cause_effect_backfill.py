"""Data only (#4415): carry ``FactionRule.suppresses_cause`` onto ``cause_effect``.

Faction rules are authored content (ADR-0237), so this is the *restructure* disposition:
every rule with ``suppresses_cause`` set gets ``cause_effect = "suppress"`` before the next
migration drops the old column. Rules without it keep the default ``"none"``.

Reverse: ``suppresses_cause`` is set back from ``cause_effect == "suppress"``. A rule that
was given ``"provoke"`` after the forward run has no old-schema meaning and reverses to
``suppresses_cause = False``.
"""

from django.db import migrations

_SUPPRESS = "suppress"


def forward(apps, schema_editor):
    FactionRule = apps.get_model("arxii", "FactionRule")
    FactionRule.objects.filter(suppresses_cause=True).update(cause_effect=_SUPPRESS)


def backward(apps, schema_editor):
    FactionRule = apps.get_model("arxii", "FactionRule")
    FactionRule.objects.filter(cause_effect=_SUPPRESS).update(suppresses_cause=True)


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0244_standoff_slice4_causes"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
