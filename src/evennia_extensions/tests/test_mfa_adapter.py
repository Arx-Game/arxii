"""TOTP secrets and recovery seeds are encrypted at rest under MFA_SECRETS_KEY (#3591, ADR-0265)."""

from cryptography.fernet import Fernet
from django.core.checks import Error
from django.test import SimpleTestCase, TestCase, override_settings

from evennia_extensions.checks import check_mfa_secrets_key
from evennia_extensions.mfa_adapter import ArxMFAAdapter, fernet_from_setting

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


class ArxMFAAdapterTests(SimpleTestCase):
    @override_settings(MFA_SECRETS_KEY=KEY_A)
    def test_round_trip_is_not_plaintext(self):
        adapter = ArxMFAAdapter()
        token = adapter.encrypt("JBSWY3DPEHPK3PXP")
        self.assertNotEqual(token, "JBSWY3DPEHPK3PXP")
        self.assertEqual(adapter.decrypt(token), "JBSWY3DPEHPK3PXP")

    @override_settings(MFA_SECRETS_KEY=KEY_A)
    def test_rotation_prepends_new_key_and_still_reads_old_rows(self):
        old_token = ArxMFAAdapter().encrypt("secret")
        with override_settings(MFA_SECRETS_KEY=f"{KEY_B},{KEY_A}"):
            adapter = ArxMFAAdapter()
            self.assertEqual(adapter.decrypt(old_token), "secret")
            # New writes use the first key only.
            new_token = adapter.encrypt("secret")
            self.assertEqual(fernet_from_setting(KEY_B).decrypt(new_token.encode()), b"secret")

    @override_settings(MFA_SECRETS_KEY=KEY_A)
    def test_wrong_key_is_loud(self):
        token = ArxMFAAdapter().encrypt("secret")
        with override_settings(MFA_SECRETS_KEY=KEY_B):
            with self.assertRaises(ValueError) as ctx:
                ArxMFAAdapter().decrypt(token)
        self.assertIn("MFA_SECRETS_KEY", str(ctx.exception))


class MfaSecretsKeyCheckTests(SimpleTestCase):
    @override_settings(MFA_SECRETS_KEY=KEY_A)
    def test_valid_key_passes(self):
        self.assertEqual(check_mfa_secrets_key(None), [])

    @override_settings(MFA_SECRETS_KEY=KEY_A[:-1])
    def test_truncated_key_is_a_critical_error_naming_the_position(self):
        errors = check_mfa_secrets_key(None)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Error)
        self.assertEqual(errors[0].id, "evennia_extensions.E001")
        self.assertIn("position 1", errors[0].msg)

    @override_settings(MFA_SECRETS_KEY=f"{KEY_A},not-a-key")
    def test_bad_second_key_is_reported_at_position_2(self):
        errors = check_mfa_secrets_key(None)
        self.assertIn("position 2", errors[0].msg)

    @override_settings(MFA_SECRETS_KEY="")
    def test_empty_key_is_an_error(self):
        self.assertEqual(len(check_mfa_secrets_key(None)), 1)


class AdapterIsWiredTests(TestCase):
    def test_settings_point_at_the_adapter(self):
        from allauth.mfa.adapter import get_adapter

        self.assertIsInstance(get_adapter(), ArxMFAAdapter)
