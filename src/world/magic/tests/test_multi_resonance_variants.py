"""Tests for multi-resonance GIFT threads and cast-time variant selection (#1619).

A character may hold multiple active GIFT threads on the same gift at
different resonances. ``gift_resonances_for`` returns all of them, and the
resolver accepts a ``preferred_resonance`` to select which variant manifests
at cast time.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    gift_resonances_for,
    provision_additional_gift_thread,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)


class MultiResonanceTests(TestCase):
    """Multiple GIFT threads per gift at different resonances."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.celestial = ResonanceFactory(name="Celestial")
        cls.abyssal = ResonanceFactory(name="Abyssal")
        cls.gift.resonances.add(cls.celestial, cls.abyssal)

        cls.technique = TechniqueFactory(gift=cls.gift)

        cls.celestial_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.celestial,
            unlock_thread_level=3,
            name_override="Celestial Form",
            intensity_delta=5,
        )
        cls.abyssal_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.abyssal,
            unlock_thread_level=3,
            name_override="Abyssal Form",
            intensity_delta=10,
        )

    def _level_thread(self, resonance) -> Thread:
        """Provision and level a GIFT thread at the given resonance."""
        provision_latent_gift_thread(self.sheet, self.gift, resonance=resonance)
        thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=resonance,
        )
        thread.level = 3
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        return thread

    def test_provision_additional_gift_thread(self) -> None:
        """provision_additional_gift_thread creates a second thread at a different resonance."""
        self._level_thread(self.celestial)

        # Add a second resonance.
        abyssal_thread = provision_additional_gift_thread(
            self.sheet, self.gift, resonance=self.abyssal
        )
        self.assertEqual(abyssal_thread.resonance_id, self.abyssal.pk)
        self.assertEqual(abyssal_thread.level, 0)
        self.assertEqual(abyssal_thread.target_kind, TargetKind.GIFT)

        # Both threads exist.
        threads = Thread.objects.filter(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            retired_at__isnull=True,
        )
        self.assertEqual(threads.count(), 2)

    def test_provision_additional_rejects_unsupported_resonance(self) -> None:
        """provision_additional_gift_thread rejects a resonance not in the gift's supported set."""
        from world.magic.exceptions import UnsupportedGiftResonanceError

        self._level_thread(self.celestial)
        primal = ResonanceFactory(name="Primal")

        with self.assertRaises(UnsupportedGiftResonanceError):
            provision_additional_gift_thread(self.sheet, self.gift, resonance=primal)

    def test_provision_latent_idempotent_on_same_resonance(self) -> None:
        """provision_latent_gift_thread is idempotent on (owner, gift, resonance)."""
        t1 = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.celestial)
        t2 = provision_latent_gift_thread(self.sheet, self.gift, resonance=self.celestial)
        self.assertEqual(t1.pk, t2.pk)

    def test_gift_resonances_for_returns_multiple(self) -> None:
        """gift_resonances_for returns all GIFT thread resonances when multiple exist."""
        self._level_thread(self.celestial)
        self._level_thread(self.abyssal)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        pks = {r.pk for r in resonances}
        self.assertEqual(pks, {self.celestial.pk, self.abyssal.pk})

    def test_gift_resonances_for_single_when_one_thread(self) -> None:
        """gift_resonances_for returns a single-element list when only one thread exists."""
        self._level_thread(self.celestial)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

    def test_resolver_without_preferred_returns_first_thread_variant(self) -> None:
        """Without preferred_resonance, the resolver uses the first GIFT thread."""
        self._level_thread(self.celestial)
        self._level_thread(self.abyssal)

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        # Without a preferred resonance, the first thread found is used.
        # The resolver iterates the cached thread list; either variant is valid.
        self.assertIn(resolved.name, ("Celestial Form", "Abyssal Form"))

    def test_resolver_with_preferred_celestial(self) -> None:
        """preferred_resonance=celestial selects the Celestial variant."""
        self._level_thread(self.celestial)
        self._level_thread(self.abyssal)

        resolved = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=self.celestial,
        )
        self.assertEqual(resolved.name, "Celestial Form")
        self.assertEqual(resolved.intensity, self.technique.intensity + 5)

    def test_resolver_with_preferred_abyssal(self) -> None:
        """preferred_resonance=abyssal selects the Abyssal variant."""
        self._level_thread(self.celestial)
        self._level_thread(self.abyssal)

        resolved = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=self.abyssal,
        )
        self.assertEqual(resolved.name, "Abyssal Form")
        self.assertEqual(resolved.intensity, self.technique.intensity + 10)

    def test_resolver_preferred_resonance_no_matching_variant(self) -> None:
        """When preferred_resonance has no variant, the parent technique resolves."""
        self._level_thread(self.celestial)
        # Add a third resonance with no variant.
        primal = ResonanceFactory(name="Primal")
        self.gift.resonances.add(primal)
        provision_additional_gift_thread(self.sheet, self.gift, resonance=primal)
        self.sheet.character.threads.invalidate()
        # Level the primal thread too.
        primal_thread = Thread.objects.get(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            resonance=primal,
        )
        primal_thread.level = 3
        primal_thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

        resolved = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=primal,
        )
        # No variant at the Primal resonance → parent technique unchanged.
        self.assertEqual(resolved.name, self.technique.name)
        self.assertEqual(resolved.intensity, self.technique.intensity)

    def test_resolver_preferred_uses_thread_level_from_preferred_resonance(self) -> None:
        """The thread level is read from the thread at the preferred resonance."""
        # Level celestial to 3, abyssal stays at 0.
        self._level_thread(self.celestial)
        provision_additional_gift_thread(self.sheet, self.gift, resonance=self.abyssal)
        self.sheet.character.threads.invalidate()

        # Abyssal thread is level 0 — below the variant unlock threshold (3).
        resolved = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=self.abyssal,
        )
        # No variant unlocks at level 0 → parent technique.
        self.assertEqual(resolved.name, self.technique.name)

        # Celestial thread is level 3 — variant unlocks.
        resolved_celestial = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=self.celestial,
        )
        self.assertEqual(resolved_celestial.name, "Celestial Form")

    def test_preferred_resonance_overrides_alt_self(self) -> None:
        """preferred_resonance takes priority over the alt-self resonance."""
        from world.forms.factories import (
            AlternateSelfFactory,
            CharacterFormFactory,
            CharacterFormStateFactory,
        )
        from world.forms.models import FormType
        from world.forms.services import assume_alternate_self

        self._level_thread(self.celestial)
        self._level_thread(self.abyssal)

        # Set up form state for assume_alternate_self.
        true_form = CharacterFormFactory(
            character=self.sheet.character, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=self.sheet.character, active_form=true_form)

        # Assume an alt-self with the Abyssal resonance.
        alt = AlternateSelfFactory(
            character=self.sheet,
            resonance=self.abyssal,
            display_name="Abyssal Alter-Ego",
        )
        assume_alternate_self(self.sheet, alt)

        # Without preferred_resonance: alt-self resonance (Abyssal) wins.
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved.name, "Abyssal Form")

        # With preferred_resonance=celestial: preferred wins over alt-self.
        resolved_pref = resolve_specialized_variant(
            entity=self.technique,
            character=self.sheet.character,
            preferred_resonance=self.celestial,
        )
        self.assertEqual(resolved_pref.name, "Celestial Form")
