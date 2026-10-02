"""The Crossing as a narratable event (#4101 Task 6; spec scenarios 1-2)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.magic.factories import CharacterCrossingTextFactory
from world.magic.models.prepared_text import CharacterCrossingText
from world.magic.serializers import PendingAudereMajoraOfferSerializer
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
