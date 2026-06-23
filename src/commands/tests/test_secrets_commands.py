"""Telnet +secrets command tests (#1334) — thin wrapper over world.secrets.services.

Your own secrets show in full; secrets about others show locked layers as "Unknown". On telnet
the caller is the active character, so scoping is automatic.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from commands.social.secrets import CmdSecrets
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.secrets.factories import SecretCategoryFactory, SecretFactory
from world.secrets.services import grant_secret_knowledge


class SecretsCommandTests(TestCase):
    def _played(self, character, account=None):
        account = account or AccountFactory()
        player_data = PlayerDataFactory(account=account)
        entry = RosterEntryFactory(character_sheet__character=character)
        RosterTenureFactory(roster_entry=entry, player_data=player_data)
        return account, entry

    def setUp(self) -> None:
        self.caller = CharacterFactory(db_key="Alice")
        self.caller.msg = MagicMock()
        self.account, self.caller_entry = self._played(self.caller)
        self.caller_sheet = self.caller_entry.character_sheet

    def _run(self, args: str = "", switches: list[str] | None = None) -> None:
        cmd = CmdSecrets()
        cmd.caller = self.caller
        cmd.account = self.account
        cmd.args = args
        cmd.switches = switches or []
        cmd.func()

    def _output(self) -> str:
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def _target(self, db_key: str):
        target = CharacterFactory(db_key=db_key)
        _, entry = self._played(target)
        self.caller.search = MagicMock(return_value=target)
        return entry.character_sheet

    def test_own_secrets_are_listed_in_full(self) -> None:
        SecretFactory(subject_sheet=self.caller_sheet, content="I poisoned the duke.")
        self._run()
        assert "I poisoned the duke." in self._output()

    def test_no_own_secrets_message(self) -> None:
        self._run()
        assert "no secrets of your own" in self._output()

    def test_known_secret_about_another_character(self) -> None:
        subject = self._target("Bob")
        secret = SecretFactory(subject_sheet=subject, content="Bob is a spy.")
        grant_secret_knowledge(roster_entry=self.caller_entry, secret=secret)
        self._run(args="Bob")
        assert "Bob is a spy." in self._output()

    def test_locked_layer_renders_unknown(self) -> None:
        subject = self._target("Bob")
        secret = SecretFactory(
            subject_sheet=subject,
            content="Bob is a spy.",
            category=SecretCategoryFactory(name="Scandal"),
            consequences="Hanged for treason.",
        )
        # Knows the fact only — not the category or consequences.
        grant_secret_knowledge(roster_entry=self.caller_entry, secret=secret)
        self._run(args="Bob")
        out = self._output()
        assert "Category: Unknown" in out
        assert "Consequences: Unknown" in out

    def test_unlocked_layers_show_values(self) -> None:
        subject = self._target("Bob")
        secret = SecretFactory(
            subject_sheet=subject,
            category=SecretCategoryFactory(name="Scandal"),
            consequences="Hanged for treason.",
        )
        grant_secret_knowledge(
            roster_entry=self.caller_entry,
            secret=secret,
            knows_category=True,
            knows_consequences=True,
        )
        self._run(args="Bob")
        out = self._output()
        assert "Scandal" in out
        assert "Hanged for treason." in out

    def test_secrets_about_someone_you_know_nothing_about(self) -> None:
        self._target("Bob")
        self._run(args="Bob")
        assert "You know none." in self._output()
