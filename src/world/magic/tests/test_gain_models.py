"""Tests for Spec C gain models."""

from django.test import TestCase

from world.magic.models import ResonanceGainConfig
from world.magic.services.gain import get_resonance_gain_config


class ResonanceGainConfigTests(TestCase):
    def test_singleton_lazy_create(self) -> None:
        """get_resonance_gain_config creates the row on first call."""
        self.assertFalse(ResonanceGainConfig.objects.exists())
        cfg = get_resonance_gain_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(ResonanceGainConfig.objects.count(), 1)

    def test_singleton_idempotent(self) -> None:
        cfg1 = get_resonance_gain_config()
        cfg2 = get_resonance_gain_config()
        self.assertEqual(cfg1.pk, cfg2.pk)
        self.assertEqual(ResonanceGainConfig.objects.count(), 1)

    def test_default_values(self) -> None:
        cfg = get_resonance_gain_config()
        self.assertEqual(cfg.weekly_pot_per_character, 20)
        self.assertEqual(cfg.scene_entry_grant, 4)
        self.assertEqual(cfg.residence_daily_trickle_per_resonance, 1)
        self.assertEqual(cfg.outfit_daily_trickle_per_item_resonance, 1)
        self.assertEqual(cfg.same_pair_daily_cap, 0)
        self.assertEqual(cfg.settlement_day_of_week, 0)


class AccountForSheetTests(TestCase):
    def test_returns_none_for_sheet_without_tenure(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.services.gain import account_for_sheet

        sheet = CharacterSheetFactory()
        # Sheet is freshly created; no RosterEntry/RosterTenure bound.
        self.assertIsNone(account_for_sheet(sheet))

    def test_returns_account_for_played_sheet(self) -> None:
        from world.magic.services.gain import account_for_sheet
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        self.assertEqual(account_for_sheet(sheet), tenure.player_data.account)


class RoomAuraProfileTests(TestCase):
    def test_onetoone_to_room_profile(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.magic.models import RoomAuraProfile

        rp = RoomProfileFactory()
        aura = RoomAuraProfile.objects.create(room_profile=rp)
        self.assertEqual(aura.pk, rp.pk)
        self.assertEqual(rp.room_aura_profile, aura)


class RoomResonanceTests(TestCase):
    def test_tag_is_unique_per_profile_resonance(self) -> None:
        from django.db import IntegrityError

        from world.magic.factories import (
            ResonanceFactory,
            RoomAuraProfileFactory,
        )
        from world.magic.models import RoomResonance

        aura = RoomAuraProfileFactory()
        res = ResonanceFactory()
        RoomResonance.objects.create(room_aura_profile=aura, resonance=res)
        with self.assertRaises(IntegrityError):
            RoomResonance.objects.create(room_aura_profile=aura, resonance=res)

    def test_multiple_resonances_per_profile(self) -> None:
        from world.magic.factories import (
            ResonanceFactory,
            RoomAuraProfileFactory,
        )
        from world.magic.models import RoomResonance

        aura = RoomAuraProfileFactory()
        r1 = ResonanceFactory()
        r2 = ResonanceFactory()
        RoomResonance.objects.create(room_aura_profile=aura, resonance=r1)
        RoomResonance.objects.create(room_aura_profile=aura, resonance=r2)
        self.assertEqual(aura.room_resonances.count(), 2)


class ResonanceGrantTests(TestCase):
    def test_residence_grant_row_shape(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import ResonanceFactory, RoomAuraProfileFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        aura = RoomAuraProfileFactory()

        grant = ResonanceGrant.objects.create(
            character_sheet=sheet,
            resonance=res,
            amount=1,
            source=GainSource.ROOM_RESIDENCE,
            source_room_aura_profile=aura,
        )
        self.assertEqual(grant.amount, 1)
        self.assertEqual(grant.source, GainSource.ROOM_RESIDENCE)

    def test_residence_grant_requires_aura_profile_fk(self) -> None:
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import ResonanceFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=1,
                source=GainSource.ROOM_RESIDENCE,
                # missing source_room_aura_profile
            )

    def test_staff_grant_accepts_null_account(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import ResonanceFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        grant = ResonanceGrant.objects.create(
            character_sheet=sheet,
            resonance=res,
            amount=5,
            source=GainSource.STAFF_GRANT,
            source_staff_account=None,
        )
        self.assertIsNone(grant.source_staff_account)


class PoseEndorsementTests(TestCase):
    def test_unique_endorser_interaction(self) -> None:
        from django.db import IntegrityError

        from world.magic.factories import (
            PoseEndorsementFactory,
            ResonanceFactory,
        )

        first = PoseEndorsementFactory()
        with self.assertRaises(IntegrityError):
            PoseEndorsementFactory(
                endorser_sheet=first.endorser_sheet,
                interaction=first.interaction,
                resonance=ResonanceFactory(),
            )

    def test_settled_at_defaults_none(self) -> None:
        from world.magic.factories import PoseEndorsementFactory

        endorsement = PoseEndorsementFactory()
        self.assertIsNone(endorsement.settled_at)
        self.assertIsNone(endorsement.granted_amount)

    def test_related_name_access(self) -> None:
        """Confirm `interaction.endorsements` related manager works."""
        from world.magic.factories import PoseEndorsementFactory

        endorsement = PoseEndorsementFactory()
        self.assertIn(endorsement, endorsement.interaction.endorsements.all())


class ResonanceGrantPoseEndorsementShapeTests(TestCase):
    def test_pose_endorsement_grant_requires_fk(self) -> None:
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import ResonanceFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=3,
                source=GainSource.POSE_ENDORSEMENT,
                # missing source_pose_endorsement
            )

    def test_pose_endorsement_grant_happy_path(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            PoseEndorsementFactory,
            ResonanceFactory,
        )
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        endorsement = PoseEndorsementFactory(endorsee_sheet=sheet, resonance=res)

        grant = ResonanceGrant.objects.create(
            character_sheet=sheet,
            resonance=res,
            amount=4,
            source=GainSource.POSE_ENDORSEMENT,
            source_pose_endorsement=endorsement,
        )
        self.assertEqual(grant.source_pose_endorsement, endorsement)

    def test_residence_rejects_pose_fk(self) -> None:
        """ROOM_RESIDENCE source must NOT have source_pose_endorsement set."""
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            PoseEndorsementFactory,
            ResonanceFactory,
            RoomAuraProfileFactory,
        )
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        aura = RoomAuraProfileFactory()
        endorsement = PoseEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=1,
                source=GainSource.ROOM_RESIDENCE,
                source_room_aura_profile=aura,
                source_pose_endorsement=endorsement,  # forbidden
            )


class SceneEntryEndorsementTests(TestCase):
    def test_unique_pair_per_scene(self) -> None:
        from django.db import IntegrityError

        from world.magic.factories import (
            ResonanceFactory,
            SceneEntryEndorsementFactory,
        )

        first = SceneEntryEndorsementFactory()
        with self.assertRaises(IntegrityError):
            SceneEntryEndorsementFactory(
                endorser_sheet=first.endorser_sheet,
                endorsee_sheet=first.endorsee_sheet,
                scene=first.scene,
                resonance=ResonanceFactory(),
            )

    def test_factory_produces_valid_row(self) -> None:
        from world.magic.factories import SceneEntryEndorsementFactory

        ep = SceneEntryEndorsementFactory()
        self.assertIsNotNone(ep.granted_amount)
        self.assertIsNotNone(ep.scene)
        self.assertIsNotNone(ep.endorser_sheet)
        self.assertIsNotNone(ep.endorsee_sheet)

    def test_related_name_access(self) -> None:
        """Confirm `scene.entry_endorsements` related manager works."""
        from world.magic.factories import SceneEntryEndorsementFactory

        ep = SceneEntryEndorsementFactory()
        self.assertIn(ep, ep.scene.entry_endorsements.all())


class ResonanceGrantSceneEntryShapeTests(TestCase):
    def test_scene_entry_grant_requires_fk(self) -> None:
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import ResonanceFactory
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=4,
                source=GainSource.SCENE_ENTRY,
                # missing source_scene_entry_endorsement
            )

    def test_scene_entry_grant_happy_path(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            ResonanceFactory,
            SceneEntryEndorsementFactory,
        )
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        endorsement = SceneEntryEndorsementFactory(endorsee_sheet=sheet, resonance=res)

        grant = ResonanceGrant.objects.create(
            character_sheet=sheet,
            resonance=res,
            amount=4,
            source=GainSource.SCENE_ENTRY,
            source_scene_entry_endorsement=endorsement,
        )
        self.assertEqual(grant.source_scene_entry_endorsement, endorsement)

    def test_residence_rejects_scene_entry_fk(self) -> None:
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            ResonanceFactory,
            RoomAuraProfileFactory,
            SceneEntryEndorsementFactory,
        )
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        aura = RoomAuraProfileFactory()
        endorsement = SceneEntryEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=1,
                source=GainSource.ROOM_RESIDENCE,
                source_room_aura_profile=aura,
                source_scene_entry_endorsement=endorsement,  # forbidden
            )

    def test_pose_endorsement_rejects_scene_entry_fk(self) -> None:
        from django.db import IntegrityError

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.constants import GainSource
        from world.magic.factories import (
            PoseEndorsementFactory,
            ResonanceFactory,
            SceneEntryEndorsementFactory,
        )
        from world.magic.models import ResonanceGrant

        sheet = CharacterSheetFactory()
        res = ResonanceFactory()
        pose_ep = PoseEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        entry_ep = SceneEntryEndorsementFactory(endorsee_sheet=sheet, resonance=res)
        with self.assertRaises(IntegrityError):
            ResonanceGrant.objects.create(
                character_sheet=sheet,
                resonance=res,
                amount=1,
                source=GainSource.POSE_ENDORSEMENT,
                source_pose_endorsement=pose_ep,
                source_scene_entry_endorsement=entry_ep,  # forbidden
            )
