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


class SettleWeeklyPotTests(TestCase):
    def _make_unsettled(self, endorser_sheet, count):
        """Helper: create `count` unsettled PoseEndorsements by endorser_sheet.

        Each endorsement has a distinct interaction + endorsee + resonance.
        Endorsees claim the resonance so the ledger write passes FK checks.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            PoseEndorsementFactory,
            ResonanceFactory,
        )
        from world.scenes.factories import InteractionFactory

        endorsements = []
        for _ in range(count):
            endorsee = CharacterSheetFactory()
            resonance = ResonanceFactory()
            CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
            interaction = InteractionFactory()
            ep = PoseEndorsementFactory(
                endorser_sheet=endorser_sheet,
                endorsee_sheet=endorsee,
                interaction=interaction,
                resonance=resonance,
            )
            endorsements.append(ep)
        return endorsements

    def test_noop_when_no_unsettled(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import settle_weekly_pot

        sheet = CharacterSheetFactory()
        result = settle_weekly_pot(sheet)
        self.assertEqual(result.endorsements_settled, 0)
        self.assertEqual(result.total_granted, 0)

    def test_divides_pot_ceil(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import (
            get_resonance_gain_config,
            settle_weekly_pot,
        )

        endorser = CharacterSheetFactory()
        self._make_unsettled(endorser, 3)
        cfg = get_resonance_gain_config()
        # 3 endorsements, pot=20 → ceil(20/3) = 7 each
        expected_share = -(-cfg.weekly_pot_per_character // 3)  # ceil divide

        result = settle_weekly_pot(endorser)
        self.assertEqual(result.endorsements_settled, 3)
        self.assertEqual(result.total_granted, expected_share * 3)

    def test_writes_ledger_rows(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.models import ResonanceGrant
        from world.magic.services.gain import settle_weekly_pot

        endorser = CharacterSheetFactory()
        self._make_unsettled(endorser, 2)
        settle_weekly_pot(endorser)
        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.POSE_ENDORSEMENT).count(),
            2,
        )

    def test_marks_settled_at(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import settle_weekly_pot

        endorser = CharacterSheetFactory()
        endorsements = self._make_unsettled(endorser, 2)
        settle_weekly_pot(endorser)
        for ep in endorsements:
            ep.refresh_from_db()
            self.assertIsNotNone(ep.settled_at)
            self.assertIsNotNone(ep.granted_amount)

    def test_idempotent_rerun(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import settle_weekly_pot

        endorser = CharacterSheetFactory()
        self._make_unsettled(endorser, 2)
        first = settle_weekly_pot(endorser)
        second = settle_weekly_pot(endorser)
        self.assertEqual(first.endorsements_settled, 2)
        self.assertEqual(second.endorsements_settled, 0)

    def test_settlement_writes_endorsee_balance(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models import CharacterResonance
        from world.magic.services.gain import settle_weekly_pot

        endorser = CharacterSheetFactory()
        endorsements = self._make_unsettled(endorser, 2)
        settle_weekly_pot(endorser)
        # Each endorsee's CharacterResonance.balance should be bumped
        for ep in endorsements:
            cr = CharacterResonance.objects.get(
                character_sheet=ep.endorsee_sheet, resonance=ep.resonance
            )
            self.assertGreater(cr.balance, 0)


class CreateSceneEntryEndorsementTests(TestCase):
    """Covers Spec C §2.3 + §7 preconditions for scene entry endorsement."""

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
            SceneFactory,
            SceneParticipationFactory,
        )

        cls.CharacterSheetFactory = CharacterSheetFactory
        cls.CharacterResonanceFactory = CharacterResonanceFactory
        cls.ResonanceFactory = ResonanceFactory
        cls.RosterTenureFactory = RosterTenureFactory
        cls.SceneFactory = SceneFactory
        cls.SceneParticipationFactory = SceneParticipationFactory
        cls.InteractionFactory = InteractionFactory

    def _build_scenario(self, *, same_account=False, with_entry_pose=True):
        """Build endorser + endorsee + scene + (optional) entry interaction.

        Returns: (endorser_sheet, endorsee_sheet, scene, resonance)
        """
        from world.magic.services.gain import account_for_sheet
        from world.scenes.constants import PoseKind

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

        resonance = self.ResonanceFactory()
        self.CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)

        if with_entry_pose:
            endorsee_persona = endorsee_sheet.primary_persona
            self.InteractionFactory(
                scene=scene,
                persona=endorsee_persona,
                pose_kind=PoseKind.ENTRY,
            )

        return endorser_sheet, endorsee_sheet, scene, resonance

    def test_fires_grant_immediately(self) -> None:
        from world.magic.models import CharacterResonance
        from world.magic.services.gain import (
            create_scene_entry_endorsement,
            get_resonance_gain_config,
        )

        endorser, endorsee, scene, resonance = self._build_scenario()
        create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

        cfg = get_resonance_gain_config()
        cr = CharacterResonance.objects.get(character_sheet=endorsee, resonance=resonance)
        self.assertEqual(cr.balance, cfg.scene_entry_grant)

    def test_writes_ledger_row(self) -> None:
        from world.magic.constants import GainSource
        from world.magic.models import ResonanceGrant
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario()
        create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        self.assertEqual(
            ResonanceGrant.objects.filter(
                source=GainSource.SCENE_ENTRY, character_sheet=endorsee
            ).count(),
            1,
        )

    def test_captures_persona_snapshot(self) -> None:
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario()
        endorsement = create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        self.assertEqual(endorsement.persona_snapshot, endorsee.primary_persona)

    def test_requires_entry_pose(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario(with_entry_pose=False)
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

    def test_once_per_pair_per_scene(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario()
        create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

    def test_blocks_self(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, _, scene, resonance = self._build_scenario()
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorser, scene, resonance)

    def test_blocks_alt(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario(same_account=True)
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

    def test_requires_participation(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import account_for_sheet, create_scene_entry_endorsement

        endorser, endorsee, scene, resonance = self._build_scenario()
        # Wipe scene participation
        scene.participations.filter(account=account_for_sheet(endorser)).delete()
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)

    def test_requires_claimed_resonance(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, _ = self._build_scenario()
        fresh_resonance = self.ResonanceFactory()
        with self.assertRaises(EndorsementValidationError):
            create_scene_entry_endorsement(endorser, endorsee, scene, fresh_resonance)


class ProtagonismLockResonanceGainTests(TestCase):
    """Gate 10.1 — protagonism-locked sheets cannot endorse or receive resonance gains."""

    def _make_subsumed_sheet(self):
        """Return a CharacterSheet at corruption stage 5 (protagonism locked)."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory, with_corruption_at_stage

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        # Bust the cached_property so is_protagonism_locked reflects DB state.
        sheet.__dict__.pop("is_protagonism_locked", None)
        return sheet

    def _make_normal_sheet_with_tenure(self):
        """Return a CharacterSheet with a RosterTenure (has an Account)."""
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        return tenure.roster_entry.character_sheet

    # --- create_pose_endorsement gates ---

    def test_locked_endorser_cannot_endorse_pose(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import create_pose_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
        )

        endorser = self._make_subsumed_sheet()
        endorsee_tenure = RosterTenureFactory()
        endorsee = endorsee_tenure.roster_entry.character_sheet

        scene = SceneFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        interaction = InteractionFactory(scene=scene, persona=endorsee.primary_persona)

        # Ensure endorser has an account so participation check would pass if lock didn't fire
        # (no need — lock fires before participation check)
        with self.assertRaises(EndorsementValidationError) as ctx:
            create_pose_endorsement(endorser, interaction, resonance)
        self.assertIn("locked", ctx.exception.reason.lower())

    def test_locked_endorsee_cannot_receive_pose_endorsement(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import account_for_sheet, create_pose_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
            SceneParticipationFactory,
        )

        endorser_tenure = RosterTenureFactory()
        endorser = endorser_tenure.roster_entry.character_sheet
        endorsee = self._make_subsumed_sheet()

        scene = SceneFactory()
        endorser_account = account_for_sheet(endorser)
        if endorser_account is not None:
            SceneParticipationFactory(scene=scene, account=endorser_account)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        interaction = InteractionFactory(scene=scene, persona=endorsee.primary_persona)

        with self.assertRaises(EndorsementValidationError) as ctx:
            create_pose_endorsement(endorser, interaction, resonance)
        self.assertIn("locked", ctx.exception.reason.lower())

    # --- create_scene_entry_endorsement gates ---

    def test_locked_endorser_cannot_endorse_scene_entry(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import create_scene_entry_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.constants import PoseKind
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
        )

        endorser = self._make_subsumed_sheet()
        endorsee_tenure = RosterTenureFactory()
        endorsee = endorsee_tenure.roster_entry.character_sheet

        scene = SceneFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        InteractionFactory(scene=scene, persona=endorsee.primary_persona, pose_kind=PoseKind.ENTRY)

        with self.assertRaises(EndorsementValidationError) as ctx:
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        self.assertIn("locked", ctx.exception.reason.lower())

    def test_locked_endorsee_cannot_receive_scene_entry_endorsement(self) -> None:
        from world.magic.exceptions import EndorsementValidationError
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.services.gain import account_for_sheet, create_scene_entry_endorsement
        from world.roster.factories import RosterTenureFactory
        from world.scenes.constants import PoseKind
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
            SceneParticipationFactory,
        )

        endorser_tenure = RosterTenureFactory()
        endorser = endorser_tenure.roster_entry.character_sheet
        endorsee = self._make_subsumed_sheet()

        scene = SceneFactory()
        endorser_account = account_for_sheet(endorser)
        if endorser_account is not None:
            SceneParticipationFactory(scene=scene, account=endorser_account)

        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee, resonance=resonance)
        InteractionFactory(scene=scene, persona=endorsee.primary_persona, pose_kind=PoseKind.ENTRY)

        with self.assertRaises(EndorsementValidationError) as ctx:
            create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        self.assertIn("locked", ctx.exception.reason.lower())

    # --- residence_trickle_tick skip ---

    def test_locked_sheet_skipped_in_residence_trickle(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
        from world.magic.models import ResonanceGrant
        from world.magic.services.gain import (
            residence_trickle_tick,
            set_residence,
            tag_room_resonance,
        )

        locked_sheet = self._make_subsumed_sheet()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=locked_sheet, resonance=resonance)
        rp = RoomProfileFactory()
        tag_room_resonance(rp, resonance)
        set_residence(locked_sheet, rp)

        residence_trickle_tick()

        # No grant should have been issued for the locked sheet
        self.assertEqual(
            ResonanceGrant.objects.filter(character_sheet=locked_sheet).count(),
            0,
        )

    # --- settle_weekly_pot skip for locked endorsee ---

    def test_locked_endorsee_skipped_in_weekly_settlement(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            PoseEndorsementFactory,
            ResonanceFactory,
        )
        from world.magic.models import CharacterResonance, ResonanceGrant
        from world.magic.services.gain import settle_weekly_pot
        from world.scenes.factories import InteractionFactory

        endorser = CharacterSheetFactory()
        locked_endorsee = self._make_subsumed_sheet()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=locked_endorsee, resonance=resonance)
        interaction = InteractionFactory()

        ep = PoseEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=locked_endorsee,
            interaction=interaction,
            resonance=resonance,
        )

        result = settle_weekly_pot(endorser)

        # Endorsement should be marked settled (not left pending)
        ep.refresh_from_db()
        self.assertIsNotNone(ep.settled_at)
        self.assertEqual(ep.granted_amount, 0)

        # No resonance grant should exist for the locked endorsee
        self.assertEqual(
            ResonanceGrant.objects.filter(character_sheet=locked_endorsee).count(),
            0,
        )

        # Locked endorsee's balance should remain 0
        cr = CharacterResonance.objects.filter(
            character_sheet=locked_endorsee, resonance=resonance
        ).first()
        if cr:
            self.assertEqual(cr.balance, 0)

        # The settlement result should reflect 1 settled endorsement
        self.assertEqual(result.endorsements_settled, 1)
