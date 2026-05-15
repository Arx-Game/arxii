"""Data migration — RoomResonance tag rows to LocationStatModifier cascade rows.

Each existing RoomResonance (room_aura_profile, resonance) tuple maps to a
LocationStatModifier with:
  - parent_type="room"
  - room_profile = the aura_profile's room_profile
  - key_type="resonance"
  - resonance = the tagged resonance
  - source = "tag_room_resonance" (matches ROOM_RESONANCE_TAG_SOURCE in services)
  - value = 100 (RESONANCE_DEFAULT_MAGNITUDE)
  - change_per_day = 0 (permanent)
  - applied_at = row.set_at if available

Idempotent via get_or_create matching on the lookup keys above. The set_by
audit field is dropped in the merge — staff/player attribution lives in the
source field (free-text) going forward; pre-existing rows lose their set_by.

One-way migration: reverse raises RuntimeError. Old RoomResonance rows are
not deleted here; Task 15 drops the RoomResonance model entirely once all
consumers are migrated.
"""

from __future__ import annotations

from django.db import migrations
from django.utils import timezone

_RESONANCE_DEFAULT_MAGNITUDE = 100


def migrate_roomresonance_to_cascade(apps, schema_editor):  # type: ignore[no-untyped-def]
    RoomResonance = apps.get_model("magic", "RoomResonance")
    LocationStatModifier = apps.get_model("locations", "LocationStatModifier")

    for row in RoomResonance.objects.select_related("room_aura_profile").all():
        profile_id = row.room_aura_profile.room_profile_id
        LocationStatModifier.objects.get_or_create(
            parent_type="room",
            room_profile_id=profile_id,
            key_type="resonance",
            resonance_id=row.resonance_id,
            source="tag_room_resonance",
            defaults={
                "stat_key": "",
                "value": _RESONANCE_DEFAULT_MAGNITUDE,
                "change_per_day": 0,
                "applied_at": row.set_at or timezone.now(),
            },
        )


def reverse_unsupported(apps, schema_editor):  # type: ignore[no-untyped-def]
    msg = "RoomResonance → cascade migration is one-way."
    raise RuntimeError(msg)


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0057_remove_resonancegrant_res_grant_residence_shape_and_more"),
        (
            "locations",
            "0005_remove_locationstatoverride_unique_override_per_area_stat_and_more",
        ),
    ]
    operations = [
        migrations.RunPython(migrate_roomresonance_to_cascade, reverse_unsupported),
    ]
