"""The Crossing as a narratable event (#4101 Task 6; spec scenarios 1-2)."""

from unittest import mock

from django.db import DatabaseError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.gm.prompt_services import dismiss_gm_prompt
from world.magic.factories import CharacterCrossingTextFactory
from world.magic.models.prepared_text import CharacterCrossingText
from world.magic.serializers import PendingAudereMajoraOfferSerializer
from world.mechanics.engagement import CharacterEngagement
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


class CrossingNarrationTest(TestCase):
    """Builds on the crossing fixtures in the existing crossing test module."""

    @classmethod
    def setUpTestData(cls):
        from world.magic.factories import wire_audere_power_multipliers
        from world.magic.tests.majora_fixtures import build_majora_world

        # cross_threshold applies the Audere Majora ConditionTemplate -- neither
        # build_majora_world nor build_crossing_world wires it (only the crossing
        # test module's own setUp does). Not part of the brief's literal test body;
        # without it every accept in this module 500s on ConditionTemplate.DoesNotExist
        # regardless of Task 6's narration changes.
        wire_audere_power_multipliers()
        (
            cls.character,
            cls.sheet,
            cls.threshold,
            _prospect,
            cls.path,
            _stage,
        ) = build_majora_world(
            10, "narr4101", vision_text="tier vision", manifestation_text="tier room"
        )
        cls.scene = SceneFactory(location=cls.character.location)
        cls.gm = AccountFactory()

    def _offer(self):
        from world.magic.audere_majora import maybe_create_audere_majora_offer

        return maybe_create_audere_majora_offer(self.character, 99, sheet=self.sheet)

    def _cross(self, offer):
        from world.magic.audere_majora import resolve_audere_majora_offer

        with self.captureOnCommitCallbacks(execute=True):
            return resolve_audere_majora_offer(
                offer.pk, accept=True, path_id=self.path.pk, declaration_text="I cross."
            )

    def test_no_gm_logs_the_vision_privately(self):
        self._cross(self._offer())
        row = Interaction.objects.get(content="tier vision")
        self.assertEqual(row.mode, InteractionMode.WHISPER)
        self.assertEqual(
            [r.persona_id for r in row.receivers.all()], [self.sheet.primary_persona.pk]
        )
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.CROSSING).exists())

    def test_no_gm_broadcasts_manifestation_at_gate_open(self):
        self._offer()
        self.assertTrue(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).exists()
        )

    def test_gm_present_withholds_and_prompts(self):
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)
        self.assertFalse(Interaction.objects.filter(content="tier room").exists())
        self._cross(offer)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.CROSSING, addressed_to=self.gm)
        self.assertEqual(prompt.private_text, "tier vision")
        self.assertEqual(prompt.room_text, "tier room")
        self.assertFalse(Interaction.objects.filter(content="tier vision").exists())

    def test_prepared_text_wins_and_is_consumed(self):
        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="her vision")
        offer = self._offer()
        data = PendingAudereMajoraOfferSerializer(offer).data
        self.assertEqual(data["vision_text"], "her vision")
        self._cross(offer)
        self.assertTrue(Interaction.objects.filter(content="her vision").exists())
        self.assertIsNotNone(CharacterCrossingText.objects.get(character_sheet=self.sheet).crossing)

    def test_declined_offer_keeps_prepared_text(self):
        from world.magic.audere_majora import resolve_audere_majora_offer

        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="kept")
        resolve_audere_majora_offer(self._offer().pk, accept=False)
        self.assertIsNone(CharacterCrossingText.objects.get(character_sheet=self.sheet).crossing)

    def test_prepared_deed_title(self):
        CharacterCrossingTextFactory(character_sheet=self.sheet, deed_title="Who Held the Rail")
        self._cross(self._offer())
        from world.magic.audere_majora import AudereMajoraCrossing

        crossing = AudereMajoraCrossing.objects.get(character_sheet=self.sheet)
        self.assertEqual(crossing.legend_entry.title, "Who Held the Rail")

    # -------------------------------------------------------------------
    # Fix round 1: withheld manifestation is never silently dropped (I1)
    # -------------------------------------------------------------------

    def test_decline_sends_withheld_manifestation_to_its_scene(self):
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)

        from world.magic.audere_majora import resolve_audere_majora_offer

        with self.captureOnCommitCallbacks(execute=True):
            resolve_audere_majora_offer(offer.pk, accept=False)

        self.assertTrue(
            Interaction.objects.filter(
                content="tier room", mode=InteractionMode.EMIT, scene=self.scene
            ).exists()
        )

    def test_stale_offer_sends_withheld_manifestation_to_its_scene(self):
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)

        CharacterEngagement.objects.filter(character=self.sheet).delete()

        from world.magic.audere_majora import resolve_audere_majora_offer
        from world.magic.exceptions import AudereMajoraOfferStaleError

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(AudereMajoraOfferStaleError):
                resolve_audere_majora_offer(
                    offer.pk, accept=True, path_id=self.path.pk, declaration_text="I cross."
                )

        self.assertTrue(
            Interaction.objects.filter(
                content="tier room", mode=InteractionMode.EMIT, scene=self.scene
            ).exists()
        )

    def test_gm_leaves_before_crossing_still_delivers_both(self):
        """The GM who was present at gate-open leaves before the crossing --
        the held manifestation and the vision must still both arrive (#4101
        fix round 1, M6)."""
        participation = SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)

        participation.left_at = participation.joined_at
        participation.save()

        self._cross(offer)

        self.assertTrue(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).exists()
        )
        self.assertTrue(
            Interaction.objects.filter(content="tier vision", mode=InteractionMode.WHISPER).exists()
        )
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.CROSSING).exists())

    def test_gm_joins_after_gate_open_no_double_manifestation(self):
        """No GM at gate-open broadcasts the manifestation immediately; a GM
        who joins before the crossing is still prompted, but the room line
        never fires a second time (#4101 fix round 1, M6)."""
        offer = self._offer()
        offer.refresh_from_db()
        self.assertFalse(offer.manifestation_withheld)
        self.assertEqual(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).count(), 1
        )

        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        # Scene is idmapper-shared; `self.scene` (the object this test holds,
        # from `SceneFactory`) is not the same Python object the ORM's own
        # `active_for_room(...).first()` resolution later returns and caches
        # `participations_cached` on -- fetch via that exact path and bust its
        # cache, mirroring the lookup `cross_threshold`/`scene_gm_accounts`
        # actually perform, so the new participation is visible to them.
        from world.scenes.models import Scene as _Scene

        fresh_scene = _Scene.objects.active_for_room(self.character.location).first()
        del fresh_scene.participations_cached
        self._cross(offer)

        self.assertEqual(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).count(), 1
        )
        prompt = GMPrompt.objects.get(kind=GMPromptKind.CROSSING, addressed_to=self.gm)
        self.assertEqual(prompt.room_text, "")
        self.assertEqual(prompt.private_text, "tier vision")

    def test_dismiss_releases_exactly_the_crossings_text(self):
        """Dismissing an unnarrated Crossing prompt releases exactly its own
        resolved text, to the right scene and the right audience (#4101 fix
        round 1, M6)."""
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        self._cross(offer)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.CROSSING, addressed_to=self.gm)

        with self.captureOnCommitCallbacks(execute=True):
            dismiss_gm_prompt(prompt, resolver=self.gm)

        manifestation = Interaction.objects.get(content="tier room", mode=InteractionMode.EMIT)
        self.assertEqual(manifestation.scene_id, self.scene.pk)
        vision = Interaction.objects.get(content="tier vision", mode=InteractionMode.WHISPER)
        self.assertEqual(
            [r.persona_id for r in vision.receivers.all()], [self.sheet.primary_persona.pk]
        )

    # -------------------------------------------------------------------
    # I3: the offer poll never shows the vision while a GM will narrate it
    # -------------------------------------------------------------------

    def test_vision_hidden_from_poll_while_withheld(self):
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)
        data = PendingAudereMajoraOfferSerializer(offer).data
        self.assertEqual(data["vision_text"], "")

    # -------------------------------------------------------------------
    # M3: prepared_for_character reflects the VISION field only
    # -------------------------------------------------------------------

    def test_prepared_for_character_true_only_for_vision(self):
        CharacterCrossingTextFactory(
            character_sheet=self.sheet, vision_text="", manifestation_text="her room"
        )
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        self._cross(offer)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.CROSSING, addressed_to=self.gm)
        self.assertFalse(prompt.prepared_for_character)
        self.assertEqual(prompt.room_text, "her room")

    def test_prepared_for_character_true_when_vision_is_prepared(self):
        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="her vision")
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        self._cross(offer)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.CROSSING, addressed_to=self.gm)
        self.assertTrue(prompt.prepared_for_character)

    # -------------------------------------------------------------------
    # M5: the crosser is never a recipient of their own Crossing prompt
    # -------------------------------------------------------------------

    def test_crosser_excluded_from_their_own_crossing_prompt(self):
        crosser_account = AccountFactory()
        entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=crosser_account),
            end_date=None,
        )
        SceneGMParticipationFactory(scene=self.scene, account=crosser_account)

        offer = self._offer()
        offer.refresh_from_db()
        self.assertFalse(offer.manifestation_withheld)
        self.assertTrue(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).exists()
        )

        self._cross(offer)
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.CROSSING).exists())
        self.assertTrue(
            Interaction.objects.filter(content="tier vision", mode=InteractionMode.WHISPER).exists()
        )

    # -------------------------------------------------------------------
    # Fix round 2 (M6 gaps): DatabaseError fallback; decline racing a cross
    # -------------------------------------------------------------------

    def test_routing_database_error_falls_back_to_unprompted_delivery_once(self):
        """#4101 fix round 2, must-fix 2/3: a DatabaseError while creating GM
        prompts falls back to unprompted delivery -- both lines still arrive,
        exactly once, and no GMPrompt is left behind (no orphan)."""
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        with mock.patch(
            "world.gm.prompt_services.route_narratable_event", side_effect=DatabaseError("boom")
        ):
            self._cross(offer)
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.CROSSING).exists())
        self.assertEqual(
            Interaction.objects.filter(content="tier room", mode=InteractionMode.EMIT).count(), 1
        )
        self.assertEqual(
            Interaction.objects.filter(content="tier vision", mode=InteractionMode.WHISPER).count(),
            1,
        )

    def test_crossing_with_no_active_scene_falls_back_to_offers_own_scene(self):
        """#4101 fix round 2, should-fix 5: the scene has ended (and its GM
        left) between gate-open and the crossing resolving -- the withheld
        manifestation and vision still deliver, recorded against the offer's
        own captured scene, never silently dropped."""
        participation = SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)

        participation.left_at = participation.joined_at
        participation.save()
        self.scene.is_active = False
        self.scene.save()

        self._cross(offer)

        self.assertTrue(
            Interaction.objects.filter(
                content="tier room", mode=InteractionMode.EMIT, scene=self.scene
            ).exists()
        )
        self.assertTrue(
            Interaction.objects.filter(content="tier vision", mode=InteractionMode.WHISPER).exists()
        )
        self.assertFalse(GMPrompt.objects.filter(kind=GMPromptKind.CROSSING).exists())

    def test_decline_racing_a_concurrent_accept_is_a_no_op(self):
        """#4101 fix round 2, should-fix 4: a decline racing a concurrent
        accept (which already deleted the offer under its own lock) must not
        re-release the manifestation -- the locked re-fetch finds nothing."""
        SceneGMParticipationFactory(scene=self.scene, account=self.gm)
        offer = self._offer()
        offer.refresh_from_db()
        self.assertTrue(offer.manifestation_withheld)
        offer_id = offer.pk
        # Simulate a concurrent accept having already consumed (and deleted)
        # the offer under its own lock, between this decline's initial lookup
        # and its own locked release-and-delete call.
        offer.delete()

        from world.magic.audere_majora import release_and_delete_withheld_offer

        with self.captureOnCommitCallbacks(execute=True):
            release_and_delete_withheld_offer(offer_id)

        self.assertFalse(Interaction.objects.filter(content="tier room").exists())
