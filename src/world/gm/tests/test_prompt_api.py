"""The GM prompt queue API (#4101 Task 9): visibility, confirm, dismiss, narrate, filters."""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.gm.models import GMPromptFilter, GMPromptNarration
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import (
    SceneFactory,
    SceneGMParticipationFactory,
    SceneOwnerParticipationFactory,
)
from world.scenes.models import Interaction

URL = "/api/gm/prompts/"


class GMPromptApiTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.scene = SceneFactory()
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm)
        cls.other_gm = AccountFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        SceneGMParticipationFactory(scene=cls.scene, account=cls.other_gm)
        cls.owner_player = AccountFactory()
        SceneOwnerParticipationFactory(scene=cls.scene, account=cls.owner_player)
        cls.crosser = CharacterSheetFactory()
        cls.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=cls.scene,
            character_sheet=cls.crosser,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="room",
        )
        cls.stake_prompt = GMPromptFactory(
            kind=GMPromptKind.STAKE_OUTCOME,
            scene=None,
            character_sheet=None,
            addressed_to=cls.gm,
            moment_type=None,
            success_level=None,
        )
        cls.moment = GMPromptFactory(scene=cls.scene)  # dramatic_moment kind

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(account)
        return client

    def _ids(self, account):
        resp = self._client(account).get(URL, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 200)
        return {row["id"] for row in resp.data["results"]}

    def test_addressed_gm_sees_scene_and_sceneless_prompts(self):
        self.assertEqual(self._ids(self.gm), {self.prompt.pk, self.stake_prompt.pk, self.moment.pk})

    def test_other_gm_never_sees_my_prompt(self):
        self.assertEqual(self._ids(self.other_gm), {self.moment.pk})

    def test_scene_owner_player_never_sees_narration_prompts(self):
        self.assertEqual(self._ids(self.owner_player), {self.moment.pk})

    def test_subject_player_sees_nothing(self):
        stranger = AccountFactory()
        resp = self._client(stranger).get(URL, {"scene": self.scene.pk})
        self.assertEqual(resp.status_code, 403)

    def test_missing_scene_param_is_400(self):
        """#4101 fix round 2, finding 5 (ported from the retired suggestion API's own
        "missing ?scene= returns 400" test): GMPromptQueueFilter's ``scene`` is
        required, so DjangoFilterBackend raises before the view runs at all."""
        resp = self._client(self.gm).get(URL)
        self.assertEqual(resp.status_code, 400)

    def test_gm_who_muted_moments_does_not_see_them(self):
        GMPrompt = type(self.moment)
        muter = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=muter)
        GMPromptFilter.objects.create(
            account=muter, group=GMPromptGroup.DRAMATIC_MOMENT, enabled=False
        )
        self.assertNotIn(self.moment.pk, self._ids(muter))
        self.assertTrue(GMPrompt.objects.filter(pk=self.moment.pk).exists())

    def test_private_text_only_in_the_addressed_gms_payload(self):
        resp = self._client(self.gm).get(URL, {"scene": self.scene.pk})
        row = next(r for r in resp.data["results"] if r["id"] == self.prompt.pk)
        self.assertEqual(row["private_text"], "vision")

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_dismiss_narration_releases(self, narrate):
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            private_text="x",
        )
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._client(self.gm).post(f"{URL}{prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 200)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once()

    def test_narrate_room_links(self):
        with (
            mock.patch("world.gm.views.character_for_request", return_value=self._gm_character()),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene),
        ):
            resp = self._client(self.gm).post(
                f"{URL}{self.prompt.pk}/narrate/",
                {"text": "The floor groans.", "audience": "room"},
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_narrate_chosen_refused_without_gm_trust_returns_400(self):
        """A room is required here (#4101 fix round 3, finding N3): with no
        location at all, the serializer's own "no room to narrate from" refusal
        would fire first and the response would carry ``non_field_errors``, not
        this test's actual target -- the trust prerequisite's ``detail``."""
        untrusted = AccountFactory()  # scene GM by participation, no GMProfile, not staff
        SceneGMParticipationFactory(scene=self.scene, account=untrusted)
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        receiver = CharacterSheetFactory()
        receiver.character.location = room
        receiver.character.save()
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=untrusted,
            moment_type=None,
            success_level=None,
        )
        char = CharacterSheetFactory().character
        char.account = untrusted
        char.location = room
        char.save()
        with (
            mock.patch("world.gm.views.character_for_request", return_value=char),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene),
        ):
            resp = self._client(untrusted).post(
                f"{URL}{prompt.pk}/narrate/",
                {
                    "text": "x",
                    "audience": "chosen",
                    "receiver_persona_ids": [receiver.primary_persona.pk],
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)
        self.assertFalse(GMPromptNarration.objects.filter(prompt=prompt).exists())

    @mock.patch("world.gm.prompt_services.narrate_privately")
    def test_narrated_prompt_stays_in_queue_and_dismiss_closes_it(self, narrate):
        """Controller amendment R6-2 (#4101 fix round 2, finding 3): a NARRATED
        prompt stays in the queue and dismiss still closes it, releasing the
        uncovered (private) line exactly once."""
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            status=GMPromptStatus.NARRATED,
            private_text="vision",
        )
        self.assertIn(prompt.pk, self._ids(self.gm))
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._client(self.gm).post(f"{URL}{prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 200, resp.data)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once()

    def test_resolved_prompts_are_excluded_from_the_queue(self):
        """#4101 fix round 2, finding 10 (ported from the retired suggestion API's
        own "resolved suggestion is excluded" test)."""
        dismissed_narration = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            status=GMPromptStatus.DISMISSED,
        )
        confirmed_moment = GMPromptFactory(scene=self.scene, status=GMPromptStatus.CONFIRMED)
        ids = self._ids(self.gm)
        self.assertNotIn(dismissed_narration.pk, ids)
        self.assertNotIn(confirmed_moment.pk, ids)

    def test_staff_may_dismiss_a_narration_prompt(self):
        """Ruling R9-2 (#4101 fix round 2, finding 7): staff bypass the addressed-to
        gate on dismiss, matching narration_prompt_for's own staff bypass for narrate."""
        staff = AccountFactory(is_staff=True)
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
        )
        resp = self._client(staff).post(f"{URL}{prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 200, resp.data)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)

    def test_other_gm_cannot_dismiss_my_prompt(self):
        """IDOR (#4101 fix round 2, finding 4): refused, status unchanged, nothing delivered."""
        resp = self._client(self.other_gm).post(f"{URL}{self.prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 404)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.PENDING)

    def test_scene_owner_cannot_dismiss_my_prompt(self):
        """IDOR (#4101 fix round 2, finding 4): a non-GM player, refused."""
        resp = self._client(self.owner_player).post(f"{URL}{self.prompt.pk}/dismiss/")
        self.assertEqual(resp.status_code, 404)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.PENDING)

    def test_other_gm_cannot_narrate_my_prompt(self):
        """IDOR (#4101 fix round 2, finding 4): refused before any dispatch, nothing delivered."""
        resp = self._client(self.other_gm).post(
            f"{URL}{self.prompt.pk}/narrate/", {"text": "x", "audience": "room"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_scene_owner_cannot_narrate_my_prompt(self):
        """IDOR (#4101 fix round 2, finding 4): a non-GM player, refused."""
        resp = self._client(self.owner_player).post(
            f"{URL}{self.prompt.pk}/narrate/", {"text": "x", "audience": "room"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_narrate_chosen_refuses_persona_outside_the_room(self):
        """#4101 fix round 2, finding 1: a batched, scene-location presence check.
        Extended (#4101 fix round 3, finding M3): the refusal creates nothing at
        all -- no narration link, no Interaction (the room/private pose never
        gets dispatched)."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
        )
        elsewhere = CharacterSheetFactory()  # never placed in `room` -- location stays None
        interactions_before = Interaction.objects.count()
        with (
            mock.patch("world.gm.views.character_for_request", return_value=self._gm_character()),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=scene),
        ):
            resp = self._client(self.gm).post(
                f"{URL}{prompt.pk}/narrate/",
                {
                    "text": "x",
                    "audience": "chosen",
                    "receiver_persona_ids": [elsewhere.primary_persona.pk],
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertFalse(GMPromptNarration.objects.filter(prompt=prompt).exists())
        self.assertEqual(Interaction.objects.count(), interactions_before)

    def test_narrate_chosen_refuses_when_no_room_is_available(self):
        """#4101 fix round 3, finding N3: a location-less scene (e.g. a
        Battle-backed scene) with no fallback either -- the narrating GM's own
        character also has no location here -- refuses with a neutral 400
        rather than treating "nowhere" as a room everyone with no location
        matches. Also covers finding M3: nothing is created on the refusal."""
        battle_scene = SceneFactory()  # location=None, mirroring a Battle-backed scene
        SceneGMParticipationFactory(scene=battle_scene, account=self.gm)
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=battle_scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
        )
        gm_character = self._gm_character()  # fresh factory character -- no location set either
        interactions_before = Interaction.objects.count()
        with (
            mock.patch("world.gm.views.character_for_request", return_value=gm_character),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=battle_scene),
        ):
            resp = self._client(self.gm).post(
                f"{URL}{prompt.pk}/narrate/",
                {
                    "text": "x",
                    "audience": "chosen",
                    "receiver_persona_ids": [self.crosser.primary_persona.pk],
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 400, resp.data)
        # Neutral: never names the persona the GM tried to choose.
        self.assertNotIn(self.crosser.primary_persona.name, str(resp.data))
        self.assertFalse(GMPromptNarration.objects.filter(prompt=prompt).exists())
        self.assertEqual(Interaction.objects.count(), interactions_before)

    def test_narrate_chosen_accepts_persona_present_in_the_room(self):
        """#4101 fix round 2, finding 1: the mirror-image success case."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        scene = SceneFactory(location=room)
        SceneGMParticipationFactory(scene=scene, account=self.gm)
        prompt = GMPromptFactory(
            kind=GMPromptKind.DEATH,
            scene=scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
        )
        present = CharacterSheetFactory()
        present.character.location = room
        present.character.save()
        with (
            mock.patch("world.gm.views.character_for_request", return_value=self._gm_character()),
            mock.patch("world.gm.prompt_services.get_active_scene", return_value=scene),
        ):
            resp = self._client(self.gm).post(
                f"{URL}{prompt.pk}/narrate/",
                {
                    "text": "x",
                    "audience": "chosen",
                    "receiver_persona_ids": [present.primary_persona.pk],
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue(GMPromptNarration.objects.filter(prompt=prompt).exists())

    def test_filters_list_five_groups_and_set(self):
        client = self._client(self.gm)
        rows = client.get("/api/gm/prompt-filters/").data
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r["enabled"] for r in rows))
        resp = client.post(
            "/api/gm/prompt-filters/set/", {"group": "miracle", "enabled": False}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            GMPromptFilter.objects.get(account=self.gm, group=GMPromptGroup.MIRACLE).enabled
        )

    def _gm_character(self):
        """A character puppeted by ``self.gm``, with a REAL roster tenure.

        ``PemitAction``'s ``MinimumGMLevelPrerequisite`` reads ``actor.active_account``,
        which resolves through a live roster tenure -- NOT the plain ``.account``
        attribute set below (that idiom only covers code reading ``actor.account``
        directly, e.g. ``narration_prompt_for``). Mirrors
        ``world.gm.tests.test_prompt_narration.PromptNarrationTest``'s own setup.
        """
        sheet = CharacterSheetFactory()
        char = sheet.character
        char.account = self.gm
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=self.gm),
            end_date=None,
        )
        return char


class GMPromptDramaticMomentConfirmDismissTest(TestCase):
    """POST .../{id}/confirm/ and .../{id}/dismiss/ on a dramatic_moment prompt (#2183,
    ported from the retired ``world.magic.tests.test_suggestion_api`` module — unchanged
    in substance, now against the one GMPromptViewSet queue instead of the retired
    per-app suggestion inbox)."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance_holder.resonance, per_scene_cap=1
        )
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        self.suggestion = GMPromptFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(account)
        return client

    def _url(self, action: str, suggestion_id: int | None = None) -> str:
        return f"{URL}{suggestion_id or self.suggestion.pk}/{action}/"

    def test_gm_confirms_mints_tag_and_grants_resonance(self):
        resp = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], GMPromptStatus.CONFIRMED)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.CONFIRMED)
        self.assertIsNotNone(self.suggestion.confirmed_tag)
        self.assertTrue(
            DramaticMomentTag.objects.filter(pk=self.suggestion.confirmed_tag_id).exists()
        )
        self.assertTrue(
            ResonanceGrant.objects.filter(character_sheet=self.sheet, amount=15).exists()
        )

    def test_gm_dismisses_no_tag(self):
        resp = self._client(self.gm).post(self._url("dismiss"))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.DISMISSED)
        self.assertIsNone(self.suggestion.confirmed_tag)

    def test_non_gm_participant_confirm_is_forbidden(self):
        """#4101 fix round 2, finding 6: the object lookup itself is now scoped to
        ``visible_prompts_for`` -- a non-GM/owner never reaches the action's own
        gate at all, so this is a 404 (an invisible id), not a 400 from inside it."""
        participant = AccountFactory()
        resp = self._client(participant).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 404, resp.data)
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_confirm_after_cap_returns_400_with_user_message(self):
        DramaticMomentTagFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        resp = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("detail", resp.data)
        self.assertTrue(resp.data["detail"])
        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, GMPromptStatus.PENDING)

    def test_double_confirm_returns_400(self):
        first = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(first.status_code, 200, first.data)
        second = self._client(self.gm).post(self._url("confirm"))
        self.assertEqual(second.status_code, 400, second.data)
        self.assertIn("detail", second.data)
        self.assertTrue(second.data["detail"])
