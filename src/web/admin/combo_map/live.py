"""The combo map's reads (#4891, slice 3 of #4843): what sets and reads a property or condition.

Pure reads, one query per source in ``sources``, never one per row. A property is set by
whatever lands a condition carrying it (on the template, or on one of its stages); it is read
by any row that checks for it. A condition is set by whatever lands it, and read both by rows
that name it and by readers of every property it carries.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import Model, Q
from django.urls import reverse

from web.admin.authoring.links import admin_change_url
from web.admin.combo_map.sources import (
    READER_SOURCES,
    SETTER_SOURCES,
    ReaderSource,
    Reads,
    RowText,
    SetterSource,
)
from world.conditions.models import ConditionStage, ConditionTemplate
from world.mechanics.models import Property

#: Page kinds, shown beside the name and used to pick the page's copy.
PROPERTY_KIND = "property"
CONDITION_KIND = "condition"


@dataclass(frozen=True)
class SourceLink:
    """A row's label and its admin change page, or no link when its model has no admin."""

    label: str
    url: str | None


@dataclass(frozen=True)
class CarrierRow:
    """One condition carrying a property, or one property a condition carries.

    ``stages`` holds the stage numbers when only those stages carry it; empty when the
    template itself does.
    """

    pk: int
    name: str
    stages: tuple[int, ...] = ()

    @property
    def stage_note(self) -> str:
        if not self.stages:
            return ""
        noun = "stage" if len(self.stages) == 1 else "stages"
        return f"({noun} {', '.join(str(n) for n in self.stages)} only)"


@dataclass(frozen=True)
class SetterRow:
    source: SourceLink
    kind: str
    condition: str
    lands: str


@dataclass(frozen=True)
class ReaderRow:
    source: SourceLink
    kind: str
    does: str


@dataclass(frozen=True)
class SetterLine:
    """One line of the Set by table: a setter, or a carrying condition nothing sets."""

    setter: SetterRow | None = None
    unset_condition: str = ""


@dataclass(frozen=True)
class ReaderGroup:
    """The readers of one subject. ``heading`` is blank on a property's page (one group)."""

    heading: str
    readers: list[ReaderRow] = field(default_factory=list)


@dataclass(frozen=True)
class ComboMap:
    name: str
    kind: str
    edit_url: str
    carriers: list[CarrierRow]
    set_by: list[SetterLine]
    reader_groups: list[ReaderGroup]

    @property
    def set_by_nothing(self) -> bool:
        return not any(line.setter for line in self.set_by)

    @property
    def read_by_nothing(self) -> bool:
        return not any(group.readers for group in self.reader_groups)


def _resolve(row: Model, path: str) -> Model:
    obj = row
    for part in path.split(".") if path else ():
        obj = getattr(obj, part)
    return obj


def _link(row: Model, owner: str, label: RowText | None) -> SourceLink:
    obj = _resolve(row, owner)
    text = label(row) if label is not None else str(obj)
    return SourceLink(label=text, url=admin_change_url(f"arxii.{type(obj).__name__}", obj.pk))


def conditions_carrying(prop: Property) -> list[CarrierRow]:
    """Every condition carrying ``prop``: on the template, or only on some of its stages."""
    whole = {t.pk: t for t in ConditionTemplate.objects.filter(properties=prop)}
    staged: dict[int, list[ConditionStage]] = defaultdict(list)
    for stage in ConditionStage.objects.filter(properties=prop).select_related("condition"):
        if stage.condition_id not in whole:
            staged[stage.condition_id].append(stage)
    rows = [CarrierRow(pk=t.pk, name=t.name) for t in whole.values()]
    for stages in staged.values():
        template = stages[0].condition
        rows.append(
            CarrierRow(
                pk=template.pk,
                name=template.name,
                stages=tuple(sorted(s.stage_order for s in stages)),
            )
        )
    return sorted(rows, key=lambda row: row.name)


def properties_carried(template: ConditionTemplate) -> list[CarrierRow]:
    """Every property ``template`` carries: on itself, or only on some of its stages."""
    whole = {p.pk: p for p in template.properties.all()}
    staged: dict[int, tuple[Property, list[int]]] = {}
    links = ConditionStage.properties.through.objects.filter(conditionstage__condition=template)
    for link in links.select_related("property", "conditionstage"):
        prop = link.property
        if prop.pk not in whole:
            staged.setdefault(prop.pk, (prop, []))[1].append(link.conditionstage.stage_order)
    rows = [CarrierRow(pk=p.pk, name=p.name) for p in whole.values()]
    rows.extend(
        CarrierRow(pk=prop.pk, name=prop.name, stages=tuple(sorted(orders)))
        for prop, orders in staged.values()
    )
    return sorted(rows, key=lambda row: row.name)


def _setter_rows(source: SetterSource, template_ids: set[int]) -> list[SetterRow]:
    queryset = source.model.objects.filter(**{f"{source.field}__in": template_ids})
    if source.narrow is not None:
        queryset = queryset.filter(source.narrow)
    rows: list[SetterRow] = []
    for row in queryset.select_related(source.field, *source.related):
        condition = getattr(row, source.field)
        rows.append(
            SetterRow(
                source=_link(row, source.owner, source.label),
                kind=source.kind,
                condition=condition.name,
                lands=f"{condition.name} {source.where(row)}",
            )
        )
    return rows


def setters_for_conditions(templates: Iterable[ConditionTemplate]) -> list[SetterRow]:
    """Every authored row that lands one of ``templates``, ordered by condition then source."""
    template_ids = {t.pk for t in templates}
    if not template_ids:
        return []
    rows = [row for source in SETTER_SOURCES for row in _setter_rows(source, template_ids)]
    return sorted(rows, key=lambda r: (r.condition, r.kind, r.source.label))


def _reader_rows(source: ReaderSource, lookup: Q) -> list[ReaderRow]:
    queryset = source.model.objects.filter(lookup).select_related(source.field, *source.related)
    return [
        ReaderRow(
            source=_link(row, source.owner, source.label),
            kind=source.kind,
            does=source.does(row),
        )
        for row in queryset
    ]


def _sorted(rows: list[ReaderRow]) -> list[ReaderRow]:
    return sorted(rows, key=lambda r: (r.kind, r.source.label))


def readers_for_properties(props: Iterable[Property]) -> dict[int, list[ReaderRow]]:
    """Every reader of each of ``props``, keyed by property pk."""
    prop_ids = {p.pk for p in props}
    by_property: dict[int, list[ReaderRow]] = {pk: [] for pk in prop_ids}
    if not prop_ids:
        return by_property
    for source in READER_SOURCES:
        if source.reads != Reads.PROPERTY:
            continue
        queryset = source.model.objects.filter(**{f"{source.field}__in": prop_ids})
        for row in queryset.select_related(source.field, *source.related):
            by_property[getattr(row, f"{source.field}_id")].append(
                ReaderRow(
                    source=_link(row, source.owner, source.label),
                    kind=source.kind,
                    does=source.does(row),
                )
            )
    return {pk: _sorted(rows) for pk, rows in by_property.items()}


def readers_for_property(prop: Property) -> list[ReaderRow]:
    return readers_for_properties([prop])[prop.pk]


def readers_for_condition(template: ConditionTemplate) -> list[ReaderRow]:
    """Every reader naming ``template`` itself, or one of its stages."""
    rows: list[ReaderRow] = []
    for source in READER_SOURCES:
        if source.reads == Reads.CONDITION:
            rows.extend(_reader_rows(source, Q(**{source.field: template})))
        elif source.reads == Reads.STAGE:
            rows.extend(_reader_rows(source, Q(**{f"{source.field}__condition": template})))
    return _sorted(rows)


def _set_by(templates: list[ConditionTemplate]) -> list[SetterLine]:
    setters = setters_for_conditions(templates)
    set_names = {row.condition for row in setters}
    lines = [SetterLine(setter=row) for row in setters]
    lines.extend(
        SetterLine(unset_condition=t.name)
        for t in sorted(templates, key=lambda t: t.name)
        if t.name not in set_names
    )
    return lines


def property_map(pk: int) -> ComboMap | None:
    """The combo map for one property, or ``None`` when there is no such property."""
    prop = Property.objects.filter(pk=pk).first()
    if prop is None:
        return None
    carriers = conditions_carrying(prop)
    templates = list(
        ConditionTemplate.objects.filter(Q(properties=prop) | Q(stages__properties=prop)).distinct()
    )
    return ComboMap(
        name=prop.name,
        kind=PROPERTY_KIND,
        edit_url=reverse("admin:arxii_property_change", args=[prop.pk]),
        carriers=carriers,
        set_by=_set_by(templates),
        reader_groups=[ReaderGroup(heading="", readers=readers_for_property(prop))],
    )


def condition_map(pk: int) -> ComboMap | None:
    """The combo map for one condition, or ``None`` when there is no such condition."""
    template = ConditionTemplate.objects.filter(pk=pk).first()
    if template is None:
        return None
    carried = properties_carried(template)
    props = list(
        Property.objects.filter(
            Q(condition_templates=template) | Q(condition_stages_carrying__condition=template)
        )
        .distinct()
        .order_by("name")
    )
    by_property = readers_for_properties(props)
    groups = [ReaderGroup(heading=template.name, readers=readers_for_condition(template))]
    groups.extend(ReaderGroup(heading=p.name, readers=by_property[p.pk]) for p in props)
    return ComboMap(
        name=template.name,
        kind=CONDITION_KIND,
        edit_url=reverse("admin:arxii_conditiontemplate_change", args=[template.pk]),
        carriers=carried,
        set_by=_set_by([template]),
        reader_groups=groups,
    )
