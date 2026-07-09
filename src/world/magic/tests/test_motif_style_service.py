"""Tests for the player-facing Motif style-binding service layer (#2030).

TDD: written RED-first, then made GREEN by adding
``world/magic/services/motif_style.py``.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import StyleFactory
from world.magic.exceptions import (
    StyleBindingCapExceeded,
    StyleNotBound,
    StyleResonanceUnclaimed,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    MotifFactory,
    MotifResonanceFactory,
    MotifResonanceStyleFactory,
    ResonanceFactory,
)
from world.magic.models import Motif, MotifResonance, MotifResonanceStyle
from world.magic.services.motif_style import (
    bind_motif_style,
    motif_style_bindings,
    unbind_motif_style,
)


class BindMotifStyleTests(TestCase):
    """Tests for bind_motif_style."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.other_resonance = ResonanceFactory()
        cls.style = StyleFactory(name="Seductive")

    def test_bind_creates_motif_substrate_lazily(self):
        """Binding with a claimed resonance but no Motif row creates the substrate."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.assertFalse(Motif.objects.filter(character=self.sheet).exists())

        result = bind_motif_style(self.sheet, self.style, self.resonance)

        self.assertIsInstance(result, MotifResonanceStyle)
        self.assertTrue(Motif.objects.filter(character=self.sheet).exists())
        motif_resonance = MotifResonance.objects.get(
            motif__character=self.sheet, resonance=self.resonance
        )
        self.assertFalse(motif_resonance.is_from_gift)
        self.assertEqual(result.motif_resonance, motif_resonance)
        self.assertEqual(result.style, self.style)

    def test_bind_unclaimed_resonance_raises(self):
        """No CharacterResonance row for the character/resonance raises."""
        with self.assertRaises(StyleResonanceUnclaimed):
            bind_motif_style(self.sheet, self.style, self.resonance)

    def test_bind_idempotent_same_resonance(self):
        """Binding the same style to the same resonance twice returns the existing row."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        first = bind_motif_style(self.sheet, self.style, self.resonance)
        second = bind_motif_style(self.sheet, self.style, self.resonance)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(MotifResonanceStyle.objects.filter(style=self.style).count(), 1)

    def test_bind_moves_style_between_own_resonances(self):
        """Binding an already-bound style to a different claimed resonance moves it."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.other_resonance)

        first = bind_motif_style(self.sheet, self.style, self.resonance)
        second = bind_motif_style(self.sheet, self.style, self.other_resonance)

        self.assertFalse(MotifResonanceStyle.objects.filter(pk=first.pk).exists())
        self.assertTrue(MotifResonanceStyle.objects.filter(pk=second.pk).exists())
        self.assertEqual(second.motif_resonance.resonance, self.other_resonance)
        self.assertEqual(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.sheet, style=self.style
            ).count(),
            1,
        )

    def test_bind_cap_enforced(self):
        """A 4th distinct style bound to the same resonance raises the cap exception."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        motif = MotifFactory(character=self.sheet)
        motif_resonance = MotifResonanceFactory(motif=motif, resonance=self.resonance)
        for _ in range(3):
            MotifResonanceStyleFactory(motif_resonance=motif_resonance, style=StyleFactory())
        fourth_style = StyleFactory()

        with self.assertRaises(StyleBindingCapExceeded):
            bind_motif_style(self.sheet, fourth_style, self.resonance)


class UnbindMotifStyleTests(TestCase):
    """Tests for unbind_motif_style."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.style = StyleFactory(name="Sinister")

    def test_unbind_removes_binding(self):
        """Unbinding a bound style removes the row."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        bind_motif_style(self.sheet, self.style, self.resonance)

        unbind_motif_style(self.sheet, self.style)

        self.assertFalse(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.sheet, style=self.style
            ).exists()
        )

    def test_unbind_not_bound_raises(self):
        """Unbinding a style that isn't bound raises."""
        with self.assertRaises(StyleNotBound):
            unbind_motif_style(self.sheet, self.style)


class MotifStyleBindingsTests(TestCase):
    """Tests for motif_style_bindings."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.style = StyleFactory(name="Radiant")

    def test_list_returns_bindings(self):
        """Returns the sheet's rows; empty list when no Motif exists."""
        self.assertEqual(motif_style_bindings(self.sheet), [])

        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        binding = bind_motif_style(self.sheet, self.style, self.resonance)

        result = motif_style_bindings(self.sheet)

        self.assertEqual(result, [binding])
