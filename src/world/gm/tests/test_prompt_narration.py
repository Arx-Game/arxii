"""GM narration is an EMIT interaction linked to its prompt (#4101 Task 3)."""

from unittest import mock

from django.test import TestCase

from actions.definitions.communication import EmitAction, PemitAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.gm.models import GMPrompt, GMPromptNarration
from world.gm.prompt_services import dismiss_gm_prompt
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


def _narrates_from(mock_msg) -> dict | None:
    """The ``narrates`` field of the first captured ``interaction=`` push, or None."""
    for call in mock_msg.call_args_list:
        if "interaction" in call.kwargs:
            _, payload = call.kwargs["interaction"]
            return payload.get("narrates")
    return None


class PromptNarrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm_account = AccountFactory()
        GMProfileFactory(account=cls.gm_account)
        cls.gm_sheet = CharacterSheetFactory()
        cls.gm_char = cls.gm_sheet.character
        cls.gm_char.db_account = cls.gm_account
        cls.gm_char.save()
        # PemitAction's MinimumGMLevelPrerequisite reads actor.active_account, which
        # resolves through a live roster tenure -- NOT the plain .account attribute
        # set in setUp() (that idiom only covers code reading actor.account directly,
        # e.g. narration_prompt_for). Mirrors PemitActionTests._gm_actor.
        entry = RosterEntryFactory(character_sheet=cls.gm_sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=cls.gm_account),
            end_date=None,
        )
        cls.crosser = CharacterSheetFactory()
        cls.scene = SceneFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm_account)

    def setUp(self):
        # actions read actor.account (the puppeting account); bind it per test
        # (the same idiom as actions/tests/test_deed_actions.py).
        self.gm_char.account = self.gm_account
        # Factory characters have location=None and get_active_scene(None) is None,
        # so pin "the scene the GM stands in" at the seam narration_prompt_for reads.
        patcher = mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm_account,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="manifestation",
        )

    def test_public_narration_is_logged_and_linked(self):
        result = EmitAction().run(
            actor=self.gm_char, text="The floor groans.", gm_prompt_id=self.prompt.pk
        )
        self.assertTrue(result.success, result.message)
        link = GMPromptNarration.objects.get(prompt=self.prompt)
        self.assertEqual(link.interaction.content, "The floor groans.")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.NARRATED)

    def test_private_narration_is_receiver_scoped_and_linked(self):
        result = PemitAction().run(
            actor=self.gm_char,
            text="vision",
            receivers=[self.crosser.character],
            gm_prompt_id=self.prompt.pk,
        )
        self.assertTrue(result.success, result.message)
        interaction = GMPromptNarration.objects.get(prompt=self.prompt).interaction
        self.assertEqual(
            [r.persona_id for r in interaction.receivers.all()],
            [self.crosser.primary_persona.pk],
        )

    def test_both_sends_link_to_one_prompt(self):
        EmitAction().run(actor=self.gm_char, text="room", gm_prompt_id=self.prompt.pk)
        PemitAction().run(
            actor=self.gm_char,
            text="private",
            receivers=[self.crosser.character],
            gm_prompt_id=self.prompt.pk,
        )
        self.assertEqual(GMPromptNarration.objects.filter(prompt=self.prompt).count(), 2)

    def test_other_account_refused(self):
        intruder = CharacterFactory()
        intruder.account = AccountFactory()
        result = EmitAction().run(actor=intruder, text="x", gm_prompt_id=self.prompt.pk)
        self.assertFalse(result.success)
        self.assertFalse(GMPromptNarration.objects.exists())

    def test_dismissed_prompt_refused(self):
        self.prompt.status = GMPromptStatus.DISMISSED
        self.prompt.save()
        result = EmitAction().run(actor=self.gm_char, text="x", gm_prompt_id=self.prompt.pk)
        self.assertFalse(result.success)

    def test_scene_bound_prompt_refused_from_another_room(self):
        other_scene = SceneFactory()
        self.prompt.scene = other_scene
        self.prompt.save()
        before = Interaction.objects.count()
        result = EmitAction().run(actor=self.gm_char, text="x", gm_prompt_id=self.prompt.pk)
        self.assertFalse(result.success)
        self.assertEqual(Interaction.objects.count(), before)

    def test_plain_emit_unchanged(self):
        result = EmitAction().run(actor=self.gm_char, text="plain")
        self.assertTrue(result.success)
        self.assertFalse(GMPromptNarration.objects.exists())

    def test_staff_may_narrate_a_prompt_addressed_to_another_gm(self):
        staff_account = AccountFactory(is_staff=True)
        staff_sheet = CharacterSheetFactory()
        staff_char = staff_sheet.character
        staff_char.db_account = staff_account
        staff_char.save()
        staff_char.account = staff_account
        result = EmitAction().run(
            actor=staff_char, text="Staff narrates it.", gm_prompt_id=self.prompt.pk
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_two_gms_narrate_sibling_prompts_both_delivered_no_release(self):
        """Two GMs each narrating their own copy of one event: both land, neither default fires."""
        second_account = AccountFactory()
        second_sheet = CharacterSheetFactory()
        second_char = second_sheet.character
        second_char.db_account = second_account
        second_char.save()
        second_char.account = second_account
        second_prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            event_group=self.prompt.event_group,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=second_account,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="manifestation",
        )

        result_a = EmitAction().run(
            actor=self.gm_char, text="A's line.", gm_prompt_id=self.prompt.pk
        )
        result_b = EmitAction().run(
            actor=second_char, text="B's line.", gm_prompt_id=second_prompt.pk
        )

        self.assertTrue(result_a.success, result_a.message)
        self.assertTrue(result_b.success, result_b.message)
        self.assertTrue(GMPromptNarration.objects.filter(prompt=self.prompt).exists())
        self.assertTrue(GMPromptNarration.objects.filter(prompt=second_prompt).exists())
        self.prompt.refresh_from_db()
        second_prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.NARRATED)
        self.assertEqual(second_prompt.status, GMPromptStatus.NARRATED)
        # No default text released for either sibling: only the two narration rows exist.
        self.assertEqual(Interaction.objects.count(), 2)

    def test_narrate_a_prompt_scene_end_just_dismissed(self):
        """A narration racing a concurrent dismiss is delivered and linked, never raises."""
        original_create = GMPromptNarration.objects.create

        def _create_then_concurrent_dismiss(*args, **kwargs):
            link = original_create(*args, **kwargs)
            # Simulate scene end's expire_scene_prompts dismissing this exact prompt
            # out from under the still-in-flight narration, via a second resolved
            # reference (never the stale `self.prompt` the action already fetched).
            dismiss_gm_prompt(GMPrompt.objects.get(pk=self.prompt.pk), resolver=None)
            return link

        with mock.patch.object(
            GMPromptNarration.objects, "create", side_effect=_create_then_concurrent_dismiss
        ):
            result = EmitAction().run(
                actor=self.gm_char, text="The ceiling cracks.", gm_prompt_id=self.prompt.pk
            )

        self.assertTrue(result.success, result.message)
        link = GMPromptNarration.objects.get(prompt=self.prompt)
        self.assertEqual(link.interaction.content, "The ceiling cracks.")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)


class NarratedPushPayloadTest(TestCase):
    """The live push payload's `narrates` field is populated for a narrated row (#4101)."""

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(
            db_key="Narration Room", db_typeclass_path="typeclasses.rooms.Room"
        )
        cls.gm_account = AccountFactory()
        GMProfileFactory(account=cls.gm_account)
        cls.gm_sheet = CharacterSheetFactory()
        cls.gm_char = cls.gm_sheet.character
        cls.gm_char.db_account = cls.gm_account
        cls.gm_char.location = cls.room
        cls.gm_char.save()
        # PemitAction's MinimumGMLevelPrerequisite reads actor.active_account (a live
        # roster tenure), not the plain .account attribute set in setUp().
        entry = RosterEntryFactory(character_sheet=cls.gm_sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=cls.gm_account),
            end_date=None,
        )
        cls.crosser = CharacterSheetFactory()
        cls.crosser.character.location = cls.room
        cls.scene = SceneFactory()

    def setUp(self):
        self.gm_char.account = self.gm_account
        patcher = mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm_account,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="manifestation",
        )

    def _assert_narrates_matches_prompt(self, narrates: dict | None) -> None:
        self.assertIsNotNone(narrates)
        self.assertEqual(narrates["prompt_id"], self.prompt.pk)
        self.assertEqual(narrates["kind"], GMPromptKind.CROSSING)
        self.assertEqual(narrates["kind_label"], self.prompt.get_kind_display())
        self.assertEqual(narrates["subject_name"], self.crosser.primary_persona.name)
        self.assertEqual(narrates["subject_persona_id"], self.crosser.primary_persona.pk)

    def test_emit_narration_pushes_populated_narrates(self):
        with mock.patch.object(self.gm_char, "msg") as mock_msg:
            result = EmitAction().run(
                actor=self.gm_char, text="The floor groans.", gm_prompt_id=self.prompt.pk
            )
        self.assertTrue(result.success, result.message)
        self._assert_narrates_matches_prompt(_narrates_from(mock_msg))

    def test_pemit_narration_pushes_populated_narrates(self):
        with mock.patch.object(self.crosser.character, "msg") as mock_msg:
            result = PemitAction().run(
                actor=self.gm_char,
                text="vision",
                receivers=[self.crosser.character],
                gm_prompt_id=self.prompt.pk,
            )
        self.assertTrue(result.success, result.message)
        self._assert_narrates_matches_prompt(_narrates_from(mock_msg))
