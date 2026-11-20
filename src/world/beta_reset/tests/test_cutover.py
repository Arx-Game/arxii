"""The cutover policy layer: roster characters, reserved OCs and carry-over (#3055 PR 3)."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, EmailAddressFactory
from world.beta_reset.constants import CutoverPolicy
from world.beta_reset.cutover import plan_cutover, run_beta_cutover
from world.beta_reset.exceptions import CarryOverError, ConfirmationPhraseMismatchError
from world.beta_reset.services import CONFIRMATION_PHRASE
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType
from world.roster.seeds import ensure_rosters
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import CharacterTraitChange, CharacterTraitValue, TraitChangeSource

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
        self.assertIn("awaiting a ruling", output)
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
