"""Data migration: map legacy CharacterVitals.status -> life_state.

Runs BEFORE the column-removal migration so the historical `status` field is
still readable here. Only sets the mortality marker (life_state); incapacitation
and dying are handled at runtime by the conditions system going forward, so this
migration does not apply any conditions.
"""

from django.db import migrations


def forward(apps, schema_editor) -> None:
    CharacterVitals = apps.get_model("vitals", "CharacterVitals")
    for v in CharacterVitals.objects.all().iterator():
        # status == "dead" -> dead; every other legacy status -> alive.
        v.life_state = "dead" if v.status == "dead" else "alive"  # noqa: STRING_LITERAL — historical literal values; data migrations must not import live constants
        v.save(update_fields=["life_state"])


class Migration(migrations.Migration):
    dependencies = [
        ("vitals", "0002_charactervitals_life_state"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
