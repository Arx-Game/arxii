"""
Factory definitions for character sheets system tests.

Provides efficient test data creation using factory_boy to improve
test performance and maintainability.
"""

from evennia.objects.models import ObjectDB
import factory
from factory import django

from world.character_sheets.models import (
    Characteristic,
    CharacteristicValue,
    CharacterSheet,
    CharacterSheetValue,
    Guise,
    Race,
    Subrace,
)
from world.character_sheets.types import Gender, MaritalStatus


class CharacterFactory(django.DjangoModelFactory):
    """Factory for creating test Character objects."""

    class Meta:
        model = ObjectDB

    db_key = factory.Sequence(lambda n: f"TestChar{n}")
    db_typeclass_path = "typeclasses.characters.Character"


class CharacterSheetFactory(django.DjangoModelFactory):
    """Factory for creating CharacterSheet instances."""

    class Meta:
        model = CharacterSheet

    character = factory.SubFactory(CharacterFactory)
    age = factory.Faker("random_int", min=18, max=50)
    gender = factory.Faker(
        "random_element", elements=[choice[0] for choice in Gender.choices]
    )
    concept = factory.Faker("sentence", nb_words=3)
    marital_status = MaritalStatus.SINGLE
    family = factory.Faker("last_name")
    vocation = factory.Faker("job")
    social_rank = factory.Faker("random_int", min=1, max=20)
    birthday = factory.Faker("date")
    quote = factory.Faker("sentence")
    personality = factory.Faker("paragraph")
    background = factory.Faker("paragraph")


class ObjectDisplayDataFactory(django.DjangoModelFactory):
    """Factory for creating ObjectDisplayData instances."""

    class Meta:
        model = "evennia_extensions.ObjectDisplayData"

    object = factory.SubFactory(CharacterFactory)
    longname = factory.LazyAttribute(lambda obj: f"{obj.object.db_key} the Brave")
    colored_name = factory.LazyAttribute(lambda obj: f"|c{obj.object.db_key}|n")
    permanent_description = ""


class GuiseFactory(django.DjangoModelFactory):
    """Factory for creating Guise instances."""

    class Meta:
        model = Guise

    character = factory.SubFactory(CharacterFactory)
    name = factory.LazyAttribute(lambda obj: obj.character.db_key)
    colored_name = factory.LazyAttribute(lambda obj: f"|c{obj.character.db_key}|n")
    description = ""
    is_default = True


class CharacteristicFactory(django.DjangoModelFactory):
    """Factory for creating Characteristic instances."""

    class Meta:
        model = Characteristic

    name = factory.Sequence(lambda n: f"test_characteristic_{n}")
    display_name = factory.LazyAttribute(lambda obj: obj.name.replace("_", " ").title())
    description = factory.Faker("sentence")
    is_active = True


class CharacteristicValueFactory(django.DjangoModelFactory):
    """Factory for creating CharacteristicValue instances."""

    class Meta:
        model = CharacteristicValue

    characteristic = factory.SubFactory(CharacteristicFactory)
    value = factory.Sequence(lambda n: f"value_{n}")
    display_value = factory.LazyAttribute(
        lambda obj: obj.value.replace("_", " ").title()
    )
    is_active = True


class CharacterSheetValueFactory(django.DjangoModelFactory):
    """Factory for creating CharacterSheetValue instances."""

    class Meta:
        model = CharacterSheetValue

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    characteristic_value = factory.SubFactory(CharacteristicValueFactory)


class RaceFactory(django.DjangoModelFactory):
    """Factory for creating Race instances."""

    class Meta:
        model = Race

    name = factory.Sequence(lambda n: f"TestRace{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} race"
    )
    allowed_in_chargen = True


class SubraceFactory(django.DjangoModelFactory):
    """Factory for creating Subrace instances."""

    class Meta:
        model = Subrace

    race = factory.SubFactory(RaceFactory)
    name = factory.Sequence(lambda n: f"TestSubrace{n}")
    description = factory.LazyAttribute(
        lambda obj: f"Description of the {obj.name} subrace of {obj.race.name}"
    )
    allowed_in_chargen = True


# Specialized factories for common test scenarios


class CompleteCharacterFactory:
    """Factory for creating a character with complete sheet data."""

    @classmethod
    def create(cls, character_name="TestChar", **kwargs):
        """Create a character with sheet, description, and default guise."""
        # Create the character
        character = CharacterFactory(db_key=character_name)

        # Create sheet data
        sheet = CharacterSheetFactory(character=character, **kwargs)

        # Create display data
        display_data = ObjectDisplayDataFactory(object=character)

        # Create default guise
        guise = GuiseFactory(character=character, is_default=True)

        return {
            "character": character,
            "sheet": sheet,
            "display_data": display_data,
            "guise": guise,
        }


class CharacterWithCharacteristicsFactory:
    """Factory for creating a character with physical characteristics."""

    @classmethod
    def create(cls, character_name="TestChar", characteristics=None):
        """
        Create a character with specified characteristics.

        Args:
            character_name: Name for the character
            characteristics: Dict of characteristic_name: value pairs
                          Default: {"eye_color": "blue", "hair_color": "brown"}
        """
        if characteristics is None:
            characteristics = {
                "eye_color": "blue",
                "hair_color": "brown",
                "height": "average",
                "skin_tone": "fair",
            }

        # Create complete character
        data = CompleteCharacterFactory.create(character_name)
        sheet = data["sheet"]

        # Create characteristics and values
        char_values = []
        for char_name, value in characteristics.items():
            # Create or get characteristic
            characteristic, _ = Characteristic.objects.get_or_create(
                name=char_name,
                defaults={
                    "display_name": char_name.replace("_", " ").title(),
                    "description": f"The character's {char_name.replace('_', ' ')}",
                },
            )

            # Create or get characteristic value
            char_value, _ = CharacteristicValue.objects.get_or_create(
                characteristic=characteristic,
                value=value,
                defaults={"display_value": value.replace("_", " ").title()},
            )

            # Link to character sheet
            sheet_value = CharacterSheetValueFactory(
                character_sheet=sheet, characteristic_value=char_value
            )
            char_values.append(sheet_value)

        data["characteristic_values"] = char_values
        return data


class BasicCharacteristicsSetupFactory:
    """Factory for creating the basic characteristics system used in migrations."""

    @classmethod
    def create(cls):
        """Create basic characteristics that match the migration data."""
        characteristics = {}

        # Eye colors
        eye_color, _ = Characteristic.objects.get_or_create(
            name="eye_color",
            defaults={
                "display_name": "Eye Color",
                "description": "The color of the character's eyes",
            },
        )
        eye_colors = ["blue", "green", "brown", "hazel", "gray", "amber", "violet"]
        eye_values = []
        for color in eye_colors:
            value, _ = CharacteristicValue.objects.get_or_create(
                characteristic=eye_color,
                value=color,
                defaults={"display_value": color.title()},
            )
            eye_values.append(value)

        characteristics["eye_color"] = {
            "characteristic": eye_color,
            "values": eye_values,
        }

        # Hair colors
        hair_color, _ = Characteristic.objects.get_or_create(
            name="hair_color",
            defaults={
                "display_name": "Hair Color",
                "description": "The color of the character's hair",
            },
        )
        hair_colors = [
            "black",
            "brown",
            "blonde",
            "red",
            "gray",
            "white",
            "auburn",
            "silver",
        ]
        hair_values = []
        for color in hair_colors:
            value, _ = CharacteristicValue.objects.get_or_create(
                characteristic=hair_color,
                value=color,
                defaults={"display_value": color.title()},
            )
            hair_values.append(value)

        characteristics["hair_color"] = {
            "characteristic": hair_color,
            "values": hair_values,
        }

        # Heights
        height, _ = Characteristic.objects.get_or_create(
            name="height",
            defaults={
                "display_name": "Height",
                "description": "The character's height category",
            },
        )
        heights = ["very_short", "short", "average", "tall", "very_tall"]
        height_displays = ["Very Short", "Short", "Average Height", "Tall", "Very Tall"]
        height_values = []
        for height_val, display in zip(heights, height_displays):
            value, _ = CharacteristicValue.objects.get_or_create(
                characteristic=height,
                value=height_val,
                defaults={"display_value": display},
            )
            height_values.append(value)

        characteristics["height"] = {"characteristic": height, "values": height_values}

        # Skin tones
        skin_tone, _ = Characteristic.objects.get_or_create(
            name="skin_tone",
            defaults={
                "display_name": "Skin Tone",
                "description": "The character's skin tone",
            },
        )
        skin_tones = [
            "very_pale",
            "pale",
            "fair",
            "olive",
            "tan",
            "brown",
            "dark_brown",
            "very_dark",
        ]
        tone_displays = [
            "Very Pale",
            "Pale",
            "Fair",
            "Olive",
            "Tan",
            "Brown",
            "Dark Brown",
            "Very Dark",
        ]
        tone_values = []
        for tone_val, display in zip(skin_tones, tone_displays):
            value, _ = CharacteristicValue.objects.get_or_create(
                characteristic=skin_tone,
                value=tone_val,
                defaults={"display_value": display},
            )
            tone_values.append(value)

        characteristics["skin_tone"] = {
            "characteristic": skin_tone,
            "values": tone_values,
        }

        return characteristics
