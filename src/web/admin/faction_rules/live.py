"""Read-only context for the Faction Rules page's rail (#4361)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Q

from world.combat.models import CreatureTemplate
from world.missions.models import MissionOptionOpponentLine
from world.societies.association import org_and_descendant_ids
from world.societies.models import Organization, Society
from world.stories.models import BeatOpponentLine

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@dataclass(frozen=True)
class Reach:
    """What an owner's rules reach: who inherits them."""

    child_organizations: list[str]
    templates: list[str]
    placements: int


def _reach_for_orgs(org_ids: set[int], children: list[str]) -> Reach:
    templates = CreatureTemplate.objects.filter(organization_id__in=org_ids).order_by("name")
    template_ids = [t.pk for t in templates]
    line_filter = Q(organization_id__in=org_ids) | Q(
        organization__isnull=True, creature_template_id__in=template_ids
    )
    placements = (
        BeatOpponentLine.objects.filter(line_filter).count()
        + MissionOptionOpponentLine.objects.filter(line_filter).count()
    )
    return Reach(
        child_organizations=children,
        templates=[t.name for t in templates],
        placements=placements,
    )


def organization_reach(organization: Organization) -> Reach:
    """Organizations below this one, the templates affiliated with any of them, placements."""
    org_ids = org_and_descendant_ids(organization)
    children = list(
        Organization.objects.filter(pk__in=org_ids - {organization.pk})
        .order_by("name")
        .values_list("name", flat=True)
    )
    return _reach_for_orgs(org_ids, children)


def society_reach(society: Society) -> Reach:
    """The society's organizations, the templates affiliated with them, placements."""
    orgs = list(Organization.objects.filter(society=society).order_by("name"))
    return _reach_for_orgs({org.pk for org in orgs}, [org.name for org in orgs])


def find_character(name: str) -> CharacterSheet | None:
    """A character sheet by its character's key or by the name a persona of it carries."""
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    name = name.strip()
    if not name:
        return None
    return (
        CharacterSheet.objects.filter(
            Q(character__db_key__iexact=name) | Q(personas__name__iexact=name)
        )
        .distinct()
        .first()
    )
