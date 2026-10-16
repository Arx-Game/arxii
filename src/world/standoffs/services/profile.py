"""A group's standoff profile: cause, drives and the faction rules it carries (#4361).

Everything here reads the snapshot stamped on the group's opponents at spawn
(``services.placement.stamp_opponent``): ``CombatOpponent.cause``,
``cause_margin_percent``, ``organization`` and ``suppressed_faction_rules``, and the
drives as ``ObjectProperty`` rows on each opponent's object. A live encounter never reads
its creature template's standoff fields, so a placement's edits apply and a later edit to
the template leaves running encounters alone.

A group is one creature template in one encounter. Its profile is its first-spawned
member's (lowest pk): two placements of the same template in one encounter with different
edits form one group that takes the first placement's profile.

Faction rules are inherited downward and carry a precedence level, most specific first:
the template's own rules (level 0), then the affiliation organization's, then each
``parent_org`` above it, then the society of each of those organizations. A placement may
switch any inherited rule off; the switch is stamped on the opponent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.combat.constants import CauseKind
from world.standoffs.constants import DriveStrength

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.combat.models import CombatOpponent, CreatureTemplate
    from world.mechanics.models import Property
    from world.societies.models import Organization, Society
    from world.standoffs.models import FactionRule, StandoffGroup

#: Precedence level of a template's own rules. Organization levels count up from here.
TEMPLATE_LEVEL = 0
#: A ``parent_org`` chain longer than this is treated as a cycle and cut.
MAX_ORG_DEPTH = 20


@dataclass(frozen=True)
class GroupDrive:
    """One drive a group carries: a property and how hard it pulls (1 to 3)."""

    property: Property
    property_id: int
    strength: int

    @property
    def strength_label(self) -> str:
        return DriveStrength(self.strength).label


@dataclass(frozen=True)
class InheritedRule:
    """A faction rule that applies to a group, where it came from and how specific it is.

    ``level`` is 0 for the template's own rules and grows with distance; a smaller level
    wins when two matched rules shift the same thing. ``source`` names the owner.
    """

    rule: FactionRule
    level: int
    source: str


def org_chain(organization: Organization | None) -> list[Organization]:
    """The organization and every ``parent_org`` above it, nearest first."""
    chain: list[Organization] = []
    seen: set[int] = set()
    current = organization
    while current is not None and current.pk not in seen and len(chain) < MAX_ORG_DEPTH:
        chain.append(current)
        seen.add(current.pk)
        current = current.parent_org
    return chain


def _societies(chain: list[Organization]) -> list[Society]:
    societies: list[Society] = []
    for org in chain:
        if org.society is not None and org.society not in societies:
            societies.append(org.society)
    return societies


def affiliation_rules(
    organization: Organization | None, first_level: int = TEMPLATE_LEVEL + 1
) -> list[InheritedRule]:
    """The rules an affiliation brings: the organization's, each parent's, each society's.

    Most specific first; the organization's own rules sit at ``first_level`` and each
    step outward adds one.
    """
    from world.standoffs.models import FactionRule  # noqa: PLC0415

    chain = org_chain(organization)
    if not chain:
        return []
    rules: list[InheritedRule] = []
    by_org: dict[int, list[FactionRule]] = {}
    for rule in FactionRule.objects.filter(
        organization__in=[org.pk for org in chain]
    ).select_related("deed_archetype", "drive"):
        by_org.setdefault(rule.organization_id, []).append(rule)
    for depth, org in enumerate(chain):
        rules.extend(
            InheritedRule(rule, first_level + depth, org.name) for rule in by_org.get(org.pk, [])
        )
    societies = _societies(chain)
    by_society: dict[int, list[FactionRule]] = {}
    for rule in FactionRule.objects.filter(
        society__in=[society.pk for society in societies]
    ).select_related("deed_archetype", "drive"):
        by_society.setdefault(rule.society_id, []).append(rule)
    base = first_level + len(chain)
    for offset, society in enumerate(societies):
        rules.extend(
            InheritedRule(rule, base + offset, society.name)
            for rule in by_society.get(society.pk, [])
        )
    return rules


def society_rules(society: Society) -> list[InheritedRule]:
    """A society's own rules, as the Faction Rules page lists them (level 0)."""
    from world.standoffs.models import FactionRule  # noqa: PLC0415

    return [
        InheritedRule(rule, TEMPLATE_LEVEL, society.name)
        for rule in FactionRule.objects.filter(society=society).select_related(
            "deed_archetype", "drive"
        )
    ]


def inherited_rules(
    template: CreatureTemplate,
    organization: Organization | None,
    suppressed_ids: Iterable[int] = (),
) -> list[InheritedRule]:
    """Every faction rule an opponent of ``template`` affiliated with ``organization`` carries.

    Most specific first: the template's rules, the organization's, each parent's, then
    each society's. Rules whose pk is in ``suppressed_ids`` are left out.
    """
    from world.standoffs.models import FactionRule  # noqa: PLC0415

    suppressed = set(suppressed_ids)
    rules = [
        InheritedRule(rule, TEMPLATE_LEVEL, template.name)
        for rule in FactionRule.objects.filter(creature_template=template).select_related(
            "deed_archetype", "drive"
        )
    ]
    rules.extend(affiliation_rules(organization))
    return [entry for entry in rules if entry.rule.pk not in suppressed]


def representative(group: StandoffGroup) -> CombatOpponent | None:
    """The group's first-spawned member, whose stamped profile the group uses."""
    return (
        group.encounter.opponents.filter(creature_template_id=group.creature_template_id)
        .select_related("organization")
        .order_by("pk")
        .first()
    )


def group_cause(group: StandoffGroup) -> tuple[str, int]:
    """The group's cause and cause margin percent, as stamped at spawn."""
    member = representative(group)
    if member is None:
        return CauseKind.NONE, 0
    return member.cause, member.cause_margin_percent


def opponent_drives(opponent: CombatOpponent | None) -> list[GroupDrive]:
    """The drives stamped on an opponent's object, strongest first.

    Only rows with no granting condition or challenge count: a property a condition or
    challenge put on the body is not a drive the creature came with.
    """
    from world.mechanics.models import ObjectProperty  # noqa: PLC0415

    if opponent is None or opponent.objectdb_id is None:
        return []
    rows = ObjectProperty.objects.filter(
        object_id=opponent.objectdb_id,
        source_condition__isnull=True,
        source_challenge__isnull=True,
    ).select_related("property")
    drives = [
        GroupDrive(
            property=row.property,
            property_id=row.property_id,
            strength=max(DriveStrength.MINOR, min(DriveStrength.DEFINING, row.value)),
        )
        for row in rows
    ]
    return sorted(drives, key=lambda drive: (-drive.strength, drive.property_id))


def group_drives(group: StandoffGroup) -> list[GroupDrive]:
    """The group's drives, strongest first (see ``opponent_drives``)."""
    return opponent_drives(representative(group))


def opponent_rules(opponent: CombatOpponent | None) -> list[InheritedRule]:
    """The faction rules an opponent carries: its template's and its affiliation's."""
    if opponent is None or opponent.creature_template is None:
        return []
    suppressed = opponent.suppressed_faction_rules.values_list("pk", flat=True)
    return inherited_rules(opponent.creature_template, opponent.organization, suppressed)


def group_rules(group: StandoffGroup) -> list[InheritedRule]:
    """The faction rules the group carries, most specific first."""
    return opponent_rules(representative(group))


def group_organization(group: StandoffGroup) -> Organization | None:
    """The group's stamped affiliation."""
    member = representative(group)
    return member.organization if member is not None else None
