"""Tests for migration 0207's rewrite_parked_rows RunPython (#3559).

Deliberate discard of the PENDING_GM_REVIEW state: parked crits (a completion
with an authored outcome_tier) become their tier's SUCCESS/FAILURE, forced
reviews (a completion with no outcome_tier) are deleted and their beat resets
to UNSATISFIED, and any orphan beat left holding the value with no completion
at all resets too.

Uses django.apps.apps directly against the real, current model classes (the
enum removal is the only schema change here and rows are rewritten by pk), per
the running-tests convention for this repo (no MigrationExecutor precedent
exists in the test suite for a data-only RunPython).
"""

import importlib

from django.apps import apps as django_apps
from evennia.utils.test_resources import EvenniaTestCase

from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.factories import BeatCompletionFactory, BeatFactory
from world.stories.models import Beat, BeatCompletion
from world.traits.factories import CheckOutcomeFactory

_migration = importlib.import_module(
    "world.migrations.0207_alter_beat_outcome_alter_beatcompletion_outcome_and_more"
)


class RewriteParkedRowsTests(EvenniaTestCase):
    """world.migrations.0207_....rewrite_parked_rows"""

    def _run(self):
        _migration.rewrite_parked_rows(django_apps, None)
        # The RunPython's own Beat/BeatCompletion.objects.filter(...).update(...)
        # calls are correct against the DB (a real `migrate` run has no live
        # instances to go stale), but this test builds its rows via factories
        # first, so both classes' idmapper identity-map caches hold pre-update
        # instances. Flush them so every read below (including
        # refresh_from_db(), which idmapper's SharedMemoryManager.get() also
        # serves from cache) reflects what the migration actually wrote.
        Beat.flush_instance_cache(force=True)
        BeatCompletion.flush_instance_cache(force=True)

    def test_parked_crit_with_tier_becomes_success_and_beat_follows(self):
        """A parked completion with an authored tier resolves by the tier's
        polarity (positive -> SUCCESS, negative -> FAILURE), and the beat
        follows the completion it owns."""
        win_tier = CheckOutcomeFactory(success_level=3)
        fail_tier = CheckOutcomeFactory(success_level=-2)

        win_beat = BeatFactory(predicate_type=BeatPredicateType.OUTCOME_TIER)
        Beat.objects.filter(pk=win_beat.pk).update(outcome="pending_gm_review")
        win_completion = BeatCompletionFactory(
            beat=win_beat, outcome="pending_gm_review", outcome_tier=win_tier
        )

        fail_beat = BeatFactory(predicate_type=BeatPredicateType.OUTCOME_TIER)
        Beat.objects.filter(pk=fail_beat.pk).update(outcome="pending_gm_review")
        fail_completion = BeatCompletionFactory(
            beat=fail_beat, outcome="pending_gm_review", outcome_tier=fail_tier
        )

        self._run()

        win_completion.refresh_from_db()
        win_beat.refresh_from_db()
        assert win_completion.outcome == BeatOutcome.SUCCESS
        assert win_beat.outcome == BeatOutcome.SUCCESS

        fail_completion.refresh_from_db()
        fail_beat.refresh_from_db()
        assert fail_completion.outcome == BeatOutcome.FAILURE
        assert fail_beat.outcome == BeatOutcome.FAILURE

    def test_parked_forced_review_without_tier_is_deleted_and_beat_reset(self):
        """A parked completion with no outcome_tier (the old forced-review
        path) is deleted outright, and its beat resets to UNSATISFIED."""
        beat = BeatFactory(predicate_type=BeatPredicateType.OUTCOME_TIER)
        Beat.objects.filter(pk=beat.pk).update(outcome="pending_gm_review")
        completion = BeatCompletionFactory(
            beat=beat, outcome="pending_gm_review", outcome_tier=None
        )
        completion_pk = completion.pk

        self._run()

        assert not BeatCompletion.objects.filter(pk=completion_pk).exists()
        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.UNSATISFIED

    def test_orphan_beat_outcome_resets(self):
        """A beat holding the value with no completion row at all resets too
        (the catch-all pass at the end of the RunPython)."""
        beat = BeatFactory(predicate_type=BeatPredicateType.OUTCOME_TIER)
        Beat.objects.filter(pk=beat.pk).update(outcome="pending_gm_review")

        self._run()

        beat.refresh_from_db()
        assert beat.outcome == BeatOutcome.UNSATISFIED
