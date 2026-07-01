"""E2E tests for the telnet ``consent`` preference command (#1487).

``CmdConsent`` is a thin DispatchCommand shell that parses telnet text into the
same kwargs the web-facing REGISTRY actions expect, then routes through
``dispatch_player_action``. These tests build characters in the same room, wire
active RosterTenures, and assert the command updates consent state (or renders
a summary) through the real action seam.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.consent_preferences import CmdConsent
from commands.default_cmdsets import CharacterCmdSet
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentBlacklistFactory,
    SocialConsentCategoryFactory,
    SocialConsentWhitelistFactory,
)
from world.consent.models import (
    SocialConsentBlacklist,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)


class CmdConsentTests(TestCase):
    """End-to-end coverage of the ``consent`` telnet namespace."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData,
        # because the idmapper's DbHolder is un-deepcopyable.
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        self.player = PlayerDataFactory()
        self.caller_char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.caller_char.account = self.player.account
        self.caller_sheet = CharacterSheetFactory(character=self.caller_char)
        self.caller_entry = RosterEntryFactory(character_sheet=self.caller_sheet)
        self.caller_tenure = RosterTenureFactory(
            player_data=self.player,
            roster_entry=self.caller_entry,
        )

        self.target_char = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.target_entry = RosterEntryFactory(character_sheet=self.target_sheet)
        self.target_tenure = RosterTenureFactory(
            roster_entry=self.target_entry,
        )

        self.category = SocialConsentCategoryFactory(key="romantic", name="Romantic")

    def _run(self, args: str) -> CmdConsent:
        cmd = CmdConsent()
        cmd.caller = self.caller_char
        cmd.args = args
        cmd.raw_string = f"consent {args}".strip()
        self.caller_char.msg = MagicMock()
        cmd.func()
        return cmd

    def test_bare_consent_shows_summary(self) -> None:
        cmd = self._run("")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Consent settings", text)
        self.assertIn("Social actions: allowed", text)
        self.assertIn("No per-category rules", text)
        self.assertIn("No whitelist entries", text)

    def test_consent_on_sets_preference(self) -> None:
        SocialConsentPreference.objects.filter(tenure=self.caller_tenure).delete()
        self.assertFalse(SocialConsentPreference.objects.filter(tenure=self.caller_tenure).exists())

        cmd = self._run("on")

        preference = SocialConsentPreference.objects.get(tenure=self.caller_tenure)
        self.assertTrue(preference.allow_social_actions)
        cmd.caller.msg.assert_called_once()
        self.assertIn("allowed", cmd.caller.msg.call_args[0][0])

    def test_consent_off_sets_preference(self) -> None:
        SocialConsentPreference.objects.create(tenure=self.caller_tenure, allow_social_actions=True)

        cmd = self._run("off")

        preference = SocialConsentPreference.objects.get(tenure=self.caller_tenure)
        self.assertFalse(preference.allow_social_actions)
        cmd.caller.msg.assert_called_once()
        self.assertIn("blocked", cmd.caller.msg.call_args[0][0])

    def test_consent_category_sets_allowlist(self) -> None:
        cmd = self._run("category romantic=allowlist")

        rule = SocialConsentCategoryRule.objects.get(
            preference__tenure=self.caller_tenure,
            category=self.category,
        )
        self.assertEqual(rule.mode, ConsentMode.ALLOWLIST)
        cmd.caller.msg.assert_called_once()
        self.assertIn("Romantic", cmd.caller.msg.call_args[0][0])

    def test_consent_category_default_removes_rule(self) -> None:
        SocialConsentPreference.objects.create(tenure=self.caller_tenure)
        SocialConsentCategoryRule.objects.create(
            preference=self.caller_tenure.social_consent_preference,
            category=self.category,
            mode=ConsentMode.ALLOWLIST,
        )

        cmd = self._run("category romantic=default")

        self.assertFalse(
            SocialConsentCategoryRule.objects.filter(preference__tenure=self.caller_tenure).exists()
        )
        cmd.caller.msg.assert_called_once()
        self.assertIn("reverted", cmd.caller.msg.call_args[0][0])

    def test_whitelist_add_by_name(self) -> None:
        cmd = self._run(f"whitelist add {self.target_char.key} to romantic")

        entry = SocialConsentWhitelist.objects.get(
            owner_tenure=self.caller_tenure,
            allowed_tenure=self.target_tenure,
            category=self.category,
        )
        self.assertIsNotNone(entry)
        cmd.caller.msg.assert_called_once()
        self.assertIn("Romantic", cmd.caller.msg.call_args[0][0])

    def test_category_sets_blacklist_mode(self) -> None:
        """The 'blacklist' token maps to ALL_BUT_BLACKLIST; 'friends' to FRIENDS_WHITELIST."""
        self._run("category romantic=blacklist")
        rule = SocialConsentCategoryRule.objects.get(preference__tenure=self.caller_tenure)
        self.assertEqual(rule.mode, ConsentMode.ALL_BUT_BLACKLIST)

        self._run("category romantic=friends")
        rule.refresh_from_db()
        self.assertEqual(rule.mode, ConsentMode.FRIENDS_WHITELIST)

    def test_blacklist_add_by_name(self) -> None:
        cmd = self._run(f"blacklist add {self.target_char.key} to romantic")

        entry = SocialConsentBlacklist.objects.get(
            owner_tenure=self.caller_tenure,
            blocked_tenure=self.target_tenure,
            category=self.category,
        )
        self.assertIsNotNone(entry)
        cmd.caller.msg.assert_called_once()
        self.assertIn("Romantic", cmd.caller.msg.call_args[0][0])

    def test_blacklist_remove_by_name(self) -> None:
        SocialConsentBlacklistFactory(
            owner_tenure=self.caller_tenure,
            blocked_tenure=self.target_tenure,
            category=self.category,
        )

        cmd = self._run(f"blacklist remove {self.target_char.key} from romantic")

        self.assertFalse(
            SocialConsentBlacklist.objects.filter(
                owner_tenure=self.caller_tenure,
                blocked_tenure=self.target_tenure,
                category=self.category,
            ).exists()
        )
        cmd.caller.msg.assert_called_once()
        self.assertIn("removed", cmd.caller.msg.call_args[0][0])

    def test_blacklist_list_shows_entries(self) -> None:
        SocialConsentBlacklistFactory(
            owner_tenure=self.caller_tenure,
            blocked_tenure=self.target_tenure,
            category=self.category,
        )

        cmd = self._run("blacklist list")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Blacklist entries", text)
        self.assertIn(str(self.target_tenure), text)

    def test_whitelist_remove_by_name(self) -> None:
        SocialConsentWhitelistFactory(
            owner_tenure=self.caller_tenure,
            allowed_tenure=self.target_tenure,
            category=self.category,
        )

        cmd = self._run(f"whitelist remove {self.target_char.key} from romantic")

        self.assertFalse(
            SocialConsentWhitelist.objects.filter(
                owner_tenure=self.caller_tenure,
                allowed_tenure=self.target_tenure,
                category=self.category,
            ).exists()
        )
        cmd.caller.msg.assert_called_once()
        self.assertIn("removed", cmd.caller.msg.call_args[0][0])

    def test_whitelist_list_shows_entries(self) -> None:
        SocialConsentWhitelistFactory(
            owner_tenure=self.caller_tenure,
            allowed_tenure=self.target_tenure,
            category=self.category,
        )

        cmd = self._run("whitelist list")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Whitelist entries", text)
        self.assertIn(str(self.target_tenure), text)
        self.assertIn("Romantic", text)

    def test_whitelist_list_filtered_by_category(self) -> None:
        other_category = SocialConsentCategoryFactory(key="hostile", name="Hostile")
        SocialConsentWhitelistFactory(
            owner_tenure=self.caller_tenure,
            allowed_tenure=self.target_tenure,
            category=self.category,
        )
        SocialConsentWhitelistFactory(
            owner_tenure=self.caller_tenure,
            allowed_tenure=self.target_tenure,
            category=other_category,
        )

        cmd = self._run("whitelist list romantic")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Romantic", text)
        self.assertNotIn("Hostile", text)

    def test_whitelist_add_unknown_target_reports_error(self) -> None:
        cmd = self._run("whitelist add Nobody to romantic")

        cmd.caller.msg.assert_called()
        text = cmd.caller.msg.call_args_list[0][0][0]
        self.assertIn("Could not find", text)
        self.assertFalse(SocialConsentWhitelist.objects.exists())

    def test_whitelist_add_target_without_tenure_reports_error(self) -> None:
        stranger = ObjectDBFactory(
            db_key="Cleo",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=stranger)

        cmd = self._run("whitelist add Cleo to romantic")

        cmd.caller.msg.assert_called()
        text = cmd.caller.msg.call_args_list[0][0][0]
        self.assertIn("active character tenure", text)
        self.assertFalse(SocialConsentWhitelist.objects.exists())

    def test_unknown_subverb_reports_usage(self) -> None:
        cmd = self._run("nonsense")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Usage", text)

    def test_category_without_equals_reports_usage(self) -> None:
        cmd = self._run("category romantic")

        cmd.caller.msg.assert_called_once()
        text = cmd.caller.msg.call_args[0][0]
        self.assertIn("Usage", text)

    def test_whitelist_malformed_reports_usage(self) -> None:
        cmd = self._run("whitelist add Bob")

        cmd.caller.msg.assert_called()
        text = cmd.caller.msg.call_args_list[0][0][0]
        self.assertIn("Usage", text)

    def test_caller_without_sheet_reports_error(self) -> None:
        no_sheet = ObjectDBFactory(
            db_key="Sheetless",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        cmd = CmdConsent()
        cmd.caller = no_sheet
        cmd.args = "on"
        cmd.raw_string = "consent on"
        no_sheet.msg = MagicMock()

        cmd.func()

        no_sheet.msg.assert_called()
        text = no_sheet.msg.call_args_list[0][0][0]
        self.assertIn("character identity", text)

    def test_caller_without_tenure_reports_error(self) -> None:
        no_tenure_char = ObjectDBFactory(
            db_key="NoTenure",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=no_tenure_char)
        no_tenure_char.account = self.player.account

        cmd = CmdConsent()
        cmd.caller = no_tenure_char
        cmd.args = "on"
        cmd.raw_string = "consent on"
        no_tenure_char.msg = MagicMock()

        cmd.func()

        no_tenure_char.msg.assert_called()
        text = no_tenure_char.msg.call_args_list[0][0][0]
        self.assertIn("active character tenure", text)

    def test_command_registered_in_character_cmdset(self) -> None:
        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {cmd.key for cmd in cmdset.commands}
        self.assertIn("consent", keys)

    def test_whitelist_uses_whitelist_alias_for_allowlist(self) -> None:
        """Player-facing 'whitelist' is accepted as an alias for 'allowlist'."""
        self._run("category romantic=whitelist")

        rule = SocialConsentCategoryRule.objects.get(
            preference__tenure=self.caller_tenure,
            category=self.category,
        )
        self.assertEqual(rule.mode, ConsentMode.ALLOWLIST)

    def test_whitelist_add_resolves_target_by_name(self) -> None:
        """The add path resolves the target character by name via Evennia search."""
        cmd = self._run("whitelist add Bob to romantic")

        self.assertTrue(
            SocialConsentWhitelist.objects.filter(
                owner_tenure=self.caller_tenure,
                allowed_tenure=self.target_tenure,
                category=self.category,
            ).exists()
        )
        cmd.caller.msg.assert_called_once()
