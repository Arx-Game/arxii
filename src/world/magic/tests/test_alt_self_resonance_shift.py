"""Tests for alt-self resonance shift (#1619).

When a character assumes an ``AlternateSelf`` that carries a ``resonance``
FK, the variant resolver and ``gift_resonances_for`` must use that resonance
instead of the GIFT thread's own resonance. The thread's *level* still gates
which variant tier unlocks — only the resonance axis shifts.

Derive-on-read (ADR-0014): no snapshot, no write-on-assume. The shift is
immediate on assumption and reverts on revert.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import FormType
from world.forms.services import assume_alternate_self, revert_alternate_self
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    _active_alt_self_resonance,
    gift_resonances_for,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)


class AltSelfResonanceShiftTests(TestCase):
    """Variant resolution shifts to the alt-self's resonance on assumption."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        # CharacterSheetFactory already creates a PRIMARY persona.
        # assume_alternate_self / revert need a CharacterFormState.
        cls.true_form = CharacterFormFactory(
            character=cls.sheet.character, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.sheet.character, active_form=cls.true_form)

        cls.gift = GiftFactory()
        # The character's "native" resonance (e.g. Celestial).
        cls.celestial = ResonanceFactory(name="Celestial")
        cls.gift.resonances.add(cls.celestial)

        # The alt-self's resonance (e.g. Abyssal).
        cls.abyssal = ResonanceFactory(name="Abyssal")

        cls.technique = TechniqueFactory(gift=cls.gift)

        # A variant at the Celestial resonance (the "native" form).
        cls.celestial_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.celestial,
            unlock_thread_level=3,
            name_override="Celestial Form",
            intensity_delta=5,
        )
        # A variant at the Abyssal resonance (the "alt-self" form).
        cls.abyssal_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.abyssal,
            unlock_thread_level=3,
            name_override="Abyssal Form",
            intensity_delta=10,
        )

    def _provision_and_level_thread(self) -> Thread:
        """Provision a GIFT thread at the Celestial resonance and level it to 3."""
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.celestial)
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
        )
        thread.level = 3
        thread.save(update_fields=["level"])
        # Invalidate the cached thread handler so the new level is visible.
        self.sheet.character.threads.invalidate()
        return thread

    def test_no_alt_self_uses_thread_resonance(self) -> None:
        """Without an active alt-self, the resolver uses the thread's resonance."""
        self._provision_and_level_thread()

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Celestial Form")
        self.assertEqual(resolved.intensity, self.technique.intensity + 5)

    def test_alt_self_resonance_shifts_variant(self) -> None:
        """Assuming an alt-self with a resonance shifts variant resolution."""
        self._provision_and_level_thread()

        # Create and assume an alt-self with the Abyssal resonance.
        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
            display_name="Abyssal Alter-Ego",
        )
        assume_alternate_self(self.sheet, alt)

        # The resolver should now return the Abyssal variant, not the Celestial one.
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Abyssal Form")
        self.assertEqual(resolved.intensity, self.technique.intensity + 10)

    def test_revert_restores_thread_resonance(self) -> None:
        """Reverting the alt-self restores the thread's native resonance."""
        self._provision_and_level_thread()

        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
            display_name="Abyssal Alter-Ego",
        )
        assume_alternate_self(self.sheet, alt)
        revert_alternate_self(self.sheet)

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Celestial Form")

    def test_alt_self_without_resonance_uses_thread_resonance(self) -> None:
        """An alt-self with no resonance FK does not shift variant resolution."""
        self._provision_and_level_thread()

        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=None,
            display_name="Non-magical disguise",
        )
        assume_alternate_self(self.sheet, alt)

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Celestial Form")

    def test_gift_resonances_for_returns_thread_resonance_not_alt_self(self) -> None:
        """gift_resonances_for returns the thread's resonance, not the alt-self's.

        The alt-self resonance override is applied in the variant resolver
        (_resolve_technique_variant), not in gift_resonances_for — to avoid
        an extra DB query in the cast pipeline. This test documents that
        contract: gift_resonances_for always reads from the GIFT thread.
        """
        self._provision_and_level_thread()

        # Before assumption: returns the thread's resonance.
        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
            display_name="Abyssal Alter-Ego",
        )
        assume_alternate_self(self.sheet, alt)

        # After assumption: still returns the thread's resonance (not alt-self's).
        # The alt-self override is the resolver's job.
        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

    def test_gift_resonances_for_unchanged_after_revert(self) -> None:
        """gift_resonances_for always returns the thread's resonance (no alt-self effect)."""
        self._provision_and_level_thread()

        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
            display_name="Abyssal Alter-Ego",
        )
        assume_alternate_self(self.sheet, alt)
        revert_alternate_self(self.sheet)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

    def test_active_alt_self_resonance_helper(self) -> None:
        """The _active_alt_self_resonance helper returns None / resonance correctly."""
        self._provision_and_level_thread()

        # No active alt-self → None.
        self.assertIsNone(_active_alt_self_resonance(self.sheet))

        # Alt-self with resonance → that resonance.
        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
        )
        assume_alternate_self(self.sheet, alt)
        self.assertEqual(_active_alt_self_resonance(self.sheet), self.abyssal)

        # After revert → None.
        revert_alternate_self(self.sheet)
        self.assertIsNone(_active_alt_self_resonance(self.sheet))

    def test_alt_self_resonance_with_no_matching_variant(self) -> None:
        """If the alt-self's resonance has no variant, the parent technique resolves."""
        self._provision_and_level_thread()

        # A resonance with no variant rows at all.
        third_resonance = ResonanceFactory(name="Primal")
        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=third_resonance,
        )
        assume_alternate_self(self.sheet, alt)

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        # No variant at the Primal resonance → parent technique unchanged.
        self.assertEqual(resolved.name, self.technique.name)
        self.assertEqual(resolved.intensity, self.technique.intensity)
