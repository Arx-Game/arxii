"""Unit tests for PoseEndorseAction, SceneEntryEndorseAction, StylePresentationEndorseAction."""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.endorsements import PoseEndorseAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import InteractionFactory, SceneFactory, SceneParticipationFactory


def _char_with_account():
    char = CharacterFactory()
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return char, sheet, tenure.player_data.account


class PoseEndorseActionTests(TestCase):
    def setUp(self):
        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.endorser_char, self.endorser_sheet, self.endorser_account = _char_with_account()
        self.endorsee_char, self.endorsee_sheet, self.endorsee_account = _char_with_account()

        SceneParticipationFactory(scene=self.scene, account=self.endorser_account)
        SceneParticipationFactory(scene=self.scene, account=self.endorsee_account)

        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.endorsee_sheet, resonance=self.resonance)
        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_preview_returns_pose_text_no_db_row(self):
        from world.magic.models import PoseEndorsement

        result = PoseEndorseAction().run(
            actor=self.endorser_char,
            interaction=self.pose,
            resonance=self.resonance,
            confirm=False,
        )
        self.assertTrue(result.success)
        self.assertTrue(result.data.get("preview"))
        self.assertIn(self.pose.content[:20], result.message)
        self.assertEqual(PoseEndorsement.objects.count(), 0)

    def test_confirm_creates_endorsement(self):
        from world.magic.models import PoseEndorsement

        result = PoseEndorseAction().run(
            actor=self.endorser_char,
            interaction=self.pose,
            resonance=self.resonance,
            confirm=True,
        )
        self.assertTrue(result.success)
        self.assertIn("endorsement", result.data)
        self.assertEqual(PoseEndorsement.objects.count(), 1)

    def test_confirm_fails_without_participation(self):
        other_char, _other_sheet, _ = _char_with_account()
        result = PoseEndorseAction().run(
            actor=other_char,
            interaction=self.pose,
            resonance=self.resonance,
            confirm=True,
        )
        self.assertFalse(result.success)
        self.assertIn("not present", result.message.lower())
