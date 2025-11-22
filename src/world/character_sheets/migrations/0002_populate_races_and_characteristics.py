# Generated manually for initial race data population

from django.db import migrations


def create_initial_races(apps, schema_editor):
    """Populate initial races and subraces."""
    Race = apps.get_model("character_sheets", "Race")
    Subrace = apps.get_model("character_sheets", "Subrace")

    # Create base races
    Race.objects.create(
        name="Human",
        description="The most numerous and diverse of the mortal races, humans are adaptable and ambitious, found in all walks of life throughout the realm.",
        allowed_in_chargen=True,
    )

    elven = Race.objects.create(
        name="Elven",
        description="An ancient and noble race, the elves are known for their longevity, grace, and mastery of magic and artistry. They are divided into several distinct sub-races.",
        allowed_in_chargen=True,
    )

    Race.objects.create(
        name="Khati",
        description="A proud and fierce race with feline characteristics, the Khati are skilled warriors and hunters with a strong tribal culture.",
        allowed_in_chargen=True,
    )

    Race.objects.create(
        name="Half-blood",
        description="Those of mixed heritage, often bearing traits of multiple races. Half-bloods face unique challenges but also possess diverse perspectives and abilities.",
        allowed_in_chargen=True,
    )

    # Create Elven subraces
    Subrace.objects.create(
        race=elven,
        name="Nox'alfar",
        description="The dark elves, masters of shadow and night magic. They dwell in the deep places of the world and are known for their cunning and political intrigue.",
        allowed_in_chargen=True,
    )

    Subrace.objects.create(
        race=elven,
        name="Sylv'alfar",
        description="The forest elves, guardians of the natural world. They live in harmony with nature and possess deep knowledge of the wild places.",
        allowed_in_chargen=True,
    )

    Subrace.objects.create(
        race=elven,
        name="Rex'alfar",
        description="The high elves, rulers and nobles among elvenkind. They are the most civilized and magically adept of the elven races.",
        allowed_in_chargen=True,
    )


def reverse_races(apps, schema_editor):
    """Remove initial race data."""
    Race = apps.get_model("character_sheets", "Race")
    Subrace = apps.get_model("character_sheets", "Subrace")

    # Delete in reverse order due to foreign key constraints
    Subrace.objects.all().delete()
    Race.objects.all().delete()


def add_basic_characteristics(apps, schema_editor):
    """Add basic characteristic types and values that characters can have."""
    Characteristic = apps.get_model("character_sheets", "Characteristic")
    CharacteristicValue = apps.get_model("character_sheets", "CharacteristicValue")

    # Create basic characteristic types
    eye_color = Characteristic.objects.create(
        name="eye_color",
        display_name="Eye Color",
        description="The color of the character's eyes",
    )

    hair_color = Characteristic.objects.create(
        name="hair_color",
        display_name="Hair Color",
        description="The color of the character's hair",
    )

    height = Characteristic.objects.create(
        name="height",
        display_name="Height",
        description="The character's height category",
    )

    skin_tone = Characteristic.objects.create(
        name="skin_tone",
        display_name="Skin Tone",
        description="The character's skin tone",
    )

    # Add eye color values
    eye_colors = ["blue", "green", "brown", "hazel", "gray", "amber", "violet"]
    for color in eye_colors:
        CharacteristicValue.objects.create(
            characteristic=eye_color,
            value=color,
            display_value=color.title(),
        )

    # Add hair color values
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
    for color in hair_colors:
        CharacteristicValue.objects.create(
            characteristic=hair_color,
            value=color,
            display_value=color.title(),
        )

    # Add height values
    heights = ["very_short", "short", "average", "tall", "very_tall"]
    height_displays = ["Very Short", "Short", "Average Height", "Tall", "Very Tall"]
    for height_val, display in zip(heights, height_displays, strict=False):
        CharacteristicValue.objects.create(
            characteristic=height,
            value=height_val,
            display_value=display,
        )

    # Add skin tone values
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
    for tone_val, display in zip(skin_tones, tone_displays, strict=False):
        CharacteristicValue.objects.create(
            characteristic=skin_tone,
            value=tone_val,
            display_value=display,
        )


def remove_basic_characteristics(apps, schema_editor):
    """Remove the basic characteristics if rolling back."""
    Characteristic = apps.get_model("character_sheets", "Characteristic")
    Characteristic.objects.filter(
        name__in=["eye_color", "hair_color", "height", "skin_tone"],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("character_sheets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_races, reverse_races),
        migrations.RunPython(add_basic_characteristics, remove_basic_characteristics),
    ]
