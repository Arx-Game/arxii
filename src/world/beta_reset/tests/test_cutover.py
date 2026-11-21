"""The cutover policy layer: roster characters, reserved OCs and carry-over (#3055 PR 3)."""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, EmailAddressFactory
from world.assets.factories import CluePoolEntryFactory
from world.beta_reset.constants import CutoverPolicy
from world.beta_reset.cutover import execute_cutover, plan_cutover, run_beta_cutover
from world.beta_reset.exceptions import (
    BetaResetDisabledError,
    CarryOverError,
    ConfirmationPhraseMismatchError,
    IncompleteLedgerError,
    ReleaseLatchedError,
    WipeBlockedError,
)
from world.beta_reset.models import ReleaseLatch
from world.beta_reset.services import CONFIRMATION_PHRASE
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
from world.items.tests.test_natural_weapon_refusals import clawed_gift
from world.magic.constants import AcquisitionOrigin
from world.magic.factories import CharacterGiftFactory, ThreadFactory
from world.magic.models import CharacterGift
from world.roster.factories import (
    PlayerDataFactory,
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.seeds import ensure_rosters
from world.secrets.factories import SecretFactory
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import CharacterTraitChange, CharacterTraitValue, TraitChangeSource
from world.vitals.factories import CharacterVitalsFactory

LONG_MESSAGE = "I would like to play this character because they seem interesting."


def _raised_stat(sheet, trait, *, authored: int, now: int) -> None:
    """A stat authored at ``authored`` and raised to ``now`` by play."""
    CharacterTraitValueFactory(character=sheet, trait=trait, value=now)
    CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=0,
        new_value=authored,
        source=TraitChangeSource.CHARACTER_CREATION,
    )
    CharacterTraitChange.objects.create(
        character_sheet=sheet,
        trait=trait,
        old_value=authored,
        new_value=now,
        source=TraitChangeSource.DEVELOPMENT_LEVEL_UP,
    )


class CutoverTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_rosters()
        cls.stat = StatTraitFactory(name="cutover_strength")
        cls.tester = AccountFactory()
        cls.tester_data = PlayerDataFactory(account=cls.tester)
        cls.other = AccountFactory()
        cls.other_data = PlayerDataFactory(account=cls.other)
        for account in (cls.tester, cls.other):
            EmailAddressFactory(user=account, email=account.email, verified=True, primary=True)

    def _entry(self, provenance, *, holder=None, author=None, shelf=RosterType.ACTIVE):
        from world.roster.models import Roster

        entry = RosterEntryFactory(
            roster=Roster.objects.get(roster_type=shelf),
            creation_provenance=provenance,
            created_by_account=author,
        )
        if holder is not None:
            RosterTenureFactory(player_data=holder, roster_entry=entry, end_date=None)
        _raised_stat(entry.character_sheet, self.stat, authored=3, now=5)
        return entry

    def _set_value(self, entry, trait, value: int) -> None:
        row = CharacterTraitValue.objects.get(character=entry.character_sheet, trait=trait)
        row.value = value
        row.save()

    def _db_stat(self, entry) -> int | None:
        return CharacterTraitValue.objects.values_list("value", flat=True).get(
            character_id=entry.character_sheet_id, trait=self.stat
        )

    def _stat(self, entry) -> int | None:
        row = CharacterTraitValue.objects.filter(
            character=entry.character_sheet, trait=self.stat
        ).first()
        return None if row is None else row.value

    def _execute(self, **kwargs):
        return run_beta_cutover(
            execute=True,
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now(),
            **kwargs,
        )


class CutoverJourneyTests(CutoverTestBase):
    def test_dry_run_lists_every_step_and_touches_nothing(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        original = self._entry(CreationProvenance.PLAYER, holder=self.other_data, author=self.other)

        report = run_beta_cutover()

        self.assertFalse(report.executed)
        by_policy = {step.policy: step for step in report.plan.steps}
        self.assertEqual(by_policy[CutoverPolicy.ROSTER_CHARACTER].open_tenures, 1)
        self.assertEqual(by_policy[CutoverPolicy.ROSTER_CHARACTER].holder, self.tester.username)
        self.assertEqual(len(by_policy[CutoverPolicy.RESERVED_OC].progress.trait_reverts), 1)
        self.assertEqual(self._stat(roster_char), 5)
        self.assertEqual(self._stat(original), 5)
        self.assertEqual(RosterTenure.objects.filter(end_date__isnull=True).count(), 2)

    def test_execute_releases_resets_and_leaves_accounts_and_other_characters(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        original = self._entry(CreationProvenance.PLAYER, holder=self.other_data, author=self.other)
        unauthored = self._entry(CreationProvenance.PLAYER, holder=self.tester_data)
        story_npc = self._entry(CreationProvenance.STAFF, shelf=RosterType.NPC)

        report = self._execute()

        self.assertTrue(report.executed)
        for entry in (roster_char, original):
            entry.refresh_from_db()
            self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)
            self.assertFalse(entry.tenures.filter(end_date__isnull=True).exists())
            self.assertTrue(entry.tenures.exists())
            self.assertEqual(self._stat(entry), 3)
        self.assertEqual(original.created_by_account_id, self.other.pk)
        # Neither a roster character nor a reserved original: left for the unruled step.
        unauthored.refresh_from_db()
        self.assertEqual(unauthored.roster.roster_type, RosterType.ACTIVE)
        self.assertTrue(unauthored.tenures.filter(end_date__isnull=True).exists())
        story_npc.refresh_from_db()
        self.assertEqual(story_npc.roster.roster_type, RosterType.NPC)
        self.assertEqual(self._stat(story_npc), 5)
        self.tester.refresh_from_db()
        self.assertTrue(type(self.tester).objects.filter(pk=self.tester.pk).exists())

    def test_a_refused_guard_runs_no_policy_step(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)

        with self.assertRaises(ConfirmationPhraseMismatchError):
            run_beta_cutover(execute=True, confirm="nope", backup_verified_at=timezone.now())

        self.assertEqual(self._stat(roster_char), 5)
        self.assertTrue(roster_char.tenures.filter(end_date__isnull=True).exists())


class ReservedOriginalCharacterTests(CutoverTestBase):
    def _apply(self, account, entry):
        client = APIClient()
        client.force_authenticate(account)
        return client.post(
            f"/api/roster/entries/{entry.pk}/apply/", {"message": LONG_MESSAGE}, format="json"
        )

    def test_only_the_creating_account_can_apply_for_a_reserved_original(self) -> None:
        original = self._entry(
            CreationProvenance.PLAYER, holder=self.tester_data, author=self.tester
        )
        self._execute()

        refused = self._apply(self.other, original)
        accepted = self._apply(self.tester, original)

        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertIn("reserved_for_creator", refused.content.decode())
        self.assertEqual(accepted.status_code, 204, accepted.content)

    def test_a_roster_character_stays_open_to_everyone(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        self._execute()

        self.assertEqual(self._apply(self.other, roster_char).status_code, 204)


class CarryOverTests(CutoverTestBase):
    def test_an_original_with_no_author_is_reserved_to_the_account_that_held_it(self) -> None:
        unauthored = self._entry(CreationProvenance.PLAYER, holder=self.tester_data)

        report = self._execute(carry_over_sheet_ids=[unauthored.character_sheet_id])

        self.assertEqual(report.plan.count(CutoverPolicy.CARRY_OVER), 1)
        unauthored.refresh_from_db()
        self.assertEqual(unauthored.created_by_account_id, self.tester.pk)
        self.assertEqual(unauthored.roster.roster_type, RosterType.AVAILABLE)
        self.assertEqual(self._stat(unauthored), 3)

    def test_a_sheet_with_no_roster_entry_is_progress_reset_in_place(self) -> None:
        sheet = CharacterSheetFactory()
        _raised_stat(sheet, self.stat, authored=3, now=5)

        self._execute(carry_over_sheet_ids=[sheet.pk])

        self.assertEqual(CharacterTraitValue.objects.get(character=sheet, trait=self.stat).value, 3)

    def test_a_reserved_original_named_for_carry_over_is_reported_as_covered(self) -> None:
        original = self._entry(
            CreationProvenance.PLAYER, holder=self.tester_data, author=self.tester
        )

        plan = plan_cutover(carry_over_sheet_ids=[original.character_sheet_id])

        self.assertEqual(plan.count(CutoverPolicy.CARRY_OVER), 0)
        self.assertEqual(len(plan.carry_over_already_covered), 1)

    def test_a_roster_character_a_missing_sheet_and_an_npc_are_refused(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        story_npc = self._entry(CreationProvenance.PLAYER, shelf=RosterType.NPC)
        for sheet_id in (roster_char.character_sheet_id, story_npc.character_sheet_id, 0):
            with self.subTest(sheet_id=sheet_id), self.assertRaises(CarryOverError):
                plan_cutover(carry_over_sheet_ids=[sheet_id])


class CutoverCommandTests(CutoverTestBase):
    def test_the_dry_run_names_each_policy_step_and_what_awaits_a_ruling(self) -> None:
        self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        out = StringIO()

        call_command("beta_reset", stdout=out)

        output = out.getvalue()
        self.assertIn("Would run 1 cutover policy step", output)
        self.assertIn("[Roster character]", output)
        self.assertIn("return to the Available roster", output)
        self.assertIn("Dry run only", output)

    def test_a_bad_carry_over_id_is_a_command_error(self) -> None:
        with self.assertRaises(CommandError):
            call_command("beta_reset", "--carry-over", "0", stdout=StringIO())

    def test_execute_runs_the_policy_steps(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)

        call_command(
            "beta_reset",
            "--execute",
            confirm=CONFIRMATION_PHRASE,
            backup_verified_at=timezone.now().isoformat(),
            stdout=StringIO(),
        )

        entry = RosterEntry.objects.get(pk=roster_char.pk)
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)
        self.assertEqual(self._stat(entry), 3)


class DryRunReportTests(CutoverTestBase):
    def test_the_dry_run_reports_reservation_removed_rows_weapons_rivals_and_warnings(
        self,
    ) -> None:
        original = self._entry(
            CreationProvenance.PLAYER, holder=self.tester_data, author=self.tester
        )
        sheet = original.character_sheet
        CharacterTraitValueFactory(
            character=sheet, trait=StatTraitFactory(name="cutover_wit"), value=7
        )
        CharacterTraitChange.objects.create(
            character_sheet=sheet,
            trait=StatTraitFactory(name="cutover_wit"),
            old_value=0,
            new_value=7,
            source=TraitChangeSource.DEVELOPMENT_LEVEL_UP,
        )
        CharacterGiftFactory(character=sheet, gift=clawed_gift(), origin=AcquisitionOrigin.TRAINED)
        RosterApplicationFactory(player_data=self.other_data, character=sheet)
        # A second kept character whose ledger does not add up.
        broken = self._entry(CreationProvenance.STAFF, holder=self.other_data)
        self._set_value(broken, self.stat, 9)
        out = StringIO()

        call_command("beta_reset", stdout=out)

        output = out.getvalue()
        self.assertIn(f"reserved to {self.tester.username}", output)
        self.assertIn("rows removed: cutover_wit", output)
        self.assertIn("natural weapon", output)
        self.assertIn("1 pending application(s) from other accounts", output)
        self.assertIn(
            "LEDGER WARNING: cutover_strength: the ledger ends at 5 but the value is 9", output
        )
        self.assertIn("1 kept character(s) have an incomplete provenance ledger", output)
        self.assertIn("computed BEFORE the policy steps", output)
        self.assertEqual(CharacterGift.objects.filter(character=sheet).count(), 1)


class CutoverGuardTests(CutoverTestBase):
    def test_a_direct_execute_call_is_refused_when_disabled_or_released(self) -> None:
        roster_char = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        plan = plan_cutover()

        with (
            mock.patch("world.beta_reset.services.BETA_RESET_ENABLED", False),
            self.assertRaises(BetaResetDisabledError),
        ):
            execute_cutover(plan)
        ReleaseLatch.objects.create(released_by=self.tester)
        with self.assertRaises(ReleaseLatchedError):
            execute_cutover(plan)

        self.assertEqual(self._stat(roster_char), 5)
        self.assertTrue(roster_char.tenures.filter(end_date__isnull=True).exists())


class IncompleteLedgerCutoverTests(CutoverTestBase):
    def _broken_roster_character(self):
        entry = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        self._set_value(entry, self.stat, 9)
        return entry

    def test_execute_refuses_and_names_the_character_and_trait(self) -> None:
        entry = self._broken_roster_character()

        with self.assertRaises(IncompleteLedgerError) as raised:
            self._execute()

        self.assertIn("cutover_strength", str(raised.exception))
        self.assertIn(entry.character_sheet.character.db_key, str(raised.exception))
        self.assertEqual(self._stat(entry), 9)
        self.assertTrue(entry.tenures.filter(end_date__isnull=True).exists())

    def test_the_command_raises_a_command_error_and_the_flag_proceeds(self) -> None:
        entry = self._broken_roster_character()
        arguments = {"confirm": CONFIRMATION_PHRASE, "stdout": StringIO()}

        with self.assertRaises(CommandError) as raised:
            call_command(
                "beta_reset",
                "--execute",
                backup_verified_at=timezone.now().isoformat(),
                **arguments,
            )
        self.assertIn("--allow-incomplete-ledger", str(raised.exception))

        call_command(
            "beta_reset",
            "--execute",
            "--allow-incomplete-ledger",
            backup_verified_at=timezone.now().isoformat(),
            **arguments,
        )
        self.assertEqual(self._stat(entry), 7)


class CutoverRollbackTests(CutoverTestBase):
    def _blocked_world(self):
        """A kept character with progress, and a Secret whose clue has a pool entry."""
        entry = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        clue = ClueFactory(
            target_kind=ClueTargetKind.SECRET,
            target_codex_entry=None,
            target_secret=SecretFactory(),
        )
        CluePoolEntryFactory(clue=clue)
        return entry

    def test_a_protected_error_after_the_policy_steps_rolls_everything_back(self) -> None:
        entry = self._blocked_world()

        with self.assertRaises(WipeBlockedError) as raised:
            self._execute()

        self.assertEqual(raised.exception.blocking_models, ["CluePoolEntry"])
        # Read the database, not the identity-mapped instance: the rollback restored the rows
        # but this process still holds the instance the policy step changed.
        shelf = RosterEntry.objects.values_list("roster__roster_type", flat=True).get(pk=entry.pk)
        self.assertEqual(shelf, RosterType.ACTIVE)
        self.assertTrue(
            RosterTenure.objects.filter(roster_entry_id=entry.pk, end_date__isnull=True).exists()
        )
        self.assertEqual(self._db_stat(entry), 5)
        self.assertEqual(
            CharacterTraitChange.objects.filter(
                character_sheet=entry.character_sheet,
                source=TraitChangeSource.DEVELOPMENT_LEVEL_UP,
            ).count(),
            1,
        )

    def test_the_command_names_the_blocking_model_not_a_traceback(self) -> None:
        self._blocked_world()

        with self.assertRaises(CommandError) as raised:
            call_command(
                "beta_reset",
                "--execute",
                confirm=CONFIRMATION_PHRASE,
                backup_verified_at=timezone.now().isoformat(),
                stdout=StringIO(),
            )

        self.assertIn("CluePoolEntry", str(raised.exception))
        self.assertIn("rolled back", str(raised.exception))


class AfterTheWipeTests(CutoverTestBase):
    def test_the_thread_cache_and_max_health_are_right_in_the_same_process(self) -> None:
        entry = self._entry(CreationProvenance.STAFF, holder=self.tester_data)
        sheet = entry.character_sheet
        vitals = CharacterVitalsFactory(
            character_sheet=sheet, base_max_health=50, max_health=999, health=10
        )
        capstone_thread = ThreadFactory(owner=sheet, as_capstone_thread=True)
        kept_thread = ThreadFactory(owner=sheet)
        self.assertEqual(
            {t.pk for t in sheet.character.threads.all()}, {capstone_thread.pk, kept_thread.pk}
        )

        self._execute()

        self.assertEqual([t.pk for t in sheet.character.threads.all()], [kept_thread.pk])
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 50)
