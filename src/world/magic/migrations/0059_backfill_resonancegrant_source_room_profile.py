"""Data migration — backfill ResonanceGrant.source_room_profile from the legacy
source_room_aura_profile FK.

For every ResonanceGrant row whose source_room_aura_profile IS NOT NULL and
source_room_profile IS NULL, copy source_room_aura_profile.room_profile_id
into source_room_profile_id. Idempotent — re-running skips rows already
backfilled.

After this migration, Task 14 drops source_room_aura_profile entirely and
tightens the residence CheckConstraint to require source_room_profile.
"""

from __future__ import annotations

from django.db import migrations


def backfill_source_room_profile(apps, schema_editor):  # type: ignore[no-untyped-def]
    ResonanceGrant = apps.get_model("magic", "ResonanceGrant")
    rows = ResonanceGrant.objects.filter(
        source_room_aura_profile__isnull=False,
        source_room_profile__isnull=True,
    ).select_related("source_room_aura_profile")
    for row in rows:
        row.source_room_profile_id = row.source_room_aura_profile.room_profile_id
        row.save(update_fields=["source_room_profile"])


def reverse_unsupported(apps, schema_editor):  # type: ignore[no-untyped-def]
    msg = "ResonanceGrant audit FK backfill is one-way."
    raise RuntimeError(msg)


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0058_migrate_roomresonance_to_cascade"),
    ]
    operations = [
        migrations.RunPython(backfill_source_room_profile, reverse_unsupported),
    ]
