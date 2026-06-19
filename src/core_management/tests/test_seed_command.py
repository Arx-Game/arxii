from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class TestSeedCommand(TestCase):
    def test_seed_dev_runs_and_reports(self) -> None:
        out = StringIO()
        call_command("seed", "dev", stdout=out)
        self.assertIn("Seeded", out.getvalue())

    def test_unknown_subcommand_errors(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed", "bogus")
