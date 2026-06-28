from unittest.mock import MagicMock, patch

from django.test import TestCase


class ActionTemplateEntryFlourishFieldTest(TestCase):
    def test_entrance_template_grants_entry_flourish(self):
        from world.checks.factories import create_social_action_templates

        templates = create_social_action_templates()
        entrance = next(t for t in templates if t.name == "Entrance")
        self.assertTrue(entrance.grants_entry_flourish)

    def test_other_social_templates_do_not_grant_flourish(self):
        from world.checks.factories import create_social_action_templates

        templates = create_social_action_templates()
        for t in templates:
            if t.name != "Entrance":
                self.assertFalse(t.grants_entry_flourish, f"{t.name} should not grant flourish")

    def test_field_defaults_false(self):
        from actions.factories import ActionTemplateFactory

        template = ActionTemplateFactory()
        self.assertFalse(template.grants_entry_flourish)


class EntranceActionDispatchTest(TestCase):
    """Tests that EntranceAction dispatches maybe_create_entry_flourish_offer correctly."""

    def _make_actor(self):
        """Return a stub actor for dispatch tests."""
        from evennia_extensions.factories import ObjectDBFactory

        return ObjectDBFactory(db_key="DispatchTestActor")

    def _make_entrance_template(self, grants_entry_flourish: bool):
        """Create and return an ActionTemplate for Entrance."""
        from actions.factories import ActionTemplateFactory

        return ActionTemplateFactory(
            name="Entrance",
            grants_entry_flourish=grants_entry_flourish,
        )

    def _location_patch(self, actor: object, fake_location: object):
        """Return a patch.object context that overrides actor.location with fake_location."""
        return patch.object(
            type(actor),
            "location",
            new_callable=lambda: property(lambda _self: fake_location),
        )

    def _resolution(self, *, success_level: int):
        """Build the PRODUCTION ``PendingActionResolution`` ``execute()`` actually returns (#1245).

        EntranceAction reads ``result.main_result.check_result.success_level`` — so the test
        must exercise that real path, not a stand-in ``ActionResult(success=...)`` (the prior
        stub bypassed the load-bearing branch). Pass ``success_level=0`` for a failed check.
        """
        from actions.types import PendingActionResolution, StepResult
        from world.checks.types import CheckResult

        outcome = MagicMock()
        outcome.success_level = success_level
        check_result = CheckResult(
            check_type=MagicMock(),
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        step = StepResult(step_label="main", check_result=check_result, consequence_id=None)
        return PendingActionResolution(
            template_id=0,
            character_id=0,
            target_difficulty=0,
            resolution_context_data={},
            current_phase="complete",
            main_result=step,
        )

    def test_success_creates_offer_for_actor_and_scene(self):
        """On a successful Entrance with grants_entry_flourish=True, the offer is created."""
        from actions.definitions.social import EntranceAction
        from world.scenes.factories import SceneFactory

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=True)

        scene = SceneFactory()
        fake_location = MagicMock()
        fake_location.active_scene = scene
        success_result = self._resolution(success_level=1)

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=success_result,
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_called_once_with(actor, scene)

    def test_failure_does_not_create_offer(self):
        """On a failed Entrance, no offer is created even if grants_entry_flourish=True."""
        from actions.definitions.social import EntranceAction
        from world.scenes.factories import SceneFactory

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=True)

        scene = SceneFactory()
        fake_location = MagicMock()
        fake_location.active_scene = scene
        failure_result = self._resolution(success_level=0)

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=failure_result,
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_not_called()

    def test_success_without_grants_entry_flourish_does_not_create_offer(self):
        """Successful Entrance on a template without grants_entry_flourish creates no offer."""
        from actions.definitions.social import EntranceAction
        from world.scenes.factories import SceneFactory

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=False)

        scene = SceneFactory()
        fake_location = MagicMock()
        fake_location.active_scene = scene
        success_result = self._resolution(success_level=1)

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=success_result,
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_not_called()

    def test_paused_resolution_no_main_creates_no_offer(self):
        """A paused resolution (``main_result is None``) hasn't succeeded → no offer (#1245).

        With honest annotations the None-guard is the only success-undetermined path; the prior
        ``ActionResult`` stub couldn't express it.
        """
        from actions.definitions.social import EntranceAction
        from actions.types import PendingActionResolution

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=True)

        fake_location = MagicMock()
        fake_location.active_scene = None
        paused = PendingActionResolution(
            template_id=0,
            character_id=0,
            target_difficulty=0,
            resolution_context_data={},
            current_phase="awaiting_confirmation",
            main_result=None,
        )

        with (
            patch("actions.services.start_action_resolution", return_value=paused),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_not_called()
