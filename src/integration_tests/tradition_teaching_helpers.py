"""Helpers the Tradition teaching journeys share (#5326).

Four journey files build the same catalog (the three affinity skills, Traditions that tick
them, a mentor who holds a rating) and read the same refusal lines. They live here, beside the
harness, so a journey file imports from one place and no test module imports from another.
The lines are written out in full: they are the expected values the journeys check, never read
back from the code under test.
"""

from __future__ import annotations

from world.character_creation.sheet_writers import set_skill_values
from world.character_sheets.models import CharacterSheet
from world.magic.factories import TraditionFactory, ensure_conversion_pairs
from world.magic.models import Affinity, Tradition
from world.skills.factories import MagicSkillFactory
from world.skills.models import Skill
from world.traits.models import TraitChangeSource

TEACHER_LINE = "{skill} needs a teacher. Choose a mentor whose Tradition teaches it."
# One line for every reason a named mentor cannot teach (no Tradition, a Tradition that does not
# teach the skill, no rating), so naming a persona reveals nothing about the character behind it.
MENTOR_CANNOT_TEACH_LINE = (
    "{mentor} cannot teach you {skill}. Choose a mentor whose Tradition teaches it and who has "
    "trained in it."
)
OWN_CHARACTER_LINE = (
    "You cannot name another of your own characters as your mentor. "
    "Choose a mentor another player plays."
)


def author_the_three_skills() -> dict[str, Skill]:
    """Staff link one Magic skill to each affinity: Heroism, Reflection and Villainy.

    Returns the skills by name. Reflection is the Primal affinity's skill, so every Tradition
    teaches it; Heroism (Celestial) and Villainy (Abyssal) are taught only when ticked.
    """
    celestial, primal, abyssal = ensure_conversion_pairs()
    skills: dict[str, Skill] = {}
    for affinity, name in ((celestial, "Heroism"), (primal, "Reflection"), (abyssal, "Villainy")):
        skill = MagicSkillFactory(name=name)
        affinity.skill = skill
        affinity.save()
        skills[name] = skill
    Affinity.objects.clear_cache()
    return skills


def tradition_teaching(name: str, *ticked: Skill) -> Tradition:
    """A Tradition whose teachers teach the ticked affinity skills (and Reflection, unticked)."""
    tradition = TraditionFactory(name=name)
    tradition.taught_skills.add(*ticked)
    return tradition


def hold_rating(sheet: CharacterSheet, skill: Skill, rating: int) -> None:
    """The character leaves creation holding ``skill`` at ``rating``, as a mentor must."""
    set_skill_values(
        sheet,
        {skill: rating},
        {},
        source=TraitChangeSource.CHARACTER_CREATION,
        enforce_caps=False,
    )
