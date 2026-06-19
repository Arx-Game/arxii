"""Seed the database with sane defaults (roadmap Phase 3; #651).

Project-rule exception: the "no management commands" rule is explicitly
overridden for this command only.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed sane defaults. Usage: seed dev"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("target", choices=["dev"], help="What to seed (dev)")  # noqa: STRING_LITERAL

    def handle(self, *_args: Any, **_options: Any) -> None:
        # The single positional arg is constrained to "dev" by argparse
        # choices=["dev"], so there is nothing to branch on yet.
        from world.seeds.database import seed_dev_database  # noqa: PLC0415

        report = seed_dev_database(verbose=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {report.created_total} rows across {len(report.clusters)} clusters."
            )
        )
