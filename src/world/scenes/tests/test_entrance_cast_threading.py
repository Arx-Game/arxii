"""Tests for the ``originated_as_entrance`` marker threaded through the standalone-cast

pipeline (#2183, Task 1). Nothing consumes the flag yet — these tests only verify it is
stamped onto the PENDING ``SceneActionRequest`` row created by a consent-gated benign cast,
and that it defaults to False when the caller doesn't pass it.
"""

from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import request_technique_cast
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    attach_behavior_altering_condition,
    grant_technique,
    make_benign_castable_technique,
)


class TestEntranceCastThreading(CastScenarioMixin):
    """originated_as_entrance is threaded from request_technique_cast to the PENDING request."""

    def test_benign_consent_pending_request_stamped(self) -> None:
        """A consent-gated benign cast called with originated_as_entrance=True stamps it."""
        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
            originated_as_entrance=True,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        self.assertTrue(cast.request.originated_as_entrance)

    def test_default_is_false(self) -> None:
        """Without the kwarg, originated_as_entrance defaults to False."""
        technique = make_benign_castable_technique()
        attach_behavior_altering_condition(technique)
        grant_technique(self.caster, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.caster,
            target_persona=self.target,
            technique=technique,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        self.assertFalse(cast.request.originated_as_entrance)
