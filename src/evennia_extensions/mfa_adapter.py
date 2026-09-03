"""allauth MFA adapter: TOTP secrets and recovery seeds encrypted at rest (#3591, ADR-0265).

allauth's default ``encrypt``/``decrypt`` are the identity, so ``Authenticator.data``
would hold every player's TOTP secret in the clear, and so would every ``pg_dump``
in the backup bucket. This adapter wraps both under ``settings.MFA_SECRETS_KEY``:
a comma-separated list of Fernet keys, first key current. ``MultiFernet`` encrypts
with the first key and decrypts with any, so rotation is prepend, deploy,
re-encrypt (see docs/systems/registration.md), drop.

The key is deliberately separate from ``SECRET_KEY`` so Django's key can still be
rotated freely (that only signs sessions out). Losing THIS key locks every 2FA user
out until staff delete their authenticators; ``evennia_extensions.checks`` refuses
to start on a malformed key and the ``mfa-secrets-key`` sentinel probe reports a
key that no longer decrypts stored rows.
"""

from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


def split_keys(value: str) -> list[str]:
    """The configured keys in priority order, whitespace stripped, empties dropped."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def fernet_from_setting(value: str) -> MultiFernet:
    """Build the MultiFernet for a raw ``MFA_SECRETS_KEY`` value. Raises ValueError on a bad key."""
    keys = split_keys(value)
    if not keys:
        msg = "MFA_SECRETS_KEY is empty"
        raise ValueError(msg)
    return MultiFernet([Fernet(key.encode("ascii")) for key in keys])


class ArxMFAAdapter(DefaultMFAAdapter):
    """Encrypt what allauth stores in ``Authenticator.data`` (TOTP secret, recovery seed)."""

    def _fernet(self) -> MultiFernet:
        return fernet_from_setting(settings.MFA_SECRETS_KEY)

    def encrypt(self, text: str) -> str:
        return self._fernet().encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, encrypted_text: str) -> str:
        try:
            return self._fernet().decrypt(encrypted_text.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            msg = (
                "A stored 2FA secret does not decrypt under any configured MFA_SECRETS_KEY. "
                "The key was rotated without re-encrypting, or the wrong key is deployed."
            )
            raise ValueError(msg) from exc
