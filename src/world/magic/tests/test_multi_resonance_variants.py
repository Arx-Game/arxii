"""One GIFT thread holding several resonances and cast-time variant selection (#1619, #5123).

A gift has one thread per character, with a ThreadResonance row per resonance it holds.
``gift_resonances_for`` returns them in row order, and the resolver accepts a
``preferred_resonance`` to select which variant manifests at cast time.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import FormType
from world.forms.services import assume_alternate_self
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.magic.services.threads import weave_thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import (
    gift_resonances_for,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)


class MultiResonanceTests(TestCase):
    """A GIFT thread with rows for several resonances."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gift = GiftFactory()
        cls.celestial = ResonanceFactory(name="Celestial")
        cls.abyssal = ResonanceFactory(name="Abyssal")
        cls.primal = ResonanceFactory(name="Primal")
        cls.gift.resonances.add(cls.celestial, cls.abyssal, cls.primal)

        cls.technique = TechniqueFactory(gift=cls.gift)
        cls.celestial_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.celestial,
            unlock_thread_level=30,
            name_override="Celestial Form",
            intensity_delta=5,
        )
        cls.abyssal_variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.abyssal,
            unlock_thread_level=30,
            name_override="Abyssal Form",
            intensity_delta=10,
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def _thread(self, *resonances, level: int = 30):
        """The gift thread holding ``resonances`` (leading first), at ``level``."""
        thread = provision_latent_gift_thread(self.sheet, self.gift, resonances=list(resonances))
        thread.level = level
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        return thread

    def _resolve(self, **kwargs):
        return resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character, **kwargs
        )

    def _assume_alt_self(self, resonance) -> None:
        true_form = CharacterFormFactory(character=self.sheet, name="True", form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.sheet, active_form=true_form)
        alt = AlternateSelfFactory(character=self.sheet, resonance=resonance)
        assume_alternate_self(self.sheet, alt)

    def test_weave_takes_a_resonance_off_the_gifts_list(self) -> None:
        """A gift's ``resonances`` list limits nothing: any resonance can be woven (#5123)."""
        outsider = ResonanceFactory(name="Outsider")

        thread = weave_thread(self.sheet, TargetKind.GIFT, self.gift, outsider)

        self.assertEqual(thread.resonance, outsider)

    def test_provision_latent_idempotent_on_the_gift(self) -> None:
        t1 = provision_latent_gift_thread(self.sheet, self.gift, resonances=[self.celestial])
        t2 = provision_latent_gift_thread(self.sheet, self.gift, resonances=[self.abyssal])
        self.assertEqual(t1.pk, t2.pk)

    def test_gift_resonances_for_single_when_one_row(self) -> None:
        self._thread(self.celestial)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in resonances], [self.celestial.pk])

    def test_gift_resonances_for_returns_every_row(self) -> None:
        self._thread(self.celestial, self.abyssal, self.primal)

        resonances = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual(
            [r.pk for r in resonances], [self.celestial.pk, self.abyssal.pk, self.primal.pk]
        )

    def test_resolver_without_preferred_uses_the_leading_resonance(self) -> None:
        """No pick and no alternate self: the thread's leading resonance picks the variant."""
        self._thread(self.abyssal, self.celestial)

        self.assertEqual(self._resolve().name, "Abyssal Form")

    def test_resolver_with_preferred_resonance(self) -> None:
        self._thread(self.celestial, self.abyssal)

        celestial = self._resolve(preferred_resonance=self.celestial)
        abyssal = self._resolve(preferred_resonance=self.abyssal)

        self.assertEqual(celestial.name, "Celestial Form")
        self.assertEqual(celestial.intensity, self.technique.intensity + 5)
        self.assertEqual(abyssal.name, "Abyssal Form")
        self.assertEqual(abyssal.intensity, self.technique.intensity + 10)

    def test_resolver_preferred_resonance_no_matching_variant(self) -> None:
        """When the preferred resonance has no variant, the parent technique resolves."""
        self._thread(self.celestial, self.primal)

        resolved = self._resolve(preferred_resonance=self.primal)

        self.assertEqual(resolved.name, self.technique.name)
        self.assertEqual(resolved.intensity, self.technique.intensity)

    def test_preferred_resonance_uses_the_threads_level(self) -> None:
        """The one thread's level gates the variant, whichever resonance is preferred."""
        self._thread(self.celestial, self.abyssal, level=29)
        self.assertEqual(self._resolve(preferred_resonance=self.abyssal).name, self.technique.name)

        thread = self._thread(self.celestial, self.abyssal, level=30)
        self.assertEqual(thread.level, 30)
        self.assertEqual(self._resolve(preferred_resonance=self.abyssal).name, "Abyssal Form")

    def test_preferred_resonance_beats_alt_self_beats_leading(self) -> None:
        """Preferred, then the worn alternate self's resonance, then the thread's leading one."""
        self._thread(self.celestial, self.abyssal)  # Celestial leads
        self.assertEqual(self._resolve().name, "Celestial Form")

        self._assume_alt_self(self.abyssal)
        self.assertEqual(self._resolve().name, "Abyssal Form")

        self.assertEqual(self._resolve(preferred_resonance=self.celestial).name, "Celestial Form")

    def test_gift_resonances_for_not_affected_by_alt_self(self) -> None:
        """The alternate self's resonance changes the variant, not the gift's resonances."""
        self._thread(self.celestial, self.abyssal)
        self._assume_alt_self(self.abyssal)

        resonances = gift_resonances_for(self.sheet.character, self.gift)

        self.assertEqual([r.pk for r in resonances], [self.celestial.pk, self.abyssal.pk])
