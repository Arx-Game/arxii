"""Unit tests for the three signature-bonus Actions (#1582).

TDD: these tests were written to cover each subverb + each exception path.

Patch strategy: the action uses lazy imports (``from ... import`` inside execute
bodies), so the correct patch target is the *origin* service module, not the
definitions module.  E.g. ``"world.magic.services.signature.set_signature_bonus"``.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions import signature as sig_actions

# Patch paths — origin module (lazy imports in execute bodies)
_SET_SVC = "world.magic.services.signature.set_signature_bonus"
_CLEAR_SVC = "world.magic.services.signature.clear_signature_bonus"
_AVAIL_SVC = "world.magic.services.signature.available_signature_bonuses"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_thread(pk: int = 1, name: str = "Ember Thread", bonus=None) -> object:
    return type("Thread", (), {"pk": pk, "name": name, "signature_bonus": bonus})()


def _make_bonus(pk: int = 10, bonus_name: str = "Scorching Edge") -> object:
    return type("Bonus", (), {"pk": pk, "name": bonus_name})()


# ---------------------------------------------------------------------------
# SignatureActionBase metadata
# ---------------------------------------------------------------------------


class SignatureActionBaseTests(TestCase):
    def test_base_fields(self):
        base = sig_actions.SignatureActionBase()
        self.assertEqual(base.category, "magic")
        self.assertEqual(base.target_type.name, "SELF")


# ---------------------------------------------------------------------------
# SignatureSetAction
# ---------------------------------------------------------------------------


class SignatureSetActionTests(TestCase):
    def test_set_success_returns_thread_and_bonus_ids(self):
        action = sig_actions.SignatureSetAction()
        thread = _make_thread(pk=5)
        bonus = _make_bonus(pk=99)
        with patch(_SET_SVC, return_value=thread) as svc:
            result = action.execute(object(), thread=thread, bonus=bonus)
        svc.assert_called_once_with(thread, bonus)
        self.assertTrue(result.success)
        self.assertEqual(result.data["thread_id"], 5)
        self.assertEqual(result.data["bonus_id"], 99)

    def test_set_not_a_technique_thread_returns_failure(self):
        from world.magic.exceptions import NotATechniqueThread

        action = sig_actions.SignatureSetAction()
        thread = _make_thread()
        bonus = _make_bonus()
        with patch(_SET_SVC, side_effect=NotATechniqueThread):
            result = action.execute(object(), thread=thread, bonus=bonus)
        self.assertFalse(result.success)
        self.assertIn("technique thread", result.message)

    def test_set_bonus_not_available_returns_failure(self):
        from world.magic.exceptions import SignatureBonusNotAvailable

        action = sig_actions.SignatureSetAction()
        thread = _make_thread()
        bonus = _make_bonus()
        with patch(_SET_SVC, side_effect=SignatureBonusNotAvailable):
            result = action.execute(object(), thread=thread, bonus=bonus)
        self.assertFalse(result.success)
        self.assertIn("not available", result.message)

    def test_set_technique_not_owned_returns_failure(self):
        from world.magic.exceptions import TechniqueNotOwned

        action = sig_actions.SignatureSetAction()
        thread = _make_thread()
        bonus = _make_bonus()
        with patch(_SET_SVC, side_effect=TechniqueNotOwned):
            result = action.execute(object(), thread=thread, bonus=bonus)
        self.assertFalse(result.success)
        self.assertIn("technique", result.message.lower())

    def test_set_success_message_contains_bonus_and_thread_name(self):
        action = sig_actions.SignatureSetAction()
        thread = _make_thread(pk=1, name="Flame Thread")
        bonus = _make_bonus(pk=2, bonus_name="Burning Edge")
        with patch(_SET_SVC, return_value=thread):
            result = action.execute(object(), thread=thread, bonus=bonus)
        self.assertIn("Burning Edge", result.message)
        self.assertIn("Flame Thread", result.message)


# ---------------------------------------------------------------------------
# SignatureClearAction
# ---------------------------------------------------------------------------


class SignatureClearActionTests(TestCase):
    def test_clear_success_returns_thread_id(self):
        action = sig_actions.SignatureClearAction()
        thread = _make_thread(pk=7, name="Cold Thread")
        with patch(_CLEAR_SVC, return_value=thread) as svc:
            result = action.execute(object(), thread=thread)
        svc.assert_called_once_with(thread)
        self.assertTrue(result.success)
        self.assertEqual(result.data["thread_id"], 7)

    def test_clear_success_message_contains_thread_name(self):
        action = sig_actions.SignatureClearAction()
        thread = _make_thread(pk=3, name="Winter Thread")
        with patch(_CLEAR_SVC, return_value=thread):
            result = action.execute(object(), thread=thread)
        self.assertIn("Winter Thread", result.message)


# ---------------------------------------------------------------------------
# SignatureListAction
# ---------------------------------------------------------------------------


class SignatureListActionTests(TestCase):
    def test_list_no_character_returns_failure(self):
        action = sig_actions.SignatureListAction()
        # Actor has no sheet_data → _sheet returns None
        result = action.execute(object())
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())

    def test_list_success_with_no_threads_or_bonuses(self):
        action = sig_actions.SignatureListAction()
        fake_sheet = object()
        fake_actor = MagicMock()
        fake_actor.sheet_data = fake_sheet
        fake_actor.threads.all.return_value = []

        with patch(_AVAIL_SVC, return_value=[]):
            result = action.execute(fake_actor)

        self.assertTrue(result.success)
        self.assertEqual(result.data["available_bonus_ids"], [])
        self.assertEqual(result.data["technique_threads"], [])
        self.assertIn("none", result.message)

    def test_list_success_populates_data(self):
        action = sig_actions.SignatureListAction()
        fake_sheet = object()

        bonus = _make_bonus(pk=11, bonus_name="Firestorm")
        technique = type("Technique", (), {"name": "Fireball", "pk": 100})()

        # A TECHNIQUE thread with a bonus set
        thread = MagicMock()
        thread.pk = 55
        thread.name = "Fire Thread"
        thread.retired_at = None
        thread.signature_bonus = bonus
        thread.target_technique = technique
        from world.magic.constants import TargetKind

        thread.target_kind = TargetKind.TECHNIQUE

        fake_actor = MagicMock()
        fake_actor.sheet_data = fake_sheet
        fake_actor.threads.all.return_value = [thread]

        with patch(_AVAIL_SVC, return_value=[bonus]):
            result = action.execute(fake_actor)

        self.assertTrue(result.success)
        self.assertIn(11, result.data["available_bonus_ids"])
        self.assertEqual(len(result.data["technique_threads"]), 1)
        entry = result.data["technique_threads"][0]
        self.assertEqual(entry["thread_id"], 55)
        self.assertEqual(entry["technique_name"], "Fireball")
        self.assertEqual(entry["current_bonus"], "Firestorm")


# ---------------------------------------------------------------------------
# _build_list_message helper
# ---------------------------------------------------------------------------


class BuildListMessageTests(TestCase):
    def test_empty_lists_show_none_placeholders(self):
        msg = sig_actions._build_list_message([], [])
        self.assertIn("none", msg)
        self.assertIn("no active technique threads", msg)

    def test_non_empty_lists_show_names(self):
        bonus = _make_bonus(bonus_name="Searing Touch")
        thread = type(
            "T",
            (),
            {
                "signature_bonus": bonus,
                "target_technique": type("Tech", (), {"name": "Smite"})(),
            },
        )()
        msg = sig_actions._build_list_message([bonus], [thread])
        self.assertIn("Searing Touch", msg)
        self.assertIn("Smite", msg)
