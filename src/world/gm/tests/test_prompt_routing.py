"""Event routing to the GM prompt queue (#4101 Task 2): the spec's test seams."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.exceptions import GMPromptError
from world.gm.factories import GMPromptFilterFactory
from world.gm.models import GMPrompt
from world.gm.prompt_services import (
    dismiss_gm_prompt,
    prompt_recipients,
    route_narratable_event,
)
from world.gm.types import NarratableEvent
from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
)
from world.scenes.models import Interaction
from world.scenes.scene_admin_services import finish_scene_full


class RouteNarratableEventTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm = AccountFactory()
        cls.second_gm = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.scene = SceneFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        cls.quiet_scene = SceneFactory()

    def _event(self, scene, kind=GMPromptKind.MIRACLE, **kw):
        return NarratableEvent(kind=kind, scene=scene, character_sheet=self.sheet, **kw)

    def test_event_with_gm_creates_prompt_and_skips_delivery(self):
        deliver = mock.Mock()
        prompts = route_narratable_event(
            self._event(self.scene, room_text="authored"), deliver_unprompted=deliver
        )
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].addressed_to, self.gm)
        self.assertEqual(prompts[0].room_text, "authored")
        self.assertEqual(prompts[0].status, GMPromptStatus.PENDING)
        deliver.assert_not_called()

    def test_no_gm_delivers_as_today_and_creates_nothing(self):
        deliver = mock.Mock()
        prompts = route_narratable_event(self._event(self.quiet_scene), deliver_unprompted=deliver)
        self.assertEqual(prompts, [])
        deliver.assert_called_once()
        self.assertFalse(GMPrompt.objects.filter(scene=self.quiet_scene).exists())

    def test_filtered_out_kind_creates_no_prompt(self):
        muted_scene = SceneFactory()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=muted_scene, account=gm)
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        deliver = mock.Mock()
        self.assertEqual(
            route_narratable_event(self._event(muted_scene), deliver_unprompted=deliver), []
        )
        deliver.assert_called_once()

    def test_mute_is_per_group(self):
        gm = AccountFactory()
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=gm)
        self.assertEqual(prompt_recipients(scene, GMPromptKind.DEATH), [gm])

    def test_two_gms_one_muted(self):
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        SceneGMParticipationFactory(scene=scene, account=self.second_gm)
        GMPromptFilterFactory(account=self.second_gm, group=GMPromptGroup.MIRACLE, enabled=False)
        prompts = route_narratable_event(self._event(scene))
        self.assertEqual([p.addressed_to for p in prompts], [self.gm])

    def test_departed_gm_is_not_prompted(self):
        scene = SceneFactory()
        part = SceneGMParticipationFactory(scene=scene, account=AccountFactory())
        part.left_at = part.joined_at
        part.save()
        self.assertEqual(prompt_recipients(scene, GMPromptKind.DEATH), [])

    def test_explicit_candidates_still_filtered(self):
        gm = AccountFactory()
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.STAKE_OUTCOME, enabled=False)
        self.assertEqual(prompt_recipients(None, GMPromptKind.STAKE_OUTCOME, candidates=[gm]), [])

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_releases_private_default(self, narrate):
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.CROSSING, private_text="vision")
        )[0]
        dismiss_gm_prompt(prompt, resolver=self.gm)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once_with(self.sheet.character, "vision", scene=self.scene)

    def test_finish_scene_releases_pending_private_default(self):
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        route_narratable_event(
            self._event(scene, kind=GMPromptKind.CROSSING, private_text="the vision")
        )
        finish_scene_full(scene)
        prompt = GMPrompt.objects.get(scene=scene)
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertTrue(
            Interaction.objects.filter(
                content="the vision",
                mode=InteractionMode.WHISPER,
                receivers__persona=self.sheet.primary_persona,
            ).exists()
        )

    @mock.patch("world.gm.prompt_services.broadcast_scene_emit")
    def test_room_text_release_on_dismiss(self, broadcast):
        """#4101 fix round 1: the room-text leg also releases on dismiss, against
        the prompt's OWN scene explicitly."""
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.MIRACLE, room_text="a wonder occurs")
        )[0]
        dismiss_gm_prompt(prompt, resolver=self.gm)
        broadcast.assert_called_once_with(self.sheet.character, "a wonder occurs", scene=self.scene)

    def test_release_uses_prompts_own_scene_not_characters_current_location(self):
        """A character who has since moved rooms still gets the room line
        attributed to the ORIGINAL scene (#4101 fix round 1), not whichever
        scene is active wherever they wandered off to. Exercises the real
        (unmocked) ``broadcast_scene_emit``/``create_interaction`` path."""
        from evennia_extensions.factories import RoomProfileFactory

        original_room = RoomProfileFactory().objectdb
        elsewhere_room = RoomProfileFactory().objectdb
        scene = SceneFactory(location=original_room)
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        # A different scene is active wherever the character ends up -- if
        # release re-derived the scene from the character's CURRENT location,
        # the EMIT would land here instead.
        elsewhere_scene = SceneFactory(location=elsewhere_room)

        self.sheet.character.location = original_room
        prompt = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=scene,
                character_sheet=self.sheet,
                room_text="a wonder occurs",
            )
        )[0]

        self.sheet.character.location = elsewhere_room
        dismiss_gm_prompt(prompt, resolver=self.gm)

        self.assertTrue(
            Interaction.objects.filter(
                content="a wonder occurs", mode=InteractionMode.EMIT, scene=scene
            ).exists()
        )
        self.assertFalse(
            Interaction.objects.filter(
                content="a wonder occurs", mode=InteractionMode.EMIT, scene=elsewhere_scene
            ).exists()
        )


class SiblingReleaseTest(TestCase):
    """Release-once-per-event, not once-per-prompt (#4101 fix round 1, critical).

    Uses ``setUp`` rather than ``setUpTestData``: Django deep-copies
    ``setUpTestData`` model instances per test method, so a ``self.gm_a.msg =
    Mock()`` reassignment in one test would land on a throwaway clone, never on
    the idmapper-shared instance ``notify_gm_prompt``'s ``prompt.addressed_to``
    actually resolves -- the two live-push tests below need the real object.
    """

    def setUp(self):
        self.gm_a = AccountFactory()
        self.gm_b = AccountFactory()
        self.sheet = CharacterSheetFactory()
        self.scene = SceneFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm_a)
        SceneGMParticipationFactory(scene=self.scene, account=self.gm_b)

    def _two_gm_prompts(self, **kw):
        prompts = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=self.scene,
                character_sheet=self.sheet,
                **kw,
            )
        )
        by_account = {p.addressed_to_id: p for p in prompts}
        return by_account[self.gm_a.pk], by_account[self.gm_b.pk]

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_a_dismisses_then_scene_end_sends_exactly_once(self, narrate):
        prompt_a, _prompt_b = self._two_gm_prompts(private_text="the vision")
        dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        narrate.assert_not_called()  # gm_b's sibling is still PENDING

        finish_scene_full(self.scene)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=self.scene)

    def test_dismiss_twice_raises(self):
        prompt_a, _prompt_b = self._two_gm_prompts(private_text="the vision")
        dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        with self.assertRaises(GMPromptError):
            dismiss_gm_prompt(prompt_a, resolver=self.gm_a)

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_scene_end_after_dismiss_sends_once(self, narrate):
        """A single-GM event: dismiss releases immediately (last and only
        sibling); a later scene end must not find it PENDING and re-release."""
        solo_scene = SceneFactory()
        SceneGMParticipationFactory(scene=solo_scene, account=self.gm_a)
        [prompt] = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=solo_scene,
                character_sheet=self.sheet,
                private_text="the vision",
            )
        )
        dismiss_gm_prompt(prompt, resolver=self.gm_a)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=solo_scene)

        finish_scene_full(solo_scene)
        narrate.assert_called_once()  # still exactly once

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_skips_release_when_a_sibling_narrated(self, narrate):
        """A GM's own narration of the event replaces the default -- the last
        sibling to dismiss must not also release it."""
        prompt_a, prompt_b = self._two_gm_prompts(private_text="the vision")
        # No narration action exists yet in this task (#4101 wires it in a later
        # task) -- simulate gm_b having narrated by setting the status directly
        # (a plain .save(), not .update() -- GMPrompt is idmapper-shared, so a
        # bare QuerySet.update() is disabled; see core.managers).
        prompt_b.status = GMPromptStatus.NARRATED
        prompt_b.save(update_fields=["status"])
        dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        narrate.assert_not_called()

    def test_live_push_reaches_only_the_addressed_gm(self):
        """``route_narratable_event``'s ``transaction.on_commit`` push (#4101)
        lands each prompt on its OWN addressed GM only -- no cross-talk between
        the two siblings' pushes."""
        self.gm_a.msg = mock.Mock()
        self.gm_b.msg = mock.Mock()
        with self.captureOnCommitCallbacks(execute=True):
            prompt_a, prompt_b = self._two_gm_prompts(room_text="a wonder occurs")

        self.gm_a.msg.assert_called_once()
        self.assertEqual(self.gm_a.msg.call_args.kwargs["gm_prompt"][1]["prompt_id"], prompt_a.pk)
        self.gm_b.msg.assert_called_once()
        self.assertEqual(self.gm_b.msg.call_args.kwargs["gm_prompt"][1]["prompt_id"], prompt_b.pk)

    def test_scene_owner_receives_no_push(self):
        """The scene owner is never addressed_to -- a prompt's live push must
        never reach them, even though they can administer the scene."""
        owner = AccountFactory()
        SceneOwnerParticipationFactory(scene=self.scene, account=owner)
        owner.msg = mock.Mock()
        self.gm_a.msg = mock.Mock()
        with self.captureOnCommitCallbacks(execute=True):
            self._two_gm_prompts(room_text="a wonder occurs")

        self.gm_a.msg.assert_called_once()
        owner.msg.assert_not_called()
