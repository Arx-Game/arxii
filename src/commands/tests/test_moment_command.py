"""Telnet E2E tests for CmdMoment — the ``moment`` suggestion inbox namespace (#2183).

Drives ``CmdMoment`` end-to-end through ``moment suggestions`` / ``moment confirm <id>``
/ ``moment dismiss <id>``, asserting DB state after each step and telnet feedback via
``caller.msg``. Mirrors ``commands/tests/test_motif.py``'s real-dispatch style (not
mocked) since these cases assert actual row creation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils import idmapper
from evennia.utils.create import create_object

from commands.dramatic_moments import CmdMoment
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SuggestionStatus
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentSuggestionFactory,
    DramaticMomentTypeFactory,
)
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory


def _run(caller: object, args: str = "") -> CmdMoment:
    """Wire CmdMoment to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdMoment()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"moment {args}".strip()
    cmd.cmdname = "moment"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


class MomentTelnetE2ETest(TestCase):
    """suggestions / confirm / dismiss through telnet CmdMoment."""

    def setUp(self) -> None:
        idmapper.models.flush_cache()

        self.room = create_object("typeclasses.rooms.Room", key="MomentRoom", nohome=True)
        self.scene = SceneFactory(location=self.room, is_active=True)

        self.sheet = CharacterSheetFactory()
        self.resonance_holder = CharacterResonanceFactory(character_sheet=self.sheet)
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance_holder.resonance, per_scene_cap=1
        )
        self.suggestion = DramaticMomentSuggestionFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )

        self.gm_character = CharacterFactory()
        self.gm_character.location = self.room
        self.gm_character.save()
        self.gm_account = AccountFactory()
        self.gm_character.db_account = self.gm_account
        self.gm_character.save(update_fields=["db_account"])
        SceneGMParticipationFactory(scene=self.scene, account=self.gm_account)

        self.outsider_character = CharacterFactory()
        self.outsider_character.location = self.room
        self.outsider_character.save()
        self.outsider_account = AccountFactory()
        self.outsider_character.db_account = self.outsider_account
        self.outsider_character.save(update_fields=["db_account"])

    # ------------------------------------------------------------------
    # suggestions
    # ------------------------------------------------------------------

    def test_suggestions_lists_pending_for_gm(self) -> None:
        _run(self.gm_character, "suggestions")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn(str(self.suggestion.pk), msg)
        self.assertIn(self.moment_type.label, msg)

    def test_non_gm_suggestions_refused(self) -> None:
        """A non-GM must never see pending suggestions (oracle leak, #2183 review)."""
        _run(self.outsider_character, "suggestions")

        self.outsider_character.msg.assert_called()
        msg = self.outsider_character.msg.call_args[0][0]
        self.assertIn("gm", msg.lower())
        self.assertNotIn(str(self.suggestion.pk), msg)
        self.assertNotIn(self.moment_type.label, msg)

    def test_suggestions_no_active_scene_reports_error(self) -> None:
        lone_room = create_object("typeclasses.rooms.Room", key="LoneRoom", nohome=True)
        self.gm_character.location = lone_room
        self.gm_character.save()

        _run(self.gm_character, "suggestions")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("no active scene", msg.lower())

    # ------------------------------------------------------------------
    # confirm
    # ------------------------------------------------------------------

    def test_gm_confirm_mints_tag(self) -> None:
        _run(self.gm_character, f"confirm {self.suggestion.pk}")

        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, SuggestionStatus.CONFIRMED)
        self.assertIsNotNone(self.suggestion.confirmed_tag)
        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("confirm", msg.lower())

    def test_non_gm_confirm_refused(self) -> None:
        _run(self.outsider_character, f"confirm {self.suggestion.pk}")

        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, SuggestionStatus.PENDING)
        self.outsider_character.msg.assert_called()
        msg = self.outsider_character.msg.call_args[0][0]
        self.assertIn("gm", msg.lower())

    def test_confirm_missing_id_is_usage_error(self) -> None:
        _run(self.gm_character, "confirm")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args_list[0][0][0]
        self.assertIn("usage", msg.lower())

    # ------------------------------------------------------------------
    # dismiss
    # ------------------------------------------------------------------

    def test_gm_dismiss_closes_out_no_tag(self) -> None:
        _run(self.gm_character, f"dismiss {self.suggestion.pk}")

        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, SuggestionStatus.DISMISSED)
        self.assertIsNone(self.suggestion.confirmed_tag)
        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("dismiss", msg.lower())

    def test_non_gm_dismiss_refused(self) -> None:
        _run(self.outsider_character, f"dismiss {self.suggestion.pk}")

        self.suggestion.refresh_from_db()
        self.assertEqual(self.suggestion.status, SuggestionStatus.PENDING)
        self.outsider_character.msg.assert_called()
        msg = self.outsider_character.msg.call_args[0][0]
        self.assertIn("gm", msg.lower())

    def test_double_confirm_second_call_fails(self) -> None:
        _run(self.gm_character, f"confirm {self.suggestion.pk}")
        _run(self.gm_character, f"confirm {self.suggestion.pk}")

        self.assertEqual(
            DramaticMomentSuggestion.objects.get(pk=self.suggestion.pk).status,
            SuggestionStatus.CONFIRMED,
        )
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("already", msg.lower())

    # ------------------------------------------------------------------
    # tag list
    # ------------------------------------------------------------------

    def test_tag_list_shows_types_for_gm(self) -> None:
        _run(self.gm_character, "tag list")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn(self.moment_type.label, msg)

    def test_non_gm_tag_list_refused(self) -> None:
        _run(self.outsider_character, "tag list")

        self.outsider_character.msg.assert_called()
        msg = self.outsider_character.msg.call_args[0][0]
        self.assertIn("gm", msg.lower())

    # ------------------------------------------------------------------
    # tag <character>=<type>
    # ------------------------------------------------------------------

    def test_gm_tag_creates_tag_and_grants_resonance(self) -> None:
        """GM tags a character — tag row created, resonance granted."""
        from world.magic.models import CharacterResonance

        target_sheet = CharacterSheetFactory()
        target_char = target_sheet.character
        CharacterResonanceFactory(
            character_sheet=target_sheet,
            resonance=self.moment_type.resonance,
        )

        _run(self.gm_character, f"tag {target_char.db_key}={self.moment_type.label}")

        from world.magic.models.dramatic_moment import DramaticMomentTag

        tag = DramaticMomentTag.objects.get(
            character_sheet=target_sheet, moment_type=self.moment_type
        )
        self.assertEqual(tag.tagged_by, self.gm_account)
        self.assertEqual(tag.scene, self.scene)
        cr = CharacterResonance.objects.get(
            character_sheet=target_sheet, resonance=self.moment_type.resonance
        )
        self.assertEqual(cr.balance, self.moment_type.resonance_amount)
        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("tagged", msg.lower())

    def test_non_gm_tag_refused(self) -> None:
        target_sheet = CharacterSheetFactory()
        target_char = target_sheet.character
        CharacterResonanceFactory(
            character_sheet=target_sheet,
            resonance=self.moment_type.resonance,
        )

        _run(self.outsider_character, f"tag {target_char.db_key}={self.moment_type.label}")

        from world.magic.models.dramatic_moment import DramaticMomentTag

        self.assertFalse(DramaticMomentTag.objects.filter(moment_type=self.moment_type).exists())
        self.outsider_character.msg.assert_called()
        msg = self.outsider_character.msg.call_args[0][0]
        self.assertIn("gm", msg.lower())

    def test_tag_unknown_type_lists_available(self) -> None:
        target_sheet = CharacterSheetFactory()
        target_char = target_sheet.character
        CharacterResonanceFactory(
            character_sheet=target_sheet,
            resonance=self.moment_type.resonance,
        )

        _run(self.gm_character, f"tag {target_char.db_key}=NonexistentType")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn(self.moment_type.label, msg)

    def test_tag_unclaimed_resonance_surfaces_error(self) -> None:
        """Target hasn't claimed the type's resonance → EndorsementValidationError."""
        target_sheet = CharacterSheetFactory()
        target_char = target_sheet.character
        # No CharacterResonance for this resonance on target_sheet

        _run(self.gm_character, f"tag {target_char.db_key}={self.moment_type.label}")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("not claimed", msg.lower())

    def test_tag_per_scene_cap_surfaces_error(self) -> None:
        """Cap already reached → DramaticMomentCapExceeded surfaces."""
        from world.magic.services.gain import create_dramatic_moment_tag

        target_sheet = CharacterSheetFactory()
        target_char = target_sheet.character
        CharacterResonanceFactory(
            character_sheet=target_sheet,
            resonance=self.moment_type.resonance,
        )
        # moment_type has per_scene_cap=1 — tag once directly via the service
        create_dramatic_moment_tag(
            character_sheet=target_sheet,
            moment_type=self.moment_type,
            tagged_by=self.gm_account,
            scene=self.scene,
        )

        _run(self.gm_character, f"tag {target_char.db_key}={self.moment_type.label}")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args[0][0]
        self.assertIn("maximum", msg.lower())

    def test_tag_missing_equals_is_usage_error(self) -> None:
        _run(self.gm_character, "tag SomeCharWithoutEquals")

        self.gm_character.msg.assert_called()
        msg = self.gm_character.msg.call_args_list[0][0][0]
        self.assertIn("usage", msg.lower())
