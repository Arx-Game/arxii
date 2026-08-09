"""Journey tests for the guarded beta-reset wipe service (#3055 PR 2).

Exercises the service layer directly (not the management command binary — see
``test_command.py`` for the thin command-layer argument-gating test).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.achievements.factories import CharacterAchievementFactory, DiscoveryFactory
from world.achievements.models import CharacterAchievement, Discovery
from world.beta_reset.exceptions import (
    AlreadyReleasedError,
    BackupNotVerifiedError,
    BetaResetDisabledError,
    ConfirmationPhraseMismatchError,
    ReleaseLatchedError,
)
from world.beta_reset.models import ReleaseLatch
from world.beta_reset.services import (
    CONFIRMATION_PHRASE,
    mark_released,
    wipe_pristine_world,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory
from world.combat.models import CombatEncounter
from world.currency.models import CharacterPurse, CurrencyTransfer
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.gm.factories import GMProfileFactory
from world.journals.factories import JournalEntryFactory, WeeklyJournalXPFactory
from world.journals.models import JournalEntry, WeeklyJournalXP
from world.magic.constants import AcquisitionOrigin
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique
from world.npc_services.factories import NPCStandingFactory
from world.npc_services.models import NPCStanding
from world.progression.factories import CharacterXPTransactionFactory
from world.progression.models import CharacterXPTransaction
from world.scenes.models import Scene
from world.secrets.factories import SecretFactory
from world.secrets.models import Secret
from world.societies.factories import LegendEntryFactory
from world.societies.models import LegendEntry
from world.traits.factories import TraitFactory
from world.traits.models import CharacterTraitChange, TraitChangeSource


def _seed_pristine_world():
    """Build one small world: a play-provenance row AND a CG-provenance row per ledger.

    Returns a dict of the seeded rows, keyed by a short label, so tests can assert on
    them individually.
    """
    sheet = CharacterSheetFactory()

    play_technique = CharacterTechniqueFactory(
        character=sheet, technique=TechniqueFactory(), origin=AcquisitionOrigin.TRAINED
    )
    cg_technique = CharacterTechniqueFactory(
        character=sheet,
        technique=TechniqueFactory(),
        origin=AcquisitionOrigin.CHARACTER_CREATION,
    )
    play_gift = CharacterGiftFactory(
        character=sheet, gift=GiftFactory(), origin=AcquisitionOrigin.PATH_GRANT
    )
    cg_gift = CharacterGiftFactory(
        character=sheet, gift=GiftFactory(), origin=AcquisitionOrigin.CHARACTER_CREATION
    )

    trait = TraitFactory()
    play_trait_change = CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=10,
        new_value=20,
        source=TraitChangeSource.DEVELOPMENT_LEVEL_UP,
    )
    cg_trait_change = CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=0,
        new_value=10,
        source=TraitChangeSource.CHARACTER_CREATION,
    )

    play_distinction = CharacterDistinctionFactory(
        character=sheet,
        distinction=DistinctionFactory(),
        origin=DistinctionOrigin.GAMEPLAY,
    )
    cg_distinction = CharacterDistinctionFactory(
        character=sheet,
        distinction=DistinctionFactory(),
        origin=DistinctionOrigin.CHARACTER_CREATION,
    )

    discovery = DiscoveryFactory()
    achievement = CharacterAchievementFactory(character_sheet=sheet)
    journal_entry = JournalEntryFactory(author=sheet)
    weekly_journal_xp = WeeklyJournalXPFactory(character_sheet=sheet)
    npc_standing = NPCStandingFactory()
    secret = SecretFactory(subject_sheet=sheet)
    xp_transaction = CharacterXPTransactionFactory(character=sheet)
    legend_entry = LegendEntryFactory()
    purse = CharacterPurse.objects.create(character_sheet=sheet, balance=100)
    currency_transfer = CurrencyTransfer.objects.create(
        amount=5, reason="test mint", to_purse=purse
    )
    gm_profile = GMProfileFactory()

    return {
        "sheet": sheet,
        "play_technique": play_technique,
        "cg_technique": cg_technique,
        "play_gift": play_gift,
        "cg_gift": cg_gift,
        "play_trait_change": play_trait_change,
        "cg_trait_change": cg_trait_change,
        "play_distinction": play_distinction,
        "cg_distinction": cg_distinction,
        "discovery": discovery,
        "achievement": achievement,
        "journal_entry": journal_entry,
        "weekly_journal_xp": weekly_journal_xp,
        "npc_standing": npc_standing,
        "secret": secret,
        "xp_transaction": xp_transaction,
        "legend_entry": legend_entry,
        "purse": purse,
        "currency_transfer": currency_transfer,
        "gm_profile": gm_profile,
    }


class PristineWorldWipeJourneyTests(TestCase):
    """The full execute path: play-provenance gone, CG/authoring + accounts intact."""

    def test_execute_strips_play_state_and_preserves_cg_authoring_and_accounts(self) -> None:
        world = _seed_pristine_world()

        report = wipe_pristine_world(
            execute=True,
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now(),
        )

        self.assertTrue(report.executed)

        # Play-provenance acquisition-ledger rows: gone.
        self.assertFalse(CharacterTechnique.objects.filter(pk=world["play_technique"].pk).exists())
        self.assertFalse(CharacterGift.objects.filter(pk=world["play_gift"].pk).exists())
        self.assertFalse(
            CharacterTraitChange.objects.filter(pk=world["play_trait_change"].pk).exists()
        )
        self.assertFalse(
            CharacterDistinction.objects.filter(pk=world["play_distinction"].pk).exists()
        )

        # CG/authoring-provenance rows on the SAME ledgers: survive untouched.
        self.assertTrue(CharacterTechnique.objects.filter(pk=world["cg_technique"].pk).exists())
        self.assertTrue(CharacterGift.objects.filter(pk=world["cg_gift"].pk).exists())
        self.assertTrue(
            CharacterTraitChange.objects.filter(pk=world["cg_trait_change"].pk).exists()
        )
        self.assertTrue(CharacterDistinction.objects.filter(pk=world["cg_distinction"].pk).exists())

        # Wholesale play-state tables: gone.
        self.assertEqual(CharacterAchievement.objects.count(), 0)
        self.assertEqual(Discovery.objects.count(), 0)
        self.assertEqual(JournalEntry.objects.count(), 0)
        self.assertEqual(WeeklyJournalXP.objects.count(), 0)
        self.assertEqual(NPCStanding.objects.count(), 0)
        self.assertEqual(Secret.objects.count(), 0)
        self.assertEqual(CharacterXPTransaction.objects.count(), 0)
        self.assertEqual(LegendEntry.objects.count(), 0)
        self.assertEqual(CurrencyTransfer.objects.count(), 0)
        self.assertEqual(CharacterPurse.objects.count(), 0)

        # Accounts / GM infrastructure / kudos: never touched by this command at all.
        self.assertTrue(
            world["gm_profile"].__class__.objects.filter(pk=world["gm_profile"].pk).exists()
        )
        self.assertTrue(world["sheet"].__class__.objects.filter(pk=world["sheet"].pk).exists())


class DryRunTests(TestCase):
    """Dry-run (the default) destroys nothing and reports accurate counts."""

    def test_dry_run_destroys_nothing_and_reports_counts(self) -> None:
        world = _seed_pristine_world()

        report = wipe_pristine_world()  # default: execute=False

        self.assertFalse(report.executed)
        self.assertGreater(report.total, 0)

        # Nothing was touched — every seeded row is still present.
        self.assertTrue(CharacterTechnique.objects.filter(pk=world["play_technique"].pk).exists())
        self.assertTrue(CharacterGift.objects.filter(pk=world["play_gift"].pk).exists())
        self.assertTrue(Discovery.objects.filter(pk=world["discovery"].pk).exists())
        self.assertTrue(NPCStanding.objects.filter(pk=world["npc_standing"].pk).exists())
        self.assertTrue(Secret.objects.filter(pk=world["secret"].pk).exists())

        # Counts line up with what execute=True would actually report deleting.
        counts_by_label = {c.label: c.would_delete for c in report.counts}
        self.assertEqual(counts_by_label["Discovery"], 1)
        self.assertEqual(counts_by_label["NPCStanding"], 1)
        # Provenance-filtered: only the play-time row counts, not the CG one.
        self.assertEqual(counts_by_label["CharacterTechnique"], 1)

    def test_execute_false_with_no_guards_supplied_is_still_a_pure_dry_run(self) -> None:
        """Calling with execute=False (the implicit default) never even checks the guards."""
        report = wipe_pristine_world(execute=False, confirm=None, backup_verified_at=None)
        self.assertFalse(report.executed)


class ReleaseLatchGuardTests(TestCase):
    """The one-way ReleaseLatch blocks execution, independent of the phrase/backup guards."""

    def test_latch_present_blocks_execution_and_nothing_is_deleted(self) -> None:
        world = _seed_pristine_world()
        account = AccountFactory()
        ReleaseLatch.objects.create(released_by=account)

        with self.assertRaises(ReleaseLatchedError):
            wipe_pristine_world(
                execute=True,
                confirm=CONFIRMATION_PHRASE,
                backup_verified_at=timezone.now(),
            )

        self.assertTrue(CharacterTechnique.objects.filter(pk=world["play_technique"].pk).exists())
        self.assertEqual(Discovery.objects.count(), 1)

    def test_mark_released_refuses_a_second_row(self) -> None:
        account = AccountFactory()
        mark_released(released_by=account)

        with self.assertRaises(AlreadyReleasedError):
            mark_released(released_by=account)

        self.assertEqual(ReleaseLatch.objects.count(), 1)


class ConfirmationAndBackupGuardTests(TestCase):
    """Refusal paths: wrong/missing phrase, missing/stale backup timestamp, disabled constant."""

    def test_refuses_without_the_exact_phrase(self) -> None:
        world = _seed_pristine_world()

        with self.assertRaises(ConfirmationPhraseMismatchError):
            wipe_pristine_world(
                execute=True,
                confirm="close enough",
                backup_verified_at=timezone.now(),
            )

        self.assertEqual(Discovery.objects.filter(pk=world["discovery"].pk).count(), 1)

    def test_refuses_with_no_phrase_supplied(self) -> None:
        with self.assertRaises(ConfirmationPhraseMismatchError):
            wipe_pristine_world(execute=True, confirm=None, backup_verified_at=timezone.now())

    def test_refuses_without_a_backup_timestamp(self) -> None:
        with self.assertRaises(BackupNotVerifiedError):
            wipe_pristine_world(execute=True, confirm=CONFIRMATION_PHRASE, backup_verified_at=None)

    def test_refuses_with_a_stale_backup_timestamp(self) -> None:
        stale = timezone.now() - timezone.timedelta(hours=48)
        with self.assertRaises(BackupNotVerifiedError):
            wipe_pristine_world(execute=True, confirm=CONFIRMATION_PHRASE, backup_verified_at=stale)

    def test_refuses_when_the_hardcoded_constant_is_disabled(self) -> None:
        with mock.patch("world.beta_reset.services.BETA_RESET_ENABLED", False):
            with self.assertRaises(BetaResetDisabledError):
                wipe_pristine_world(
                    execute=True,
                    confirm=CONFIRMATION_PHRASE,
                    backup_verified_at=timezone.now(),
                )


class ProtectOrderingTests(TestCase):
    """PROTECT-constraint landmines the scope table must resolve in order."""

    def test_npc_standing_present_does_not_block_the_wipe(self) -> None:
        standing = NPCStandingFactory()

        report = wipe_pristine_world(
            execute=True,
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now(),
        )

        self.assertTrue(report.executed)
        self.assertFalse(NPCStanding.objects.filter(pk=standing.pk).exists())

    def test_combat_encounter_does_not_block_the_scene_wipe(self) -> None:
        """CombatEncounter.scene is PROTECT against scenes.Scene.

        Deleting Scene before CombatEncounter would raise ProtectedError; the scope
        table lists CombatEncounter ahead of Scene specifically to prevent that.
        """
        encounter = CombatEncounterFactory()
        scene_pk = encounter.scene_id

        report = wipe_pristine_world(
            execute=True,
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now(),
        )

        self.assertTrue(report.executed)
        self.assertFalse(CombatEncounter.objects.filter(pk=encounter.pk).exists())
        self.assertFalse(Scene.objects.filter(pk=scene_pk).exists())
