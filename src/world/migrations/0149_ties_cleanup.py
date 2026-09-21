"""Data-only cleanup ahead of the ties redesign (#3957).

The schema migration that follows (0150_ties_redrawn) restructures
RelationshipTier (per-track tiers become one global ladder),
RelationshipCapstone (writeup capstones become tier-advance receipts), and the
Thread anchors those two models fed. None of that is authored content (ADR-0237):
RelationshipTier rows are seed-owned (the ``relationship_scale`` cluster
re-creates them against the new shape) and RelationshipCapstone/anchored Thread
rows are alpha play state, deliberately discarded rather than migrated forward.

Deletes dependents first where a PROTECT FK would otherwise block a Thread
delete, and nulls SecretGrievance.capstone before 0150 drops that column.

0150 also drops HybridRelationshipType and HybridRequirement outright (DeleteModel,
no RunPython here) - a deliberate discard, not a restructure (ADR-0237): no seed
ever wrote either table and no staff-authoring path exists for them (``grep -rn
HybridRelationshipType src/world/seeds`` finds nothing), so both are empty in
production by construction.
"""

from django.db import migrations

_STALE_THREAD_KINDS = ("RELATIONSHIP_TRACK", "RELATIONSHIP_CAPSTONE")


def cleanup_relationships_play_state(apps, schema_editor):
    """Discard the pre-redesign relationship play state (#3957)."""
    RelationshipTier = apps.get_model("arxii", "RelationshipTier")
    RelationshipCapstone = apps.get_model("arxii", "RelationshipCapstone")
    Thread = apps.get_model("arxii", "Thread")
    ThreadLevelUnlock = apps.get_model("arxii", "ThreadLevelUnlock")
    CombatPullResolvedEffect = apps.get_model("arxii", "CombatPullResolvedEffect")
    TreatmentAttempt = apps.get_model("arxii", "TreatmentAttempt")
    SceneActionRequest = apps.get_model("arxii", "SceneActionRequest")
    SecretGrievance = apps.get_model("arxii", "SecretGrievance")

    stale_threads = Thread.objects.filter(target_kind__in=_STALE_THREAD_KINDS)
    stale_thread_ids = list(stale_threads.values_list("pk", flat=True))
    if stale_thread_ids:
        # PROTECT FKs onto Thread: clear/delete dependents before the Thread rows go.
        # CrossingChoice/PendingCrossingOffer (CASCADE) and the M2M relations
        # (JournalEntry.related_threads, ActionPullDeclaration.threads,
        # CombatPull.threads) need no explicit handling - Django's own delete
        # collector clears those automatically.
        ThreadLevelUnlock.objects.filter(thread_id__in=stale_thread_ids).delete()
        CombatPullResolvedEffect.objects.filter(source_thread_id__in=stale_thread_ids).delete()
        TreatmentAttempt.objects.filter(thread_used_id__in=stale_thread_ids).update(
            thread_used=None
        )
        SceneActionRequest.objects.filter(thread_used_id__in=stale_thread_ids).update(
            thread_used=None
        )
        stale_threads.delete()

    # SecretGrievance.capstone (SET_NULL) is cleared automatically by the delete
    # below too, but 0150 drops the column outright, so null it explicitly first.
    SecretGrievance.objects.exclude(capstone__isnull=True).update(capstone=None)
    RelationshipCapstone.objects.all().delete()
    RelationshipTier.objects.all().delete()


def noop_reverse(apps, schema_editor):
    """Irreversible discard; nothing to restore."""


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0148_journal_about_consent_visit"),
    ]

    operations = [
        migrations.RunPython(cleanup_relationships_play_state, noop_reverse),
    ]
