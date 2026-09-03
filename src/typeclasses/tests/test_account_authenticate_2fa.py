"""Telnet password sign-in vs. opt-in 2FA (#3591, ADR-0264).

Evennia's ``CmdUnconnectedConnect`` calls ``Account.authenticate`` on
``settings.BASE_ACCOUNT_TYPECLASS`` (``evennia/commands/default/unloggedin.py:75,149``),
so this override is the telnet door. Web sessions never pass through it.
"""

from allauth.mfa.models import Authenticator
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.mfa_adapter import ArxMFAAdapter
from evennia_extensions.models import PlayerData
from typeclasses.accounts import TELNET_BLOCKED_BY_2FA_MESSAGE, Account

PASSWORD = "TelnetPass123!"  # noqa: S105 - test fixture value, not a real credential


class AccountAuthenticate2FATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory(username="telnet_2fa_user")
        cls.account.set_password(PASSWORD)
        cls.account.save()
        cls.player_data, _ = PlayerData.objects.get_or_create(account=cls.account)

    def _enrol(self):
        Authenticator.objects.create(
            user=self.account,
            type=Authenticator.Type.TOTP,
            data={"secret": ArxMFAAdapter().encrypt("JBSWY3DPEHPK3PXP")},
        )

    def _set_block(self, value: bool):
        self.player_data.block_telnet_login_with_2fa = value
        self.player_data.save(update_fields=["block_telnet_login_with_2fa"])

    def test_no_2fa_no_block_signs_in(self):
        account, errors = Account.authenticate("telnet_2fa_user", PASSWORD)
        self.assertEqual(account.pk, self.account.pk)
        self.assertEqual(errors, [])

    def test_2fa_on_but_block_off_still_signs_in(self):
        """2FA alone never changes telnet (decision 5)."""
        self._enrol()
        account, errors = Account.authenticate("telnet_2fa_user", PASSWORD)
        self.assertEqual(account.pk, self.account.pk)
        self.assertEqual(errors, [])

    def test_block_on_without_2fa_is_inert(self):
        self._set_block(True)
        account, _ = Account.authenticate("telnet_2fa_user", PASSWORD)
        self.assertEqual(account.pk, self.account.pk)

    def test_both_on_refuses_with_the_message(self):
        self._enrol()
        self._set_block(True)
        account, errors = Account.authenticate("telnet_2fa_user", PASSWORD)
        self.assertIsNone(account)
        self.assertEqual(errors, [TELNET_BLOCKED_BY_2FA_MESSAGE])

    def test_wrong_password_is_unchanged_and_never_leaks_the_block(self):
        self._enrol()
        self._set_block(True)
        account, errors = Account.authenticate("telnet_2fa_user", "wrong")
        self.assertIsNone(account)
        self.assertNotIn(TELNET_BLOCKED_BY_2FA_MESSAGE, errors)
