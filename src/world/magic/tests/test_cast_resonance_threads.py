"""Which threads decide the resonance a cast may be worked in (#5231, WB2 and WB3).

Unit tests because a journey cannot arrange a covenant role's thread beside a Gift the caster
does not hold, and the default for a caster with no thread is read by no screen on its own.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CharacterCovenantRoleFactory
from world.magic.exceptions import ResonanceNotOnGiftThread
from world.magic.factories import (
    AffinityFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
    ThreadFactory,
)
from world.magic.services.cast_resonance_options import cast_resonance_options
from world.magic.specialization.services import (
    _ResolvedTechnique,
    cast_resonance_for,
    resolve_specialized_variant,
)


class RoleGrantedTechniqueFormTests(TestCase):
    """A form the screen offers from a covenant role's thread is accepted, not refused."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.gift = GiftFactory()  # the caster holds no thread on it
        cls.frost = ResonanceFactory(name="Frost")
        cls.other = ResonanceFactory(name="Embers")
        cls.technique = TechniqueFactory(gift=cls.gift, name="Rimed Lash")
        cls.frost_form = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.frost,
            unlock_thread_level=10,
            name_override="Rimed Lash, frost-formed",
        )
        membership = CharacterCovenantRoleFactory(character_sheet=cls.sheet)
        ThreadFactory(
            owner=cls.sheet,
            resonance=cls.frost,
            level=10,
            as_covenant_role_thread=membership.covenant_role,
        )
        cls.hold = CharacterTechniqueFactory(
            character=cls.sheet, technique=cls.technique, role_source=membership
        )

    def test_the_role_threads_resonance_casts_in_its_form_and_another_is_still_refused(
        self,
    ) -> None:
        self.assertEqual(cast_resonance_for(self.character, self.technique, self.frost), self.frost)
        resolved = resolve_specialized_variant(
            entity=self.technique,
            character=self.character,
            character_technique=self.hold,
            preferred_resonance=self.frost,
        )
        self.assertIsInstance(resolved, _ResolvedTechnique)
        self.assertEqual(resolved.variant, self.frost_form)
        with self.assertRaises(ResonanceNotOnGiftThread):
            cast_resonance_for(self.character, self.technique, self.other)


class CasterWithNoThreadOnTheGiftTests(TestCase):
    """She is offered no choice, and her default is never the Abyssal resonance."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.abyssal = ResonanceFactory(name="Dread", affinity=AffinityFactory(name="Abyssal"))
        cls.celestial = ResonanceFactory(name="Halo", affinity=AffinityFactory(name="Celestial"))
        cls.primal = ResonanceFactory(name="Wild", affinity=AffinityFactory(name="Primal"))
        cls.gift = GiftFactory()
        cls.gift.resonances.add(cls.abyssal, cls.celestial, cls.primal)
        cls.technique = TechniqueFactory(gift=cls.gift)

    def test_the_default_is_primal_first_and_the_only_option_is_that_default(self) -> None:
        self.assertEqual(cast_resonance_for(self.character, self.technique), self.primal)
        options = cast_resonance_options(self.character, self.technique, sheet=self.sheet)
        self.assertEqual([o.resonance for o in options], [self.primal])
        self.assertTrue(options[0].is_default)
