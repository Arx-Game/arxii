"""CharacterContent — creates characters with social traits for pipeline tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.scenes.models import Persona

# Social stat names matched to CheckType trait weights in factories.py
_SOCIAL_STAT_NAMES = ["presence", "strength", "charm", "intellect", "wits", "willpower"]

# Trait value giving ~50 points (with 1-pt-per-level STAT conversion range)
_SOCIAL_TRAIT_VALUE = 50

# Physical/mental stat names for challenge testing
_CHALLENGE_STAT_NAMES = ["strength", "agility", "perception", "intellect", "wits"]

# Trait value giving ~50 points (with 1-pt-per-level STAT conversion range)
_CHALLENGE_TRAIT_VALUE = 50


class CharacterContent:
    """Creates characters pre-loaded with social traits for integration tests."""

    @staticmethod
    def create_base_social_character(
        *,
        name: str | None = None,
    ) -> tuple[ObjectDB, Persona]:
        """Create a character with social trait values and a PRIMARY persona.

        Sets up CharacterTraitValue records for all 6 social stats at value 50,
        giving 50 total points via the 1-point-per-level STAT conversion range.
        With CheckRank thresholds at 0/30/60, a trait total of 50 maps to rank 1.

        Args:
            name: Optional character name (defaults to factory sequence name).

        Returns:
            Tuple of (ObjectDB character, PRIMARY Persona).
        """
        from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
        from world.character_sheets.factories import (  # noqa: PLC0415
            CharacterIdentityFactory,
        )
        from world.magic.factories import CharacterAnimaFactory  # noqa: PLC0415
        from world.traits.factories import StatTraitFactory  # noqa: PLC0415
        from world.traits.models import CharacterTraitValue  # noqa: PLC0415

        kwargs: dict[str, object] = {}
        if name is not None:
            kwargs["db_key"] = name

        character = CharacterFactory(**kwargs)
        identity = CharacterIdentityFactory(character=character)
        persona = identity.active_persona

        # CharacterIdentityFactory already ensures the sheet exists.
        CharacterAnimaFactory(character=character, current=20, maximum=30)

        for stat_name in _SOCIAL_STAT_NAMES:
            trait = StatTraitFactory(name=stat_name)
            CharacterTraitValue.objects.get_or_create(
                character=character,
                trait=trait,
                defaults={"value": _SOCIAL_TRAIT_VALUE},
            )

        return character, persona

    @staticmethod
    def create_base_challenge_character(
        *,
        name: str | None = None,
    ) -> tuple[ObjectDB, Persona]:
        """Create a character with physical/mental trait values and a PRIMARY persona.

        Sets up CharacterTraitValue records for 5 physical/mental stats at value 50,
        giving 50 total points via the 1-point-per-level STAT conversion range.

        Args:
            name: Optional character name (defaults to factory sequence name).

        Returns:
            Tuple of (ObjectDB character, PRIMARY Persona).
        """
        from evennia_extensions.factories import CharacterFactory  # noqa: PLC0415
        from world.character_sheets.factories import (  # noqa: PLC0415
            CharacterIdentityFactory,
        )
        from world.magic.factories import CharacterAnimaFactory  # noqa: PLC0415
        from world.traits.factories import StatTraitFactory  # noqa: PLC0415
        from world.traits.models import CharacterTraitValue  # noqa: PLC0415

        kwargs: dict[str, object] = {}
        if name is not None:
            kwargs["db_key"] = name

        character = CharacterFactory(**kwargs)
        identity = CharacterIdentityFactory(character=character)
        persona = identity.active_persona

        # CharacterIdentityFactory already ensures the sheet exists.
        CharacterAnimaFactory(character=character, current=20, maximum=30)

        for stat_name in _CHALLENGE_STAT_NAMES:
            trait = StatTraitFactory(name=stat_name)
            CharacterTraitValue.objects.get_or_create(
                character=character,
                trait=trait,
                defaults={"value": _CHALLENGE_TRAIT_VALUE},
            )

        return character, persona
