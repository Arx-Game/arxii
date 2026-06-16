"""
Factory definitions for character sheets system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

from __future__ import annotations

import factory
import factory.django as factory_django

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.models import (
    CharacterSheet,
    Gender,
    Pronouns,
)
from world.character_sheets.types import MaritalStatus


class GenderFactory(factory_django.DjangoModelFactory):
    """Factory for creating Gender instances."""

    class Meta:
        model = Gender
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"gender_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.key.replace("_", " ").title())
    is_default = False


class PronounsFactory(factory_django.DjangoModelFactory):
    """Factory for creating Pronouns instances."""

    class Meta:
        model = Pronouns
        django_get_or_create = ("key",)

    key = factory.Sequence(lambda n: f"pronouns_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.key.replace("_", " ").title())
    subject = "they"
    object = "them"
    possessive = "their"
    is_default = False


class CharacterSheetFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterSheet instances."""

    class Meta:
        model = CharacterSheet
        django_get_or_create = ("character",)

    character = factory.SubFactory(CharacterFactory)
    age = factory.Faker("random_int", min=18, max=50)
    # gender and pronouns are now FKs - leave null for basic factory
    concept = factory.Faker("sentence", nb_words=3)
    marital_status = MaritalStatus.SINGLE
    family = None  # FK to roster.Family
    vocation = factory.Faker("job")
    social_rank = factory.Faker("random_int", min=1, max=20)
    birthday = factory.Faker("date")
    quote = factory.Faker("sentence")
    personality = factory.Faker("paragraph")
    background = factory.Faker("paragraph")

    @factory.post_generation
    def primary_persona(
        self: CharacterSheet,
        create: bool,
        extracted: object,
        **kwargs: object,
    ) -> None:
        """Ensure every sheet has a PRIMARY persona (the invariant).

        Idempotent: if a PRIMARY persona already exists for this character,
        link it to the sheet. Otherwise create a new PRIMARY persona for it.

        Pass ``primary_persona=False`` to opt out.
        """
        if not create:
            return
        if extracted is False:
            return

        from world.scenes.constants import PersonaType
        from world.scenes.models import Persona

        existing_primary = Persona.objects.filter(
            character_sheet=self,
            persona_type=PersonaType.PRIMARY,
        ).first()

        if existing_primary is not None:
            return

        Persona.objects.create(
            character_sheet=self,
            name=self.character.db_key,
            persona_type=PersonaType.PRIMARY,
        )

    @factory.post_generation
    def _path_stage(
        self: CharacterSheet,
        create: bool,
        extracted: object,
        **kwargs: object,
    ) -> None:
        """Add a CharacterPathHistory row for the given stage integer.

        Pass ``_path_stage=<int>`` to create a Path of that stage and a
        corresponding history entry on the character. Used by cap-helper tests
        (Phase 10 of the Resonance Pivot, Spec A §2.4).
        """
        if not create or extracted is None:
            return
        stage = int(extracted)  # type: ignore[arg-type]
        from world.classes.factories import PathFactory
        from world.progression.models.paths import CharacterPathHistory

        path = PathFactory(stage=stage)
        CharacterPathHistory.objects.create(character=self.character, path=path)


class ObjectDisplayDataFactory(factory_django.DjangoModelFactory):
    """Factory for creating ObjectDisplayData instances."""

    class Meta:
        model = "evennia_extensions.ObjectDisplayData"

    object = factory.SubFactory(CharacterFactory)
    longname = factory.LazyAttribute(lambda obj: f"{obj.object.db_key} the Brave")
    colored_name = factory.LazyAttribute(lambda obj: f"|c{obj.object.db_key}|n")
    permanent_description = ""


# Specialized factories for common test scenarios


class CompleteCharacterFactory:
    """Factory for creating a character with complete sheet data."""

    @classmethod
    def create(
        cls,
        character_name: str = "TestChar",
        **kwargs: object,
    ) -> dict:
        """Create a character with sheet and display data.

        CharacterSheetFactory's post_generation hook ensures a PRIMARY
        Persona exists for the sheet, so the returned sheet is fully wired.
        """
        # Create the character
        character = CharacterFactory(db_key=character_name)

        # Create sheet data (post_generation creates the PRIMARY persona)
        sheet = CharacterSheetFactory(character=character, **kwargs)

        # Create display data
        display_data = ObjectDisplayDataFactory(object=character)

        return {
            "character": character,
            "sheet": sheet,
            "display_data": display_data,
        }


class CharacterWithCharacteristicsFactory:
    """Create a character with appearance traits (FormTrait-backed).

    Keeps the legacy ``characteristics={name: value}`` interface so callers read
    unchanged, but builds the character's TRUE-form ``FormTrait`` values — the single
    appearance source. ``height`` is a no-op here (it lives on the height system, not
    a FormTrait).
    """

    @classmethod
    def create(
        cls,
        character_name: str = "TestChar",
        characteristics: dict[str, str] | None = None,
    ) -> dict:
        if characteristics is None:
            characteristics = {
                "eye_color": "blue",
                "hair_color": "brown",
                "skin_tone": "fair",
            }

        from world.forms.factories import CharacterFormValueFactory
        from world.forms.models import CharacterForm, FormTrait, FormTraitOption, FormType

        data = CompleteCharacterFactory.create(character_name)
        character = data["character"]

        form, _ = CharacterForm.objects.get_or_create(character=character, form_type=FormType.TRUE)
        for char_name, value in characteristics.items():
            # Height isn't a FormTrait (test shim); it lives on the height system.
            if char_name == "height":  # noqa: STRING_LITERAL
                continue
            trait, _ = FormTrait.objects.get_or_create(
                name=char_name,
                defaults={"display_name": char_name.replace("_", " ").title()},
            )
            option, _ = FormTraitOption.objects.get_or_create(
                trait=trait,
                name=str(value).lower(),
                defaults={"display_name": str(value).replace("_", " ").title()},
            )
            CharacterFormValueFactory(form=form, trait=trait, option=option)

        return data
