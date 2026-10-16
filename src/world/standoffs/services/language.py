"""The language gate (#4373): who in a standoff can be talked to, and by whom.

A creature template group understands its template's ``language`` (blank: none). A named
NPC's group understands every language its character has trained fluency in. A verbal
approach (``StandoffApproach.is_verbal``) is refused when the group understands no
language, or none the actor comprehends (``comprehension_value``, so a condition that
grants understanding counts). Terms are refused only when the group has a language and the
actor comprehends none of it: a group with no language at all can still be offered terms
by gesture, as before the gate existed. Read is never gated; it is watching, not talking.
Any comprehension at all is enough (owner ruling 8 on #4121).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.standoffs.constants import REFUSAL_NO_LANGUAGE, REFUSAL_NO_SHARED_LANGUAGE

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona
    from world.species.models import Language
    from world.standoffs.models import StandoffGroup


def persona_languages(persona: Persona) -> list[Language]:
    """The languages a named NPC's character has trained fluency in, by name."""
    from world.species.models import Language  # noqa: PLC0415

    return list(
        Language.objects.filter(
            trait__character_values__character_id=persona.character_sheet_id,
            trait__character_values__value__gt=0,
        )
        .distinct()
        .order_by("name")
    )


def group_languages(group: StandoffGroup) -> list[Language]:
    """The languages a group understands: its named NPC's, or its template's one."""
    if group.persona_id is not None:
        return persona_languages(group.persona)
    template = group.creature_template
    if template is None or template.language_id is None:
        return []
    return [template.language]


def language_refusal(
    group: StandoffGroup,
    sheet: CharacterSheet,
    *,
    verbal: bool,
    languages: list[Language] | None = None,
) -> str:
    """Why ``sheet`` cannot speak to ``group`` (empty when it can).

    ``verbal`` is True for a verbal approach and False for terms; see the module docstring
    for the difference. ``languages`` lets a caller grading many entries read them once.
    """
    from world.species.language_services import comprehension_value  # noqa: PLC0415

    known = group_languages(group) if languages is None else languages
    if not known:
        return REFUSAL_NO_LANGUAGE if verbal else ""
    if any(comprehension_value(sheet, language) > 0 for language in known):
        return ""
    return REFUSAL_NO_SHARED_LANGUAGE
