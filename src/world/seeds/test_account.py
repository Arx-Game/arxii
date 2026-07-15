"""Seed a pre-verified test account for e2e and integration testing.

Creates an AccountDB with a verified EmailAddress and associated PlayerData,
so authenticated e2e flows (Playwright) and integration tests can skip the
registration + email-verification dance.

Idempotent: re-running on an existing account is a no-op. Never overwrites
the password or email-verified status of an existing account — if you need
a fresh account, delete it and re-seed.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Default credentials for the seeded test account. These are intentionally
#: hardcoded and public — they exist solely for local dev / e2e testing and
#: must never be used in production. The safety gate is ALLOW_INTEGRATION_TESTS
#: in .env, checked by the CLI command that invokes this seed.
DEFAULT_USERNAME = "e2e_test_account"
DEFAULT_EMAIL = "e2e_test@example.com"
DEFAULT_PASSWORD = "TestPass123!"  # noqa: S105


@dataclass
class TestAccountSeedResult:
    """Outcome of seeding the test account."""

    username: str
    email: str
    created: bool


def seed_test_account(
    *,
    username: str = DEFAULT_USERNAME,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
) -> TestAccountSeedResult:
    """Create a pre-verified test account if it doesn't already exist.

    Args:
        username: The account username.
        email: The account email address.
        password: The account password.

    Returns:
        A result indicating whether a new account was created.
    """
    from allauth.account.models import EmailAddress
    from evennia.accounts.models import AccountDB

    from evennia_extensions.models import PlayerData

    existing = AccountDB.objects.filter(username=username).first()
    if existing is not None:
        # Ensure PlayerData exists even if the account was created out-of-band.
        PlayerData.objects.get_or_create(account=existing)
        return TestAccountSeedResult(username=username, email=email, created=False)

    account = AccountDB.objects.create_user(
        username=username,
        email=email,
        password=password,
    )

    # The ArxAccountAdapter creates PlayerData on signup via the web form,
    # but we're creating the account directly, so do it here too.
    PlayerData.objects.get_or_create(account=account)

    # Mark the email as verified so the account can log in immediately
    # without going through the email-verification flow.
    EmailAddress.objects.create(
        user=account,
        email=email,
        primary=True,
        verified=True,
    )

    return TestAccountSeedResult(username=username, email=email, created=True)
