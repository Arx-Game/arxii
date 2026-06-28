from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.tests.resolution_helpers import make_paused_resolution, make_resolution


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

    def test_success_creates_offer_and_prompts_via_result_message(self):
        """On a successful Entrance with grants_entry_flourish=True, the offer is created.

        ``execute()`` returns a real ``ActionResult`` whose ``message`` carries the
        flourish prompt — the command/web both surface it through the normal result
        channel (#1245).
        """
        from actions.definitions.social import EntranceAction
        from actions.types import ActionResult
        from world.scenes.factories import SceneFactory

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=True)

        scene = SceneFactory()
        fake_location = MagicMock()
        fake_location.active_scene = scene

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=make_resolution(1),
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            result = EntranceAction().execute(actor, context)

        mock_offer.assert_called_once_with(actor, scene)
        # A genuine ActionResult (honest annotation) carrying the flourish prompt.
        self.assertIsInstance(result, ActionResult)
        self.assertTrue(result.success)
        self.assertIn("flourish", (result.message or "").lower())

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

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=make_resolution(0),
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_not_called()

    def test_paused_resolution_no_main_creates_no_offer(self):
        """A paused resolution (main step not yet rolled) creates no offer.

        ``main_result is None`` is not a success — this is the branch the old
        ``ActionResult(success=...)`` stub couldn't express (#1245).
        """
        from actions.definitions.social import EntranceAction
        from world.scenes.factories import SceneFactory

        actor = self._make_actor()
        context = MagicMock()
        self._make_entrance_template(grants_entry_flourish=True)

        scene = SceneFactory()
        fake_location = MagicMock()
        fake_location.active_scene = scene

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=make_paused_resolution(),
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

        with (
            patch(
                "actions.services.start_action_resolution",
                return_value=make_resolution(1),
            ),
            self._location_patch(actor, fake_location),
            patch(
                "world.magic.entry_flourish.maybe_create_entry_flourish_offer",
            ) as mock_offer,
        ):
            EntranceAction().execute(actor, context)

        mock_offer.assert_not_called()
