"""Tests for the late-selection Path recovery surface (#2121).

Covers the service (``select_initial_path``), the ``SelectPathAction``, the
telnet ``durance selectpath`` subverb, and the REST ``SelectPathViewSet``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from actions.definitions.progression_rewards import SelectPathAction
from commands.durance import CmdDurance
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.classes.models import PathStage
from world.progression.exceptions import PathAlreadySelectedError
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.selectors import current_path_for_character
from world.progression.services.advancement import select_initial_path

URL = "/api/progression/select-path/"


def _run(cmd_cls, caller, args=""):
    """Build a command instance and call func(); return the list of msg strings."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class SelectInitialPathServiceTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        self.path = PathFactory(stage=PathStage.PROSPECT)

    def test_writes_the_first_path_history_row(self) -> None:
        select_initial_path(self.character, self.path)
        self.assertEqual(current_path_for_character(self.character), self.path)

    def test_raises_when_a_path_is_already_on_record(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        other_path = PathFactory(stage=PathStage.PROSPECT)
        with self.assertRaises(PathAlreadySelectedError):
            select_initial_path(self.character, other_path)

    def test_does_not_grant_path_magic(self) -> None:
        """Deliberately narrower than cross_into_path — no gift/technique grant."""
        with patch("world.magic.services.path_magic.grant_path_magic") as mock_grant:
            select_initial_path(self.character, self.path)
        mock_grant.assert_not_called()


# ---------------------------------------------------------------------------
# Action tests
# ---------------------------------------------------------------------------


class SelectPathActionTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        self.path = PathFactory(stage=PathStage.PROSPECT)

    def test_success_writes_path_history(self) -> None:
        result = SelectPathAction().run(actor=self.character, path_id=self.path.pk)
        self.assertTrue(result.success)
        self.assertEqual(current_path_for_character(self.character), self.path)

    def test_rejects_a_non_prospect_path(self) -> None:
        advanced_path = PathFactory(stage=PathStage.POTENTIAL)
        result = SelectPathAction().run(actor=self.character, path_id=advanced_path.pk)
        self.assertFalse(result.success)
        self.assertIsNone(current_path_for_character(self.character))

    def test_fails_when_already_selected(self) -> None:
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        other_path = PathFactory(stage=PathStage.PROSPECT)
        result = SelectPathAction().run(actor=self.character, path_id=other_path.pk)
        self.assertFalse(result.success)
        self.assertIn("already selected", result.message)

    def test_fails_without_a_character_sheet(self) -> None:
        sheetless = CharacterFactory()
        result = SelectPathAction().run(actor=sheetless, path_id=self.path.pk)
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# Telnet tests
# ---------------------------------------------------------------------------


class DuranceSelectPathCommandTests(TestCase):
    def setUp(self) -> None:
        self.path = PathFactory(name="Path of Nails", stage=PathStage.PROSPECT)
        self.char = CharacterFactory(db_key="SelectPathChar")
        self.sheet = CharacterSheetFactory(character=self.char)

    def test_selectpath_by_name_dispatches_action(self) -> None:
        msgs = _run(CmdDurance, self.char, "selectpath Path of Nails")
        self.assertEqual(current_path_for_character(self.char), self.path)
        self.assertTrue(any("Path of Nails" in m for m in msgs))

    def test_selectpath_by_id_dispatches_action(self) -> None:
        _run(CmdDurance, self.char, f"selectpath {self.path.pk}")
        self.assertEqual(current_path_for_character(self.char), self.path)

    def test_selectpath_unknown_name_errors(self) -> None:
        msgs = _run(CmdDurance, self.char, "selectpath Nonexistent Path")
        self.assertTrue(any("No starting path named" in m for m in msgs))
        self.assertIsNone(current_path_for_character(self.char))

    def test_selectpath_bare_errors(self) -> None:
        msgs = _run(CmdDurance, self.char, "selectpath")
        self.assertTrue(any("Usage: durance selectpath" in m for m in msgs))


# ---------------------------------------------------------------------------
# REST tests
# ---------------------------------------------------------------------------


class SelectPathAPIBaseTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        self.path = PathFactory(stage=PathStage.PROSPECT)

        self.client = APIClient()
        self.client.force_authenticate(user=self.account)


class SelectPathGetTests(SelectPathAPIBaseTests):
    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_get_lists_prospect_options(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["current_path"] is None
        option_names = {o["name"] for o in response.data["options"]}
        assert self.path.name in option_names

    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_get_no_character_returns_404(self, mock_get_char: object) -> None:
        mock_get_char.return_value = None
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.get(URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class SelectPathPostTests(SelectPathAPIBaseTests):
    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_post_selects_path(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        response = self.client.post(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert current_path_for_character(self.character) == self.path

    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_post_rejects_non_prospect_path(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        advanced_path = PathFactory(stage=PathStage.POTENTIAL)
        response = self.client.post(URL, {"path_id": advanced_path.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_post_fails_when_already_selected(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        other_path = PathFactory(stage=PathStage.PROSPECT)
        response = self.client.post(URL, {"path_id": other_path.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.progression.views.SelectPathViewSet._get_character")
    def test_post_no_character_returns_404(self, mock_get_char: object) -> None:
        mock_get_char.return_value = None
        response = self.client.post(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_post_unauthenticated_returns_403(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
