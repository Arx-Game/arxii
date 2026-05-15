"""Verifies the partial unique constraint on Beat (episode, predicate_type, req_cond_template)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.stories.constants import BeatPredicateType
from world.stories.factories import BeatFactory, EpisodeFactory


class BeatUniqueConstraintTests(TestCase):
    def test_unique_per_episode_predicate_type_required_template(self) -> None:
        """Verify that duplicate (episode, predicate_type, required_condition_template)
        raises IntegrityError."""
        episode = EpisodeFactory()
        burning = ConditionTemplateFactory(name="Burning T5 Unique")
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=burning,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            BeatFactory(
                episode=episode,
                predicate_type=BeatPredicateType.CONDITION_HELD,
                required_condition_template=burning,
            )

    def test_different_required_templates_allowed_on_same_episode(self) -> None:
        """Verify different required_condition_template values don't collide on same
        episode."""
        episode = EpisodeFactory()
        burning = ConditionTemplateFactory(name="Burning T5 Diff Tmpl A")
        singed = ConditionTemplateFactory(name="Singed T5 Diff Tmpl B")
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=burning,
        )
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=singed,
        )
        # No assertion needed — if the constraint blocks this, an IntegrityError fires.

    def test_partial_constraint_allows_multiple_null_required_template(self) -> None:
        """GM_MARKED beats have required_condition_template=NULL; constraint must
        be partial so multiple GM_MARKED Beats on one episode don't collide."""
        episode = EpisodeFactory()
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_condition_template=None,
        )
        # Second GM_MARKED beat on same episode must NOT raise.
        BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            required_condition_template=None,
        )
