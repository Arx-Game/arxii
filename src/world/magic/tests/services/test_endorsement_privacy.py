"""Tests for the updated WHISPER / VERY_PRIVATE rules and get_endorseable_poses_in_scene()."""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.exceptions import EndorsementValidationError
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.services.gain import (
    create_pose_endorsement,
    get_endorseable_poses_in_scene,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.place_models import InteractionReceiver


def _char_with_account(room=None):
    char = CharacterFactory()
    if room is not None:
        char.location = room
        char.save()
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return char, sheet, tenure.player_data.account


class WhisperEndorsementTests(TestCase):
    """WHISPER interactions: only endorseable by the direct recipient."""

    def setUp(self):
        idmapper_models.flush_cache()
        from evennia.objects.models import ObjectDB

        self.room = ObjectDB.objects.create(
            db_key="TestRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.endorser_char, self.endorser_sheet, self.endorser_account = _char_with_account()
        self.endorsee_char, self.endorsee_sheet, self.endorsee_account = _char_with_account()

        SceneParticipationFactory(scene=self.scene, account=self.endorser_account)
        SceneParticipationFactory(scene=self.scene, account=self.endorsee_account)

        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.endorsee_sheet, resonance=self.resonance)

        self.whisper = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_whisper_blocked_without_receiver_row(self):
        with self.assertRaises(EndorsementValidationError) as ctx:
            create_pose_endorsement(self.endorser_sheet, self.whisper, self.resonance)
        self.assertIn("recipient", ctx.exception.user_message.lower())

    def test_whisper_allowed_with_receiver_row(self):
        from world.magic.models import PoseEndorsement

        InteractionReceiver.objects.create(
            interaction=self.whisper,
            timestamp=self.whisper.timestamp,
            persona=self.endorser_sheet.primary_persona,
            account=self.endorser_account,
        )
        result = create_pose_endorsement(self.endorser_sheet, self.whisper, self.resonance)
        self.assertIsNotNone(result.pk)
        self.assertEqual(PoseEndorsement.objects.count(), 1)


class VeryPrivateEndorsementTests(TestCase):
    """VERY_PRIVATE interactions: endorseable by scene participants (not blanket-blocked)."""

    def setUp(self):
        idmapper_models.flush_cache()
        from evennia.objects.models import ObjectDB

        self.room = ObjectDB.objects.create(
            db_key="TestRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.endorser_char, self.endorser_sheet, self.endorser_account = _char_with_account()
        self.endorsee_char, self.endorsee_sheet, self.endorsee_account = _char_with_account()
        self.outsider_char, self.outsider_sheet, _ = _char_with_account()

        SceneParticipationFactory(scene=self.scene, account=self.endorser_account)
        SceneParticipationFactory(scene=self.scene, account=self.endorsee_account)
        # outsider has NO participation

        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.endorsee_sheet, resonance=self.resonance)

        self.vp_pose = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.VERY_PRIVATE,
        )

    def test_very_private_allowed_for_participant(self):
        from world.magic.models import PoseEndorsement

        result = create_pose_endorsement(self.endorser_sheet, self.vp_pose, self.resonance)
        self.assertIsNotNone(result.pk)
        self.assertEqual(PoseEndorsement.objects.count(), 1)

    def test_very_private_blocked_for_non_participant(self):
        with self.assertRaises(EndorsementValidationError) as ctx:
            create_pose_endorsement(self.outsider_sheet, self.vp_pose, self.resonance)
        self.assertIn("not present", ctx.exception.user_message.lower())


class GetEndorseablePosesTests(TestCase):
    """get_endorseable_poses_in_scene: stable numbering, privacy filtering."""

    def setUp(self):
        idmapper_models.flush_cache()
        from evennia.objects.models import ObjectDB

        self.room = ObjectDB.objects.create(
            db_key="TestRoom3", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.endorser_char, self.endorser_sheet, self.endorser_account = _char_with_account()
        self.endorsee_char, self.endorsee_sheet, self.endorsee_account = _char_with_account()

        SceneParticipationFactory(scene=self.scene, account=self.endorser_account)
        SceneParticipationFactory(scene=self.scene, account=self.endorsee_account)

        # Three poses: regular, whisper, regular
        self.pose1 = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        self.whisper = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.WHISPER,
            visibility=InteractionVisibility.DEFAULT,
        )
        self.pose3 = InteractionFactory(
            scene=self.scene,
            persona=self.endorsee_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )

    def test_regular_poses_visible_to_participant(self):
        result = get_endorseable_poses_in_scene(
            self.endorser_sheet, self.endorsee_sheet, self.scene
        )
        # pose1 = #1, whisper hidden = #2 (absent), pose3 = #3
        positions = [n for n, _ in result]
        self.assertIn(1, positions)
        self.assertIn(3, positions)
        # whisper not visible (no receiver row)
        self.assertNotIn(2, positions)

    def test_stable_numbers_skip_invisible(self):
        """Pose3 is #3 even when pose2 (whisper) is invisible."""
        result = get_endorseable_poses_in_scene(
            self.endorser_sheet, self.endorsee_sheet, self.scene
        )
        id_by_pos = {n: iact.pk for n, iact in result}
        self.assertEqual(id_by_pos.get(3), self.pose3.pk)

    def test_whisper_visible_to_receiver(self):
        InteractionReceiver.objects.create(
            interaction=self.whisper,
            timestamp=self.whisper.timestamp,
            persona=self.endorser_sheet.primary_persona,
            account=self.endorser_account,
        )
        result = get_endorseable_poses_in_scene(
            self.endorser_sheet, self.endorsee_sheet, self.scene
        )
        positions = [n for n, _ in result]
        self.assertIn(2, positions)
        self.assertEqual(len(result), 3)  # all three now visible
