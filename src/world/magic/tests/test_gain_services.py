"""Tests for Spec C gain service functions."""

from django.test import TestCase


class TagRoomResonanceTests(TestCase):
    def test_creates_aura_profile_if_missing(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomAuraProfile, RoomResonance
        from world.magic.services.gain import tag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        self.assertFalse(hasattr(rp, "room_aura_profile") and rp.room_aura_profile is not None)

        tag = tag_room_resonance(rp, res)

        self.assertTrue(RoomAuraProfile.objects.filter(room_profile=rp).exists())
        self.assertIsInstance(tag, RoomResonance)
        self.assertEqual(tag.resonance, res)

    def test_idempotent_on_duplicate(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomResonance
        from world.magic.services.gain import tag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        t1 = tag_room_resonance(rp, res)
        t2 = tag_room_resonance(rp, res)
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(RoomResonance.objects.count(), 1)


class UntagRoomResonanceTests(TestCase):
    def test_untag_removes_row(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.models import RoomResonance
        from world.magic.services.gain import tag_room_resonance, untag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        tag_room_resonance(rp, res)
        self.assertEqual(RoomResonance.objects.count(), 1)
        untag_room_resonance(rp, res)
        self.assertEqual(RoomResonance.objects.count(), 0)

    def test_untag_noop_if_absent(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import ResonanceFactory
        from world.magic.services.gain import untag_room_resonance

        rp = RoomProfileFactory()
        res = ResonanceFactory()
        untag_room_resonance(rp, res)  # should not raise


class SetResidenceTests(TestCase):
    def test_set_residence_stores_fk(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import set_residence

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        set_residence(sheet, rp)
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_residence, rp)

    def test_clear_residence_with_none(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import set_residence

        sheet = CharacterSheetFactory()
        set_residence(sheet, RoomProfileFactory())
        set_residence(sheet, None)
        sheet.refresh_from_db()
        self.assertIsNone(sheet.current_residence)


class GetResidenceResonancesTests(TestCase):
    def test_empty_when_no_residence(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import get_residence_resonances

        sheet = CharacterSheetFactory()
        self.assertEqual(get_residence_resonances(sheet), set())

    def test_empty_when_residence_has_no_aura_profile(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import get_residence_resonances, set_residence

        sheet = CharacterSheetFactory()
        set_residence(sheet, RoomProfileFactory())
        self.assertEqual(get_residence_resonances(sheet), set())

    def test_returns_intersection_of_tagged_and_claimed(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.magic.services.gain import (
            get_residence_resonances,
            set_residence,
            tag_room_resonance,
        )

        sheet = CharacterSheetFactory()
        rp = RoomProfileFactory()
        r_claimed_and_tagged = ResonanceFactory()
        r_tagged_only = ResonanceFactory()
        r_claimed_only = ResonanceFactory()

        CharacterResonanceFactory(character_sheet=sheet, resonance=r_claimed_and_tagged)
        CharacterResonanceFactory(character_sheet=sheet, resonance=r_claimed_only)

        tag_room_resonance(rp, r_claimed_and_tagged)
        tag_room_resonance(rp, r_tagged_only)

        set_residence(sheet, rp)

        self.assertEqual(get_residence_resonances(sheet), {r_claimed_and_tagged})


class CreatePoseEndorsementTests(TestCase):
    """Covers Spec C §7 preconditions for pose endorsement."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import (
            InteractionFactory,
            PersonaFactory,
            SceneFactory,
            SceneParticipationFactory,
        )

        cls.CharacterSheetFactory = CharacterSheetFactory
        cls.CharacterResonanceFactory = CharacterResonanceFactory
        cls.ResonanceFactory = ResonanceFactory
        cls.RosterTenureFactory = RosterTenureFactory
        cls.InteractionFactory = InteractionFactory
        cls.PersonaFactory = PersonaFactory
        cls.SceneFactory = SceneFactory
        cls.SceneParticipationFactory = SceneParticipationFactory

    def _build_scenario(self, *, same_account: bool = False):
        """Build a standard endorsement scenario.

        Returns: (endorser_sheet, endorsee_sheet, scene, interaction, resonance)

        Interaction is authored by endorsee's primary persona (field: persona).
        Endorser is a scene participant via SceneParticipation.
        """
        from world.magic.services.gain import account_for_sheet

        if same_account:
            endorser_tenure = self.RosterTenureFactory()
            endorser_sheet = endorser_tenure.roster_entry.character_sheet
            endorsee_tenure = self.RosterTenureFactory(
                player_data=endorser_tenure.player_data,
            )
            endorsee_sheet = endorsee_tenure.roster_entry.character_sheet
        else:
            endorser_tenure = self.RosterTenureFactory()
            endorser_sheet = endorser_tenure.roster_entry.character_sheet
            endorsee_tenure = self.RosterTenureFactory()
            endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        scene = self.SceneFactory()
        endorser_account = account_for_sheet(endorser_sheet)
        if endorser_account is not None:
            self.SceneParticipationFactory(scene=scene, account=endorser_account)

        # CharacterSheetFactory already creates a PRIMARY persona (post_generation hook).
        # Fetch it directly — do NOT create a second PRIMARY, the unique constraint forbids it.
        endorsee_persona = endorsee_sheet.primary_persona
        # endorser also has a primary persona created by CharacterSheetFactory
        # (used by _endorser_was_present grid branch — nothing to create here)

        resonance = self.ResonanceFactory()
        self.CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)

        # Interaction is authored by endorsee's primary persona via the `persona` field
        interaction = self.InteractionFactory(scene=scene, persona=endorsee_persona)
        return endorser_sheet, endorsee_sheet, scene, interaction, resonance

    def test_happy_path(self) -> None:
        from world.magic.models import PoseEndorsement
        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, resonance = self._build_scenario()
        endorsement = create_pose_endorsement(endorser, interaction, resonance)

        self.assertIsInstance(endorsement, PoseEndorsement)
        self.assertIsNone(endorsement.settled_at)
        self.assertEqual(endorsement.endorser_sheet, endorser)
        self.assertEqual(endorsement.resonance, resonance)

    def test_blocks_self_endorsement(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement
        from world.scenes.constants import PersonaType
        from world.scenes.models import Persona

        endorser, _, _, interaction, resonance = self._build_scenario()
        # Re-author the interaction by the endorser themselves
        endorser_persona = Persona.objects.get(
            character_sheet=endorser, persona_type=PersonaType.PRIMARY
        )
        interaction.persona = endorser_persona
        interaction.save(update_fields=["persona"])

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)

    def test_blocks_alt_endorsement(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, resonance = self._build_scenario(same_account=True)
        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)

    def test_blocks_whisper(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement
        from world.scenes.constants import InteractionMode

        endorser, _, _, interaction, resonance = self._build_scenario()
        interaction.mode = InteractionMode.WHISPER
        interaction.save(update_fields=["mode"])

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)

    def test_blocks_very_private(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement
        from world.scenes.constants import InteractionVisibility

        endorser, _, _, interaction, resonance = self._build_scenario()
        interaction.visibility = InteractionVisibility.VERY_PRIVATE
        interaction.save(update_fields=["visibility"])

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)

    def test_blocks_non_participant(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import account_for_sheet, create_pose_endorsement
        from world.scenes.models import SceneParticipation

        endorser, _, scene, interaction, resonance = self._build_scenario()
        endorser_account = account_for_sheet(endorser)
        SceneParticipation.objects.filter(scene=scene, account=endorser_account).delete()

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)

    def test_blocks_unclaimed_resonance(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, _ = self._build_scenario()
        fresh_resonance = self.ResonanceFactory()

        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, fresh_resonance)

    def test_blocks_duplicate(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, resonance = self._build_scenario()
        create_pose_endorsement(endorser, interaction, resonance)
        with self.assertRaises(EndorsementValidationError):
            create_pose_endorsement(endorser, interaction, resonance)
