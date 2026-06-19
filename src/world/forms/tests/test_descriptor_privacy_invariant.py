"""The descriptor privacy invariant (#1109, slice 2).

> A descriptor is authored independently per persona and never auto-attaches from another
> persona of the same character — blank by default, no "copy from my real face" pre-fill,
> no template that carries it over.

Outing-by-descriptor is only possible when one distinctive string lands on two personas of
the *same* character. The structural absence of any copy/pre-fill path makes accidental
cross-persona sameness impossible; deliberate reuse (a chosen tell) stays available because
each descriptor is authored explicitly. These tests pin that guarantee.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.factories import FormTraitFactory, PersonaTraitDescriptorFactory
from world.forms.models import PersonaTraitDescriptor
from world.scenes.factories import PersonaFactory


class DescriptorPrivacyInvariantTests(TestCase):
    def test_a_new_persona_is_born_with_no_descriptors(self) -> None:
        sheet = CharacterSheetFactory()
        # The PRIMARY persona created with the sheet carries no descriptors.
        assert not PersonaTraitDescriptor.objects.filter(persona=sheet.primary_persona).exists()
        # A freshly created sibling persona is likewise blank.
        sibling = PersonaFactory(character_sheet=sheet)
        assert not PersonaTraitDescriptor.objects.filter(persona=sibling).exists()

    def test_a_sibling_descriptor_never_attaches_to_another_face(self) -> None:
        """Bob's "Rusty Auburn" must never bleed onto Robert — the core outing guard."""
        sheet = CharacterSheetFactory()
        bob = sheet.primary_persona
        trait = FormTraitFactory()
        PersonaTraitDescriptorFactory(persona=bob, trait=trait, text="Rusty Auburn")

        # Creating Robert on the same body copies nothing.
        robert = PersonaFactory(character_sheet=sheet)

        assert not PersonaTraitDescriptor.objects.filter(persona=robert).exists()
        # Bob keeps his; Robert has none for that trait — no cross-persona sameness.
        assert PersonaTraitDescriptor.objects.get(persona=bob, trait=trait).text == "Rusty Auburn"
        assert not PersonaTraitDescriptor.objects.filter(persona=robert, trait=trait).exists()

    def test_deliberate_reuse_is_allowed_because_each_is_authored_explicitly(self) -> None:
        """A chosen tell (the same descriptor on two faces) is permitted — only the
        accidental/default carry-over is structurally impossible. Authoring each on purpose
        is the supported path, so the same string can appear twice when intended."""
        sheet = CharacterSheetFactory()
        bob = sheet.primary_persona
        robert = PersonaFactory(character_sheet=sheet)
        trait = FormTraitFactory()

        PersonaTraitDescriptorFactory(persona=bob, trait=trait, text="a livid scar")
        PersonaTraitDescriptorFactory(persona=robert, trait=trait, text="a livid scar")

        assert PersonaTraitDescriptor.objects.filter(trait=trait, text="a livid scar").count() == 2
