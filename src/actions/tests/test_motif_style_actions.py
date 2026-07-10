"""Unit tests for the three motif style-binding Actions (#2030).

TDD: written RED-first, then made GREEN by adding
``actions/definitions/motif_style.py``.

Patch strategy: the action uses lazy imports (``from ... import`` inside execute
bodies), so the correct patch target is the *origin* service module, not the
definitions module.  E.g. ``"world.magic.services.motif_style.bind_motif_style"``.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions import motif_style as motif_actions

# Patch paths — origin module (lazy imports in execute bodies)
_BIND_SVC = "world.magic.services.motif_style.bind_motif_style"
_UNBIND_SVC = "world.magic.services.motif_style.unbind_motif_style"
_LIST_SVC = "world.magic.services.motif_style.motif_style_bindings"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_style(pk: int = 1, name: str = "Seductive") -> object:
    return type("Style", (), {"pk": pk, "name": name})()


def _make_resonance(pk: int = 10, name: str = "Fire") -> object:
    return type("Resonance", (), {"pk": pk, "name": name})()


def _make_binding(pk: int = 100) -> object:
    return type("Binding", (), {"pk": pk})()


# ---------------------------------------------------------------------------
# MotifStyleActionBase metadata
# ---------------------------------------------------------------------------


class MotifStyleActionBaseTests(TestCase):
    def test_base_fields(self):
        base = motif_actions.MotifStyleActionBase()
        self.assertEqual(base.category, "magic")
        self.assertEqual(base.target_type.name, "SELF")


# ---------------------------------------------------------------------------
# BindMotifStyleAction
# ---------------------------------------------------------------------------


class BindMotifStyleActionTests(TestCase):
    def test_bind_success_returns_ids(self):
        action = motif_actions.BindMotifStyleAction()
        fake_sheet = object()
        fake_actor = MagicMock()
        fake_actor.sheet_data = fake_sheet

        style = _make_style(pk=5)
        resonance = _make_resonance(pk=9)
        binding = _make_binding(pk=42)

        with patch(_BIND_SVC, return_value=binding) as svc:
            result = action.execute(fake_actor, style=style, resonance=resonance)

        svc.assert_called_once_with(fake_sheet, style, resonance)
        self.assertTrue(result.success)
        self.assertEqual(result.data["binding_id"], 42)
        self.assertEqual(result.data["style_id"], 5)
        self.assertEqual(result.data["resonance_id"], 9)

    def test_bind_success_message_contains_style_and_resonance_name(self):
        action = motif_actions.BindMotifStyleAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        style = _make_style(name="Seductive")
        resonance = _make_resonance(name="Ember")
        binding = _make_binding()

        with patch(_BIND_SVC, return_value=binding):
            result = action.execute(fake_actor, style=style, resonance=resonance)

        self.assertIn("Seductive", result.message)
        self.assertIn("Ember", result.message)

    def test_bind_unclaimed_resonance_returns_failure(self):
        from world.magic.exceptions import StyleResonanceUnclaimed

        action = motif_actions.BindMotifStyleAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        style = _make_style()
        resonance = _make_resonance()

        with patch(_BIND_SVC, side_effect=StyleResonanceUnclaimed):
            result = action.execute(fake_actor, style=style, resonance=resonance)

        self.assertFalse(result.success)
        self.assertEqual(result.message, StyleResonanceUnclaimed.user_message)

    def test_bind_cap_exceeded_returns_failure(self):
        from world.magic.exceptions import StyleBindingCapExceeded

        action = motif_actions.BindMotifStyleAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        style = _make_style()
        resonance = _make_resonance()

        with patch(_BIND_SVC, side_effect=StyleBindingCapExceeded):
            result = action.execute(fake_actor, style=style, resonance=resonance)

        self.assertFalse(result.success)
        self.assertEqual(result.message, StyleBindingCapExceeded.user_message)

    def test_bind_no_active_character_returns_failure(self):
        action = motif_actions.BindMotifStyleAction()
        # Actor has no sheet_data → _sheet returns None
        result = action.execute(object(), style=_make_style(), resonance=_make_resonance())
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())


# ---------------------------------------------------------------------------
# UnbindMotifStyleAction
# ---------------------------------------------------------------------------


class UnbindMotifStyleActionTests(TestCase):
    def test_unbind_success_returns_style_id(self):
        action = motif_actions.UnbindMotifStyleAction()
        fake_sheet = object()
        fake_actor = MagicMock()
        fake_actor.sheet_data = fake_sheet

        style = _make_style(pk=7, name="Sinister")

        with patch(_UNBIND_SVC, return_value=None) as svc:
            result = action.execute(fake_actor, style=style)

        svc.assert_called_once_with(fake_sheet, style)
        self.assertTrue(result.success)
        self.assertEqual(result.data["style_id"], 7)
        self.assertIn("Sinister", result.message)

    def test_unbind_not_bound_returns_failure_not_raise(self):
        from world.magic.exceptions import StyleNotBound

        action = motif_actions.UnbindMotifStyleAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        style = _make_style()

        with patch(_UNBIND_SVC, side_effect=StyleNotBound):
            result = action.execute(fake_actor, style=style)

        self.assertFalse(result.success)
        self.assertEqual(result.message, StyleNotBound.user_message)

    def test_unbind_no_active_character_returns_failure(self):
        action = motif_actions.UnbindMotifStyleAction()
        result = action.execute(object(), style=_make_style())
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())


# ---------------------------------------------------------------------------
# ListMotifStylesAction
# ---------------------------------------------------------------------------


class ListMotifStylesActionTests(TestCase):
    def test_list_no_character_returns_failure(self):
        action = motif_actions.ListMotifStylesAction()
        result = action.execute(object())
        self.assertFalse(result.success)
        self.assertIn("character", result.message.lower())

    def test_list_success_with_no_bindings(self):
        action = motif_actions.ListMotifStylesAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        with patch(_LIST_SVC, return_value=[]):
            result = action.execute(fake_actor)

        self.assertTrue(result.success)
        self.assertEqual(result.data["bindings"], [])
        self.assertIn("no styles bound", result.message.lower())

    def test_list_success_populates_data(self):
        action = motif_actions.ListMotifStylesAction()
        fake_actor = MagicMock()
        fake_actor.sheet_data = object()

        style = MagicMock()
        style.pk = 5
        style.name = "Radiant"
        style.get_audacity_display.return_value = "Bold"

        resonance = MagicMock()
        resonance.pk = 9
        resonance.name = "Light"

        motif_resonance = MagicMock()
        motif_resonance.resonance_id = 9
        motif_resonance.resonance = resonance

        binding = MagicMock()
        binding.style_id = 5
        binding.style = style
        binding.motif_resonance = motif_resonance

        with patch(_LIST_SVC, return_value=[binding]):
            result = action.execute(fake_actor)

        self.assertTrue(result.success)
        self.assertEqual(len(result.data["bindings"]), 1)
        entry = result.data["bindings"][0]
        self.assertEqual(entry["style_id"], 5)
        self.assertEqual(entry["style_name"], "Radiant")
        self.assertEqual(entry["audacity"], "Bold")
        self.assertEqual(entry["resonance_id"], 9)
        self.assertEqual(entry["resonance_name"], "Light")
        self.assertIn("Radiant", result.message)


# ---------------------------------------------------------------------------
# _build_list_message helper
# ---------------------------------------------------------------------------


class BuildListMessageTests(TestCase):
    def test_empty_list_shows_placeholder(self):
        msg = motif_actions._build_list_message([])
        self.assertIn("no styles bound", msg.lower())

    def test_non_empty_list_shows_names(self):
        style = MagicMock()
        style.name = "Radiant"
        style.get_audacity_display.return_value = "Bold"

        resonance = MagicMock()
        resonance.name = "Light"

        motif_resonance = MagicMock()
        motif_resonance.resonance = resonance

        binding = MagicMock()
        binding.style = style
        binding.motif_resonance = motif_resonance

        msg = motif_actions._build_list_message([binding])
        self.assertIn("Radiant", msg)
        self.assertIn("Light", msg)
