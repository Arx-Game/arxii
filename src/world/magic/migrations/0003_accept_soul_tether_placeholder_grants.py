"""Placeholder PathRitualGrants for accept_soul_tether (preserves visibility).

Ported from main's original 0052 after the 2026-05-24 migration rebuild.
This migration grants accept_soul_tether to every Path so that
reconcile_ritual_knowledge() (called at finalize_character time) will
create knowledge rows for all new characters. Idempotent via get_or_create
and silently skips when accept_soul_tether doesn't yet exist in this DB
(e.g. before wire_soul_tether_content() has been called in tests).
"""

from django.db import migrations


def grant_accept_soul_tether_to_all_paths(apps, schema_editor):
    Ritual = apps.get_model("magic", "Ritual")
    Path = apps.get_model("classes", "Path")
    PathRitualGrant = apps.get_model("magic", "PathRitualGrant")

    try:
        ritual = Ritual.objects.get(name="accept_soul_tether")
    except Ritual.DoesNotExist:
        return

    for path in Path.objects.all():
        PathRitualGrant.objects.get_or_create(path=path, ritual=ritual)


def remove_accept_soul_tether_grants(apps, schema_editor):
    Ritual = apps.get_model("magic", "Ritual")
    PathRitualGrant = apps.get_model("magic", "PathRitualGrant")

    try:
        ritual = Ritual.objects.get(name="accept_soul_tether")
    except Ritual.DoesNotExist:
        return
    PathRitualGrant.objects.filter(ritual=ritual).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("magic", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(
            grant_accept_soul_tether_to_all_paths,
            remove_accept_soul_tether_grants,
        ),
    ]
