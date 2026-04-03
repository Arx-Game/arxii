"""Shared test helpers for the fatigue system."""

from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory
from world.traits.models import TraitCategory


def setup_stat(
    character: object,
    stat_name: str,
    internal_value: int,
    category: str = TraitCategory.PHYSICAL,
) -> None:
    """Create a stat trait and assign a value to a character.

    Args:
        character: ObjectDB character instance.
        stat_name: Name of the stat (e.g. "stamina").
        internal_value: Internal scale value (e.g. 30 for display value 3).
        category: TraitCategory for the stat.
    """
    trait = StatTraitFactory(name=stat_name, category=category)
    CharacterTraitValueFactory(character=character, trait=trait, value=internal_value)
    # Clear trait handler cache so it picks up the new value
    if hasattr(character, "traits") and character.traits.initialized:
        character.traits.clear_cache()
