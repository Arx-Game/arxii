"""Event routing to the GM prompt queue (#4101 Task 2): the spec's test seams."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.exceptions import GMPromptError
from world.gm.factories import GMPromptFilterFactory
from world.gm.models import GMPrompt, GMPromptNarration
from world.gm.prompt_services import (
    dismiss_gm_prompt,
    expire_scene_prompts,
    link_prompt_narration,
    prompt_recipients,
    route_narratable_event,
)
from world.gm.types import NarratableEvent
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
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
        """#4101 fix round 2 (ruling R7-2): ``route_narratable_event`` no longer
        takes a ``deliver_unprompted`` callback -- the caller delivers, exactly
        once, based on whether the returned list is empty. This exercises that
        caller-side pattern directly."""
        deliver = mock.Mock()
        prompts = route_narratable_event(self._event(self.scene, room_text="authored"))
        if not prompts:
            deliver()
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].addressed_to, self.gm)
        self.assertEqual(prompts[0].room_text, "authored")
        self.assertEqual(prompts[0].status, GMPromptStatus.PENDING)
        deliver.assert_not_called()

    def test_no_gm_delivers_as_today_and_creates_nothing(self):
        deliver = mock.Mock()
        prompts = route_narratable_event(self._event(self.quiet_scene))
        if not prompts:
            deliver()
        self.assertEqual(prompts, [])
        deliver.assert_called_once()
        self.assertFalse(GMPrompt.objects.filter(scene=self.quiet_scene).exists())

    def test_filtered_out_kind_creates_no_prompt(self):
        muted_scene = SceneFactory()
        gm = AccountFactory()
        SceneGMParticipationFactory(scene=muted_scene, account=gm)
        GMPromptFilterFactory(account=gm, group=GMPromptGroup.MIRACLE, enabled=False)
        deliver = mock.Mock()
        prompts = route_narratable_event(self._event(muted_scene))
        if not prompts:
            deliver()
        self.assertEqual(prompts, [])
        deliver.assert_called_once()

    def test_subjects_own_gm_account_is_excluded_default_goes_out(self):
        """#4101 fix round 2 (ruling R7-1): ``route_narratable_event`` itself
        drops the event's own subject from recipients -- every narratable-event
        source gets this for free now, not just the ones (Crossing, surge,
        ultimate) that used to duplicate the exclusion by hand per fix round 1."""
        own_account = AccountFactory()
        entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=own_account),
            end_date=None,
        )
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=own_account)
        deliver = mock.Mock()

        prompts = route_narratable_event(self._event(scene, room_text="authored"))
        if not prompts:
            deliver()

        self.assertEqual(prompts, [])
        deliver.assert_called_once()
        self.assertFalse(GMPrompt.objects.filter(scene=scene).exists())

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
        """#4101 fix round 2: release is deferred to ``transaction.on_commit``,
        so the triggering call must run inside ``captureOnCommitCallbacks``."""
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.CROSSING, private_text="vision")
        )[0]
        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
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

    def test_finish_scene_releases_pending_room_text_default(self):
        """The room-text leg also releases through the real ``finish_scene_full``
        scene-end path (#4101 fix round 2), not just a plain dismiss."""
        scene = SceneFactory()
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        route_narratable_event(
            self._event(scene, kind=GMPromptKind.MIRACLE, room_text="a wonder occurs")
        )
        with self.captureOnCommitCallbacks(execute=True):
            finish_scene_full(scene)
        prompt = GMPrompt.objects.get(scene=scene)
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        self.assertTrue(
            Interaction.objects.filter(
                content="a wonder occurs", mode=InteractionMode.EMIT, scene=scene
            ).exists()
        )

    @mock.patch("world.gm.prompt_services.broadcast_scene_emit")
    def test_room_text_release_on_dismiss(self, broadcast):
        """#4101 fix round 1: the room-text leg also releases on dismiss, against
        the prompt's OWN scene explicitly."""
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.MIRACLE, room_text="a wonder occurs")
        )[0]
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm)
        broadcast.assert_called_once_with(
            self.sheet.character,
            "a wonder occurs",
            scene=self.scene,
            scene_scoped_push=True,
            push_live=True,
        )

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
        with self.captureOnCommitCallbacks(execute=True):
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

    @mock.patch("world.scenes.interaction_services.push_interaction")
    def test_release_into_finished_scene_is_recorded_not_pushed_live(self, push):
        """#4101 fix round 2, must-fix 2: a room default releasing into a scene
        that has since ended is recorded (the Interaction row exists) but never
        live-pushed -- nobody's watching that room's WebSocket feed for a scene
        that's already over."""
        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.MIRACLE, room_text="a wonder occurs")
        )[0]
        self.scene.is_active = False
        self.scene.save()
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm)
        push.assert_not_called()
        self.assertTrue(
            Interaction.objects.filter(content="a wonder occurs", scene=self.scene).exists()
        )

    @mock.patch("world.scenes.interaction_services.push_interaction")
    def test_release_after_character_moved_pushes_to_scenes_own_location(self, push):
        """#4101 fix round 2, must-fix 2: the live push targets the SCENE's own
        location, never wherever the character has since wandered off to."""
        from evennia_extensions.factories import RoomProfileFactory

        scene_room = RoomProfileFactory().objectdb
        elsewhere_room = RoomProfileFactory().objectdb
        scene = SceneFactory(location=scene_room)
        SceneGMParticipationFactory(scene=scene, account=self.gm)

        prompt = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=scene,
                character_sheet=self.sheet,
                room_text="a wonder occurs",
            )
        )[0]
        self.sheet.character.location = elsewhere_room
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm)

        push.assert_called_once()
        self.assertEqual(push.call_args.kwargs.get("location"), scene_room)

    @mock.patch("world.scenes.interaction_services.push_interaction")
    def test_release_into_location_less_scene_is_recorded_never_pushed(self, push):
        """#4101 fix round 3 (ruling N3): a scene with no location (a Battle,
        ADR-0081) never falls back to the writer's current room for the live
        push -- it is recorded (the Interaction row exists) and nothing more.
        The character here DOES have a real current location, proving this is
        a genuine guard against ``push_interaction``'s own fallback and not
        merely a side effect of the character having nowhere to stand."""
        from evennia_extensions.factories import RoomProfileFactory

        scene = SceneFactory(location=None)
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        self.sheet.character.location = RoomProfileFactory().objectdb

        prompt = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.MIRACLE,
                scene=scene,
                character_sheet=self.sheet,
                room_text="a wonder occurs",
            )
        )[0]
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm)

        push.assert_not_called()
        self.assertTrue(Interaction.objects.filter(content="a wonder occurs", scene=scene).exists())

    def test_failed_resolve_restores_pending_status_and_a_later_dismiss_still_sends(self):
        """#4101 fix round 2: if the database write inside the resolve-and-
        release transaction fails (simulated here via a failing
        ``GMPrompt.save()``), the cached instance's status/resolved_by are put
        back -- the prompt stays PENDING in both the database and the identity
        map, and a later, real dismiss still works and still releases.

        A failed *delivery* (``release_prompt_defaults`` itself raising) can no
        longer produce this symptom at all -- it runs via ``transaction.on_commit``
        now, strictly after the status change has already committed, so by
        definition nothing is left to roll back by the time it could fail.
        """
        from django.db import IntegrityError

        prompt = route_narratable_event(
            self._event(self.scene, kind=GMPromptKind.CROSSING, private_text="vision")
        )[0]

        with mock.patch.object(GMPrompt, "save", side_effect=IntegrityError("boom")):
            with self.assertRaises(IntegrityError):
                dismiss_gm_prompt(prompt, resolver=self.gm)

        # The identity-map-cached object (the same instance route_narratable_event
        # returned) was reverted, not left stuck at DISMISSED.
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)
        self.assertIsNone(prompt.resolved_by)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)

        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                dismiss_gm_prompt(prompt, resolver=self.gm)
        narrate.assert_called_once_with(self.sheet.character, "vision", scene=self.scene)


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
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        narrate.assert_not_called()  # gm_b's sibling is still PENDING

        with self.captureOnCommitCallbacks(execute=True):
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
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=solo_scene)

        with self.captureOnCommitCallbacks(execute=True):
            finish_scene_full(solo_scene)
        narrate.assert_called_once()  # still exactly once

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_skips_release_when_a_sibling_narrated(self, narrate):
        """Dismissing A while sibling B is still open (NARRATED, not closed)
        must not release anything yet -- the event isn't closed until every
        sibling reaches DISMISSED (#4101 fix round 2, controller ruling R6-1).

        #4101 fix round 1 (I2): release is derived from the actual
        ``GMPromptNarration``-linked interaction, not a bare status flip --
        this exercises a real receiver-scoped (pemit-shaped) narration via
        ``link_prompt_narration`` so the per-line coverage check has real data
        to read.
        """
        prompt_a, prompt_b = self._two_gm_prompts(private_text="the vision")
        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="B's private line")
        InteractionReceiverFactory(interaction=interaction, persona=self.sheet.primary_persona)
        link_prompt_narration(prompt_b, interaction)
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        narrate.assert_not_called()

    def _crossing_prompt(self, **kw):
        [prompt] = route_narratable_event(
            NarratableEvent(
                kind=GMPromptKind.CROSSING,
                scene=self.scene,
                character_sheet=self.sheet,
                room_text="the floor groans",
                private_text="the vision",
                **kw,
            ),
            candidates=[self.gm_a],
        )
        return prompt

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_room_narration_does_not_release_private_default_yet(self, narrate):
        """#4101 fix round 2 (controller ruling R6-1): a GM's first narration
        does not decide the release -- a room-only narration must not release
        the vision while the prompt stays open for more lines."""
        prompt = self._crossing_prompt()
        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the floor groans")
        with self.captureOnCommitCallbacks(execute=True):
            link_prompt_narration(prompt, interaction)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)
        narrate.assert_not_called()

    @mock.patch("world.gm.prompt_services.broadcast_scene_emit")
    def test_private_narration_does_not_release_room_default_yet(self, broadcast):
        """The reverse: a private-only narration must not release the room
        default while the prompt stays open."""
        prompt = self._crossing_prompt()
        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the vision")
        InteractionReceiverFactory(interaction=interaction, persona=self.sheet.primary_persona)
        with self.captureOnCommitCallbacks(execute=True):
            link_prompt_narration(prompt, interaction)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)
        broadcast.assert_not_called()

    @mock.patch("world.gm.prompt_services.broadcast_scene_emit")
    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_room_then_private_narration_then_close_releases_nothing_extra(
        self, narrate, broadcast
    ):
        """Both lines narrated, then the GM closes the prompt: nothing extra
        releases -- every leg was already covered by a real narration."""
        prompt = self._crossing_prompt()
        room_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the floor groans")
        vision_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the vision")
        InteractionReceiverFactory(
            interaction=vision_interaction, persona=self.sheet.primary_persona
        )
        link_prompt_narration(prompt, room_interaction)
        link_prompt_narration(prompt, vision_interaction)
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)
        narrate.assert_not_called()
        broadcast.assert_not_called()

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_room_narrated_then_close_releases_vision_once(self, narrate):
        """Room-only narration, then the GM closes the prompt: the vision
        (never covered) releases exactly once."""
        prompt = self._crossing_prompt()
        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the floor groans")
        link_prompt_narration(prompt, interaction)
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=self.scene)

    @mock.patch("world.gm.prompt_services.broadcast_scene_emit")
    def test_private_narrated_then_close_releases_room_once(self, broadcast):
        """Private-only narration, then the GM closes the prompt: the room
        line (never covered) releases exactly once."""
        prompt = self._crossing_prompt()
        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the vision")
        InteractionReceiverFactory(interaction=interaction, persona=self.sheet.primary_persona)
        link_prompt_narration(prompt, interaction)
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)
        broadcast.assert_called_once_with(
            self.sheet.character,
            "the floor groans",
            scene=self.scene,
            scene_scoped_push=True,
            push_live=True,
        )

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_expire_scene_prompts_closes_narrated_and_releases_uncovered_once(self, narrate):
        """#4101 fix round 3 (N2 test 1): expire_scene_prompts must close a
        NARRATED prompt too, not just PENDING ones -- a GM who covered the
        room line, then the scene ends before they send the private line,
        must still get that uncovered line released exactly once. Fails if
        the expire query's ``status__in`` is reverted to PENDING-only (the
        prompt would stay NARRATED forever and the vision would never go
        out)."""
        prompt = self._crossing_prompt()
        room_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the floor groans")
        link_prompt_narration(prompt, room_interaction)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)

        with self.captureOnCommitCallbacks(execute=True):
            expired = expire_scene_prompts(self.scene)

        self.assertEqual(expired, 1)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=self.scene)

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_a_narrates_room_b_dismisses_a_closes_releases_private_once(self, narrate):
        """#4101 fix round 3 (N2 test 3): A narrates the room line (A ->
        NARRATED, stays open); B dismisses (B -> DISMISSED, but A is still
        open so nothing releases yet); A then closes -- only now does the
        event fully close, and the uncovered private line releases exactly
        once, never on B's earlier dismiss."""
        prompt_a, prompt_b = self._two_gm_prompts(
            room_text="a wonder occurs", private_text="the vision"
        )
        room_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="a wonder occurs")
        link_prompt_narration(prompt_a, room_interaction)
        prompt_a.refresh_from_db()
        self.assertEqual(prompt_a.status, GMPromptStatus.NARRATED)

        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt_b, resolver=self.gm_b)
        narrate.assert_not_called()  # A is still open (NARRATED); event not closed yet

        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt_a, resolver=self.gm_a)
        narrate.assert_called_once_with(self.sheet.character, "the vision", scene=self.scene)

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

    def test_narration_after_close_is_rejected_not_double_linked(self):
        """#4101 fix round 3 (ruling N6), fix round 4: a narration arriving for a
        prompt that has ALREADY closed is refused -- returns None, no link row --
        never silently linked and never raised out of the ``on_created`` hook."""
        prompt = self._crossing_prompt()
        room_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the floor groans")
        link_prompt_narration(prompt, room_interaction)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)

        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)

        late_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="too late")
        self.assertIsNone(link_prompt_narration(prompt, late_interaction))
        self.assertFalse(GMPromptNarration.objects.filter(interaction=late_interaction).exists())

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_narration_after_pending_close_is_refused_default_released_once(self, narrate):
        """#4101 fix round 4: a PENDING prompt closed before its narration lands --
        the narration is refused (no link, prompt stays DISMISSED), and the
        uncovered default the close released goes out exactly once."""
        prompt = self._crossing_prompt()
        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm_a)
        narrate.assert_called_once()

        late_interaction = InteractionFactory(mode=InteractionMode.EMIT, content="the vision")
        InteractionReceiverFactory(interaction=late_interaction, persona=self.sheet.primary_persona)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertIsNone(link_prompt_narration(prompt, late_interaction))
        self.assertFalse(GMPromptNarration.objects.filter(prompt=prompt).exists())
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once()  # never a second send

    def _assert_link_written_under_lock(self, prompt):
        events: list[str] = []
        original_lock = GMPrompt.objects.select_for_update
        original_create = GMPromptNarration.objects.create

        def _lock(*args, **kwargs):
            events.append("lock")
            return original_lock(*args, **kwargs)

        def _create(*args, **kwargs):
            events.append("link")
            return original_create(*args, **kwargs)

        interaction = InteractionFactory(mode=InteractionMode.EMIT, content="a line")
        with (
            mock.patch.object(GMPrompt.objects, "select_for_update", side_effect=_lock),
            mock.patch.object(GMPromptNarration.objects, "create", side_effect=_create),
        ):
            link_prompt_narration(prompt, interaction)
        self.assertIn("link", events)
        self.assertEqual(events[0], "lock", events)

    def test_first_narration_takes_sibling_lock_before_linking(self):
        """#4101 fix round 4: the PENDING (first-narration) path locks the event's
        siblings BEFORE inserting the link row, so a concurrent close can never
        compute coverage without seeing it (and the insert's key-share lock is
        never held ahead of the close's FOR UPDATE)."""
        prompt = self._crossing_prompt()
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)
        self._assert_link_written_under_lock(prompt)

    def test_later_narration_takes_sibling_lock_before_linking(self):
        """The NARRATED (repeat-narration) path takes the same lock first."""
        prompt = self._crossing_prompt()
        link_prompt_narration(prompt, InteractionFactory(mode=InteractionMode.EMIT))
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.NARRATED)
        self._assert_link_written_under_lock(prompt)
