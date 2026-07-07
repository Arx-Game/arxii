from django.test import TestCase

from world.stories.exceptions import (
    AmbiguousTransitionError,
    BeatNotResolvableError,
    NoEligibleTransitionError,
    ProgressionRequirementNotMetError,
    StoryError,
)


class StoryExceptionTests(TestCase):
    def test_base_story_error_has_user_message(self) -> None:
        exc = StoryError("internal details")
        self.assertEqual(exc.user_message, "A story system error occurred.")

    def test_beat_not_resolvable_safe_message(self) -> None:
        exc = BeatNotResolvableError("internal: weird state")
        self.assertEqual(
            exc.user_message,
            "This beat cannot be resolved in its current state.",
        )

    def test_no_eligible_transition_safe_message(self) -> None:
        exc = NoEligibleTransitionError()
        self.assertIn("no transition", exc.user_message.lower())

    def test_ambiguous_transition_safe_message(self) -> None:
        exc = AmbiguousTransitionError()
        self.assertIn("multiple", exc.user_message.lower())

    def test_progression_requirement_not_met_safe_message(self) -> None:
        exc = ProgressionRequirementNotMetError()
        self.assertIn("progression", exc.user_message.lower())

    def test_subclasses_inherit_from_story_error(self) -> None:
        self.assertTrue(issubclass(BeatNotResolvableError, StoryError))
        self.assertTrue(issubclass(NoEligibleTransitionError, StoryError))
        self.assertTrue(issubclass(AmbiguousTransitionError, StoryError))
        self.assertTrue(issubclass(ProgressionRequirementNotMetError, StoryError))

    def test_user_message_does_not_leak_args(self) -> None:
        """Critical: passing internal details as args must not leak to user_message."""
        exc = BeatNotResolvableError("DB error: column 'foo' not found")
        self.assertNotIn("foo", exc.user_message)
        self.assertNotIn("DB", exc.user_message)

    def test_crossover_errors_have_safe_messages(self) -> None:
        """Crossover errors must not leak PKs or status values (#2002)."""
        from world.stories.exceptions import (
            CrossoverAuthorityError,
            CrossoverError,
            CrossoverStateError,
        )

        self.assertTrue(issubclass(CrossoverError, StoryError))
        self.assertTrue(issubclass(CrossoverAuthorityError, CrossoverError))
        self.assertTrue(issubclass(CrossoverStateError, CrossoverError))
        # State error with internal details must not leak them.
        exc = CrossoverStateError("CrossoverInvite 42 is not PENDING (status='accepted')")
        self.assertNotIn("42", exc.user_message)
        self.assertNotIn("PENDING", exc.user_message)
        self.assertNotIn("accepted", exc.user_message)
        # Authority error must not leak account/story details.
        exc = CrossoverAuthorityError("from_gm.account_id=5 != withdrawing_account.id=7")
        self.assertNotIn("5", exc.user_message)
        self.assertNotIn("7", exc.user_message)
