"""Placements: one opponent line's edits over its creature template (#4361).

A placement is a ``BeatOpponentLine`` or a ``MissionOptionOpponentLine``. It may change
the cause, the cause margin and the affiliation, raise, lower, remove or add drives
(``OpponentLineDrive``), and switch off inherited faction rules
(``OpponentLineFactionRuleSuppression``). Every pick comes from a catalog: cause kinds,
properties, organizations, and the rules the placement inherits (ADR-0110).

``placement_profile`` resolves what one opponent of the line will carry (from
``draft_from_line`` for saved edits, or an unsaved ``PlacementDraft`` for a preview);
``stamp_opponent`` writes that onto a spawned ``CombatOpponent``; ``save_placement`` is
the one writer the staff Placement page and the GM beat dialog share.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from world.combat.constants import CauseKind
from world.standoffs.constants import DriveStrength
from world.standoffs.services.profile import InheritedRule, inherited_rules

if TYPE_CHECKING:
    from world.combat.models import CombatOpponent, CreatureTemplate
    from world.mechanics.models import Property
    from world.missions.models import MissionOptionOpponentLine
    from world.societies.models import Organization
    from world.standoffs.models import FactionRule
    from world.stories.models import BeatOpponentLine

    OpponentLine = BeatOpponentLine | MissionOptionOpponentLine


class DriveEditState:
    """How a placement's drive compares with its template's."""

    SAME = "same"
    EDITED = "edited"
    ADDED = "added"
    REMOVED = "removed"


@dataclass(frozen=True)
class PlacementDrive:
    """One drive row of a placement: the template's strength beside the strength here."""

    property: Property
    property_id: int
    template_strength: int | None
    strength: int | None
    state: str

    @property
    def template_label(self) -> str:
        return DriveStrength(self.template_strength).label if self.template_strength else ""

    @property
    def label(self) -> str:
        return DriveStrength(self.strength).label if self.strength else ""


@dataclass(frozen=True)
class PlacementRule:
    """An inherited faction rule and whether this placement switches it off."""

    inherited: InheritedRule
    suppressed: bool


@dataclass(frozen=True)
class PlacementProfile:
    """What one opponent spawned from a placement will carry."""

    template: CreatureTemplate
    cause: str
    template_cause: str
    cause_margin_percent: int
    template_cause_margin_percent: int
    organization: Organization | None
    template_organization: Organization | None
    drives: list[PlacementDrive] = field(default_factory=list)
    rules: list[PlacementRule] = field(default_factory=list)

    @property
    def live_drives(self) -> list[PlacementDrive]:
        return [drive for drive in self.drives if drive.strength]

    @property
    def live_rules(self) -> list[InheritedRule]:
        return [entry.inherited for entry in self.rules if not entry.suppressed]

    @property
    def cause_edited(self) -> bool:
        return self.cause != self.template_cause

    @property
    def organization_edited(self) -> bool:
        return self.organization != self.template_organization

    def summary(self, count: int) -> str:
        """One plain line saying what the placement spawns."""
        drives = ", ".join(f"{d.property.name} ({d.label})" for d in self.live_drives)
        rules = len(self.live_rules)
        parts = [
            f"Spawns {count} {self.template.name}",
            f"cause {CauseKind(self.cause).label}, margin {self.cause_margin_percent}",
            f"drives {drives}" if drives else "no drives",
            f"{rules} faction rule{'s' if rules != 1 else ''}",
        ]
        if self.organization is not None:
            parts.append(f"affiliated with {self.organization.name}")
        return ". ".join([parts[0] + ": " + parts[1], *parts[2:]]) + "."


@dataclass(frozen=True)
class DriveEdit:
    """One requested drive change: a strength, or ``None`` to remove the template's drive."""

    property: Property
    strength: int | None


@dataclass(frozen=True)
class PlacementDraft:
    """A placement's edits, saved or not: what ``placement_profile`` resolves."""

    cause_override: str = ""
    cause_margin_override: int | None = None
    organization: Organization | None = None
    drive_edits: dict[int, int | None] = field(default_factory=dict)
    suppressed_ids: frozenset[int] = frozenset()


def draft_from_line(line: OpponentLine | None) -> PlacementDraft:
    """The saved edits of a line (an empty draft for no line)."""
    if line is None or line.pk is None:
        return PlacementDraft()
    return PlacementDraft(
        cause_override=line.cause_override,
        cause_margin_override=line.cause_margin_override,
        organization=line.organization,
        drive_edits={row.property_id: row.strength for row in line.drive_edits.all()},
        suppressed_ids=frozenset(
            line.faction_rule_suppressions.values_list("faction_rule_id", flat=True)
        ),
    )


def placement_profile(
    template: CreatureTemplate, draft: PlacementDraft | None = None
) -> PlacementProfile:
    """Resolve a placement's edits over its template (no draft: the template as it is)."""
    draft = draft or PlacementDraft()
    edits = draft.drive_edits
    suppressed = draft.suppressed_ids
    template_drives = {
        drive.property_id: drive for drive in template.drives.select_related("property")
    }
    drives: list[PlacementDrive] = []
    for property_id, drive in template_drives.items():
        if property_id in edits:
            strength = edits[property_id]
            state = (
                DriveEditState.REMOVED
                if not strength
                else DriveEditState.SAME
                if strength == drive.strength
                else DriveEditState.EDITED
            )
        else:
            strength, state = drive.strength, DriveEditState.SAME
        drives.append(PlacementDrive(drive.property, property_id, drive.strength, strength, state))
    added_ids = [pid for pid, strength in edits.items() if pid not in template_drives and strength]
    if added_ids:
        from world.mechanics.models import Property  # noqa: PLC0415

        drives.extend(
            PlacementDrive(prop, prop.pk, None, edits[prop.pk], DriveEditState.ADDED)
            for prop in Property.objects.filter(pk__in=added_ids)
        )
    drives.sort(key=lambda d: (-(d.strength or 0), d.property.name))

    effective_org = draft.organization or template.organization
    rules = [
        PlacementRule(entry, entry.rule.pk in suppressed)
        for entry in inherited_rules(template, effective_org)
    ]
    return PlacementProfile(
        template=template,
        cause=draft.cause_override or template.cause,
        template_cause=template.cause,
        cause_margin_percent=(
            draft.cause_margin_override
            if draft.cause_margin_override is not None
            else template.cause_margin_percent
        ),
        template_cause_margin_percent=template.cause_margin_percent,
        organization=effective_org,
        template_organization=template.organization,
        drives=drives,
        rules=rules,
    )


def stamp_opponent(opponent: CombatOpponent, profile: PlacementProfile) -> None:
    """Write a placement profile onto a freshly spawned opponent.

    The drives become ``ObjectProperty`` rows on the opponent's object (value = strength),
    so the encounter reads the snapshot and never the template again.
    """
    from world.mechanics.models import ObjectProperty  # noqa: PLC0415

    opponent.cause = profile.cause
    opponent.cause_margin_percent = profile.cause_margin_percent
    opponent.organization = profile.organization
    opponent.save(update_fields=["cause", "cause_margin_percent", "organization"])
    opponent.suppressed_faction_rules.set(
        [entry.inherited.rule.pk for entry in profile.rules if entry.suppressed]
    )
    if opponent.objectdb_id is None:
        return
    for drive in profile.live_drives:
        ObjectProperty.objects.update_or_create(
            object_id=opponent.objectdb_id,
            property_id=drive.property_id,
            defaults={"value": drive.strength},
        )


def placement_errors(
    template: CreatureTemplate,
    organization: Organization | None,
    drive_edits: list[DriveEdit],
    suppressed_rule_ids: list[int],
) -> dict[str, list[str]]:
    """What is wrong with a placement's edits, by field (empty when they are valid)."""
    errors: dict[str, list[str]] = {}
    for edit in drive_edits:
        if edit.strength is not None and edit.strength not in DriveStrength.values:
            errors.setdefault("drive_edits", []).append(f"{edit.property}: unknown strength.")
    seen = [edit.property.pk for edit in drive_edits]
    if len(seen) != len(set(seen)):
        errors.setdefault("drive_edits", []).append("Each drive may be edited once.")
    effective_org = organization or template.organization
    allowed = {entry.rule.pk for entry in inherited_rules(template, effective_org)}
    if any(pk not in allowed for pk in suppressed_rule_ids):
        errors["suppressed_faction_rules"] = [
            "Only a rule this placement inherits can be switched off."
        ]
    return errors


@transaction.atomic
def save_placement(  # noqa: PLR0913 - one placement's whole edit set
    line: OpponentLine,
    *,
    cause_override: str,
    cause_margin_override: int | None,
    organization: Organization | None,
    drive_edits: list[DriveEdit],
    suppressed_rule_ids: list[int],
) -> None:
    """Write one placement's edits: the line's own fields, its drive rows and suppressions.

    Raises ``ValidationError`` for a strength outside the catalog, a drive edited twice,
    or a suppression of a rule the placement does not inherit. A drive edit that matches
    the template's own strength is not stored.
    """
    from world.standoffs.models import (  # noqa: PLC0415
        OpponentLineDrive,
        OpponentLineFactionRuleSuppression,
    )

    template = line.creature_template
    errors = placement_errors(template, organization, drive_edits, suppressed_rule_ids)
    if errors:
        raise ValidationError(errors)
    line.cause_override = cause_override or ""
    line.cause_margin_override = cause_margin_override
    line.organization = organization
    line.save(update_fields=["cause_override", "cause_margin_override", "organization"])

    line_field = _line_field(line)
    template_strengths = {d.property_id: d.strength for d in template.drives.all()}
    OpponentLineDrive.objects.filter(**{line_field: line}).delete()
    OpponentLineDrive.objects.bulk_create(
        [
            OpponentLineDrive(**{line_field: line}, property=edit.property, strength=edit.strength)
            for edit in drive_edits
            if template_strengths.get(edit.property.pk) != edit.strength
            and not (edit.strength is None and edit.property.pk not in template_strengths)
        ]
    )
    OpponentLineFactionRuleSuppression.objects.filter(**{line_field: line}).delete()
    OpponentLineFactionRuleSuppression.objects.bulk_create(
        [
            OpponentLineFactionRuleSuppression(**{line_field: line}, faction_rule_id=pk)
            for pk in sorted(set(suppressed_rule_ids))
        ]
    )


def _line_field(line: OpponentLine) -> str:
    from world.stories.models import BeatOpponentLine  # noqa: PLC0415

    return "beat_line" if isinstance(line, BeatOpponentLine) else "mission_line"


@dataclass(frozen=True)
class ContextDrive:
    property: Property
    property_id: int
    strength: int
    strength_label: str


@dataclass(frozen=True)
class ContextRule:
    rule: FactionRule
    label: str
    source: str
    level: int


@dataclass(frozen=True)
class TemplateContext:
    """A template's own standoff values, beside which a placement editor shows its edits."""

    creature_template: int
    name: str
    cause: str
    cause_label: str
    cause_margin_percent: int
    organization: int | None
    organization_name: str
    drives: list[ContextDrive]
    inherited_rules: list[ContextRule]


def template_context(
    template: CreatureTemplate, organization: Organization | None = None
) -> TemplateContext:
    """The template's cause, margin, affiliation and drives, and the rules a placement
    affiliated with ``organization`` (or the template's own affiliation) inherits."""
    from world.standoffs.services.gm_view import faction_rule_label  # noqa: PLC0415

    effective_org = organization or template.organization
    return TemplateContext(
        creature_template=template.pk,
        name=template.name,
        cause=template.cause,
        cause_label=CauseKind(template.cause).label,
        cause_margin_percent=template.cause_margin_percent,
        organization=template.organization_id,
        organization_name=template.organization.name if template.organization else "",
        drives=[
            ContextDrive(
                drive.property,
                drive.property_id,
                drive.strength,
                DriveStrength(drive.strength).label,
            )
            for drive in template.drives.select_related("property")
        ],
        inherited_rules=[
            ContextRule(entry.rule, faction_rule_label(entry.rule), entry.source, entry.level)
            for entry in inherited_rules(template, effective_org)
        ],
    )
