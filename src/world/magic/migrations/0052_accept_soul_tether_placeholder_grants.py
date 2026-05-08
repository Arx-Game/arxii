"""Placeholder PathRitualGrants for accept_soul_tether (preserves visibility).

Before CharacterRitualKnowledge gating shipped (Phase 7), the accept_soul_tether
Ritual was visible to all characters. The RitualViewSet now filters by
CharacterRitualKnowledge rows, so any character without a row cannot see it.

This migration grants accept_soul_tether to every Path so that reconcile_ritual_knowledge()
(called at finalize_character time) will create knowledge rows for all new characters.
Existing characters need a one-time reconciliation pass (Phase 10 or admin task).

The grants are silently skipped when accept_soul_tether does not yet exist in this DB
(e.g. fresh test databases before wire_soul_tether_content() has been called).
"""

from django.db import migrations


def grant_accept_soul_tether_to_all_paths(apps, schema_editor):
    Ritual = apps.get_model("magic", "Ritual")
    Path = apps.get_model("classes", "Path")
    PathRitualGrant = apps.get_model("magic", "PathRitualGrant")

    try:
        ritual = Ritual.objects.get(name="accept_soul_tether")
    except Ritual.DoesNotExist:
        # accept_soul_tether not yet seeded in this DB — skip silently.
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
        ("magic", "0051_alter_animaritualperformance_ritual_and_more"),
        ("classes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            grant_accept_soul_tether_to_all_paths,
            remove_accept_soul_tether_grants,
        ),
    ]
