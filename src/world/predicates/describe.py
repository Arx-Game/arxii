"""Player-facing reasons for matched predicate leaves.

``matched_leaves`` says which leaves let a character through a rule; this turns
one of them into a short second-person line ("you are Cinderi") so a character's
special traits are never silently used. The text is composed from the authored
row's own display name: it displays an existing row, it designates no behavior.
"""

from __future__ import annotations

from collections.abc import Callable

from world.predicates.predicates import KEY_LEAF, KEY_PARAMS

_YOU_HAVE = "you have {}"
_YOU_ARE = "you are {}"
_UPBRINGING = "your upbringing: {}"
_BELONG = "you belong to {}"
_STANDING = "your standing in {}"


def _species(params: dict) -> str | None:
    from world.species.models import Species  # noqa: PLC0415

    row = Species.objects.filter(pk=params.get("species_id")).first()
    return _YOU_ARE.format(row.name) if row else None


def _upbringing(params: dict) -> str | None:
    from world.character_creation.models import OriginTemplate  # noqa: PLC0415

    row = OriginTemplate.objects.filter(pk=params.get("origin_template_id")).first()
    return _UPBRINGING.format(row.name) if row else None


def _distinction(params: dict) -> str | None:
    from world.distinctions.models import Distinction  # noqa: PLC0415

    row = Distinction.objects.filter(slug=params.get("slug")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _achievement(params: dict) -> str | None:
    from world.achievements.models import Achievement  # noqa: PLC0415

    row = Achievement.objects.filter(slug=params.get("slug")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _item(params: dict) -> str | None:
    from world.items.models import ItemTemplate  # noqa: PLC0415

    row = ItemTemplate.objects.filter(pk=params.get("template_id")).first()
    return _YOU_HAVE.format(row.name) if row else None


def _named(template: str, key: str) -> Callable[[dict], str | None]:
    """A leaf whose param already holds the row's display name."""

    def describe(params: dict) -> str | None:
        value = params.get(key)
        return template.format(value) if value else None

    return describe


_DESCRIBERS: dict[str, Callable[[dict], str | None]] = {
    "has_species": _species,
    "has_upbringing": _upbringing,
    "has_distinction": _distinction,
    "has_achievement": _achievement,
    "has_item": _item,
    "is_member_of_org": _named(_BELONG, "org"),
    "min_org_rank": _named(_BELONG, "org"),
    "is_member_of_society": _named(_STANDING, "society"),
    "min_society_standing": _named(_STANDING, "society"),
    "has_codex_entry": _named(_YOU_HAVE, "name"),
    "has_skill": _named(_YOU_HAVE, "skill"),
    "min_trait": _named(_YOU_HAVE, "trait"),
    "has_resonance": _named(_YOU_HAVE, "name"),
    "has_capability": _named(_YOU_HAVE, "name"),
}


def describe_leaf(leaf: dict) -> str | None:
    """A short second-person reason for a matched leaf, or None if it has none."""
    describer = _DESCRIBERS.get(leaf[KEY_LEAF])
    if describer is None:
        return None
    return describer(leaf.get(KEY_PARAMS, {}))
