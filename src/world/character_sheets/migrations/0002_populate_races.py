# Generated manually for initial race data population

from django.db import migrations


def create_initial_races(apps, schema_editor):
    """Populate initial races and subraces."""
    Race = apps.get_model("character_sheets", "Race")
    Subrace = apps.get_model("character_sheets", "Subrace")

    # Create base races
    human = Race.objects.create(
        name="Human",
        description="The most numerous and diverse of the mortal races, humans are adaptable and ambitious, found in all walks of life throughout the realm.",
        allowed_in_chargen=True,
    )

    elven = Race.objects.create(
        name="Elven",
        description="An ancient and noble race, the elves are known for their longevity, grace, and mastery of magic and artistry. They are divided into several distinct sub-races.",
        allowed_in_chargen=True,
    )

    khati = Race.objects.create(
        name="Khati",
        description="A proud and fierce race with feline characteristics, the Khati are skilled warriors and hunters with a strong tribal culture.",
        allowed_in_chargen=True,
    )

    half_blood = Race.objects.create(
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


class Migration(migrations.Migration):

    dependencies = [
        ("character_sheets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_races, reverse_races),
    ]
