"""Unit tests for CmdDurance — status / intent / convene (#1700).

Covers:
  (a) bare ``durance`` hub shows the caller's level and eligible-path info.
  (b) ``durance convene`` with no training site in the room → NoDuranceSiteError message.
  (c) ``durance intent <name>`` dispatches SetPathIntentAction (PathIntent row set).
  (d) Unknown subverb is handled gracefully.
  (e) Tier-boundary path surfaces the Audere Majora message.

Uses the _run() harness pattern (set cmd.caller, cmd.args, mock caller.msg),
matching test_progression_rewards_commands.py and test_ritual_durance.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.durance import CmdDurance
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import PathStage
from world.progression.exceptions import NoDuranceSiteError
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import PathIntent
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock

_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


def _run(cmd_cls, caller, args=""):
    """Build a command instance and call func(); return the list of msg strings."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class DuranceStatusHubTests(TestCase):
    """Bare ``durance`` shows level, readiness, eligible paths, intent, site."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.char = CharacterFactory(db_key="HubTestChar")
        self.sheet = CharacterSheetFactory(character=self.char)
        self.char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=self.sheet,
            character_class=self.char_class,
            level=2,
            is_primary=True,
        )
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        # Authored unlock for level 3.
        ClassLevelUnlock.objects.create(
            character_class=self.char_class,
            target_level=3,
        )
        # Child path at POTENTIAL stage (eligible at level 3).
        self.child_path = PathFactory(name="Iron Vein", stage=PathStage.POTENTIAL)
        self.path.child_paths.add(self.child_path)

    def test_bare_durance_shows_level(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("level 2", combined)

    def test_ready_message_when_requirements_met(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("ready", combined.lower())

    def test_shows_eligible_advanced_path_name(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("Iron Vein", combined)

    def test_unmet_requirements_lists_reason(self) -> None:
        with patch(_CHECK_PATH, return_value=(False, ["Requires 10 Legend"])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("Requires 10 Legend", combined)

    def test_status_subverb_is_same_as_bare(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs_bare = _run(CmdDurance, self.char, "")
        self.char.msg = MagicMock()
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs_status = _run(CmdDurance, self.char, "status")
        # Both produce at least one message containing level info.
        self.assertTrue(any("level 2" in m for m in msgs_bare))
        self.assertTrue(any("level 2" in m for m in msgs_status))

    def test_no_training_site_shows_site_status(self) -> None:
        """Without a location or training site, the hub shows a site-related status line."""
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        # Either "No training site here." (in a room with no site) or
        # "You are not in a room." (no location at all).
        has_site_status = "No training site" in combined or "not in a room" in combined
        self.assertTrue(has_site_status, f"Expected site status line, got: {combined!r}")

    def test_no_intent_declared_shown(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("No path intent", combined)


class DuranceXPUnlockReadinessLineTests(TestCase):
    """The XP-unlock readiness line (#2116) — purchased vs. not-purchased."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.char = CharacterFactory(db_key="UnlockLineChar")
        self.sheet = CharacterSheetFactory(character=self.char)
        self.char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=self.sheet,
            character_class=self.char_class,
            level=2,
            is_primary=True,
        )
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.char_class,
            target_level=3,
        )

    def test_shows_not_purchased_with_cost(self) -> None:
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("XP unlock: not purchased (cost 0).", combined)

    def test_shows_purchased_when_receipt_exists(self) -> None:
        CharacterUnlock.objects.create(
            character=self.sheet,
            character_class=self.char_class,
            target_level=3,
        )
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("XP unlock: purchased.", combined)
        self.assertNotIn("not purchased", combined)

    def test_ready_message_requires_both_gates(self) -> None:
        """met=True alone is not enough — purchase is also required for 'ready to advance'."""
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs_unpurchased = _run(CmdDurance, self.char)
        combined_unpurchased = "\n".join(msgs_unpurchased)
        self.assertNotIn("You are ready to advance", combined_unpurchased)

        CharacterUnlock.objects.create(
            character=self.sheet,
            character_class=self.char_class,
            target_level=3,
        )
        self.char.msg = None  # reset caller.msg mock via a fresh _run
        with patch(_CHECK_PATH, return_value=(True, [])):
            msgs_purchased = _run(CmdDurance, self.char)
        combined_purchased = "\n".join(msgs_purchased)
        self.assertIn("You are ready to advance to level 3.", combined_purchased)


class DuranceTierBoundaryTests(TestCase):
    """Tier-boundary level shows the Audere Majora message, skips readiness."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="TierChar")
        CharacterSheetFactory(character=self.char)

    def test_tier_boundary_surfaces_audere_majora_message(self) -> None:
        # Patch AudereMajoraThreshold to pretend level 5 is a boundary.
        with patch("world.magic.audere_majora.AudereMajoraThreshold.objects") as mock_mgr:
            mock_mgr.filter.return_value.exists.return_value = True
            msgs = _run(CmdDurance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("Audere Majora", combined)


class DuranceConveneTests(TestCase):
    """``durance convene`` delegates to convene_durance_at_site."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="ConveneChar")
        CharacterSheetFactory(character=self.char)

    def test_convene_no_site_surfaces_error_message(self) -> None:
        """When convene_durance_at_site raises NoDuranceSiteError the user sees the message."""
        with patch(
            "world.progression.services.advancement.convene_durance_at_site",
            side_effect=NoDuranceSiteError,
        ):
            msgs = _run(CmdDurance, self.char, "convene")
        combined = "\n".join(msgs)
        self.assertIn(NoDuranceSiteError.user_message, combined)

    def test_convene_success_shows_ritual_join_instruction(self) -> None:
        """On success the message tells the inductee to use 'ritual join'."""
        mock_session = MagicMock()
        mock_session.pk = 42
        with patch(
            "world.progression.services.advancement.convene_durance_at_site",
            return_value=mock_session,
        ):
            msgs = _run(CmdDurance, self.char, "convene")
        combined = "\n".join(msgs)
        self.assertIn("ritual join 42", combined)


class DuranceIntentTests(TestCase):
    """``durance intent`` sets or clears PathIntent via the existing Action."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.char = CharacterFactory(db_key="IntentChar")
        self.sheet = CharacterSheetFactory(character=self.char)
        CharacterClassLevelFactory(
            character=self.sheet,
            character_class=CharacterClassFactory(),
            level=2,
            is_primary=True,
        )
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        # A child path the character can declare intent for.
        self.child_path = PathFactory(name="Shadow Thorn", stage=PathStage.POTENTIAL)
        self.path.child_paths.add(self.child_path)

    def test_intent_by_name_sets_path_intent_row(self) -> None:
        _run(CmdDurance, self.char, "intent Shadow Thorn")
        # PathIntent row should have been set by SetPathIntentAction.
        self.assertTrue(
            PathIntent.objects.filter(
                character_sheet=self.sheet,
                intended_path=self.child_path,
            ).exists()
        )

    def test_intent_message_acknowledges_path(self) -> None:
        msgs = _run(CmdDurance, self.char, "intent Shadow Thorn")
        combined = "\n".join(msgs)
        self.assertIn("Shadow Thorn", combined)

    def test_intent_clear_removes_intent(self) -> None:
        PathIntent.objects.create(
            character_sheet=self.sheet,
            intended_path=self.child_path,
        )
        msgs = _run(CmdDurance, self.char, "intent clear")
        combined = "\n".join(msgs)
        self.assertIn("cleared", combined.lower())
        self.assertFalse(PathIntent.objects.filter(character_sheet=self.sheet).exists())

    def test_intent_unknown_path_surfaces_error(self) -> None:
        msgs = _run(CmdDurance, self.char, "intent Nonexistent Path")
        combined = "\n".join(msgs)
        self.assertIn("Nonexistent Path", combined)

    def test_intent_no_arg_shows_usage(self) -> None:
        msgs = _run(CmdDurance, self.char, "intent")
        combined = "\n".join(msgs)
        self.assertIn("Usage", combined)


class DuranceUnknownSubverbTests(TestCase):
    """Unknown subverbs surface a helpful error, not an exception."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="UnknownSubChar")
        CharacterSheetFactory(character=self.char)

    def test_unknown_subverb_shows_error_message(self) -> None:
        msgs = _run(CmdDurance, self.char, "frobnicate")
        combined = "\n".join(msgs)
        self.assertIn("frobnicate", combined)
        self.assertIn("Unknown", combined)
