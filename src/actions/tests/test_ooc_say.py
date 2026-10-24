"""``ooc`` leaves the character puppeted (#4337, ADR-0294).

Speaking ``ooc`` is a journey (``integration_tests/test_voice_and_feeling_journeys.py``).
What a typed line cannot show is a command that is absent: Evennia's stock ``ooc``
unpuppeted the character into an account screen, and login always puppets now.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from commands.default_cmdsets import AccountCmdSet


class OOCCommandTests(SimpleTestCase):
    def test_evennias_unpuppeting_ooc_is_gone(self) -> None:
        """No account screen to fall into: login always puppets (ADR-0294)."""
        keys = {cmd.key for cmd in AccountCmdSet().commands}
        aliases = {alias for cmd in AccountCmdSet().commands for alias in cmd.aliases}

        assert "ooc" not in keys
        assert "unpuppet" not in aliases
