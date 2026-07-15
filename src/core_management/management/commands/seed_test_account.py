"""Seed a pre-verified test account for e2e / integration testing.

Usage: arx manage seed_test_account

Creates an AccountDB with username ``e2e_test_account``, a verified
EmailAddress, and associated PlayerData. Idempotent — re-running is a no-op.

The account credentials are intentionally hardcoded and public; they exist
solely for local dev / e2e testing and must never be used in production.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed a pre-verified test account for e2e / integration testing."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--username",
            default="e2e_test_account",
            help="Username for the test account (default: e2e_test_account)",
        )
        parser.add_argument(
            "--email",
            default="e2e_test@example.com",
            help="Email for the test account (default: e2e_test@example.com)",
        )
        parser.add_argument(
            "--password",
            default="TestPass123!",
            help="Password for the test account (default: TestPass123!)",
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        from world.seeds.test_account import seed_test_account  # noqa: PLC0415

        result = seed_test_account(
            username=options["username"],
            email=options["email"],
            password=options["password"],
        )

        if result.created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created test account '{result.username}' "
                    f"({result.email}) with verified email."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Test account '{result.username}' already exists — no changes made."
                )
            )
