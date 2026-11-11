"""Pure reads for the Power Builder (item 8 of #5066).

One page is about one ``Application``: every source of its capability side by side, with
its strength at a reference character, what each use costs, and whether it does the
application. Every list is read with one query per kind of row, never per row; M2M
memberships (properties, a technique's paths) are read through their through tables with
``values_list`` so no prefetch cache lands on the identity-mapped rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Model
from django.urls import reverse

from web.admin.authoring.links import admin_change_url
from web.admin.power_builder.constants import SourceKind
from world.areas.positioning.constants import CreatureTraversal
from world.combat.models import MovementConfig
from world.combat.services.movement_use import scaled_strength
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionStage,
    ConditionTemplate,
)
from world.distinctions.models import DistinctionEffect
from world.magic.constants import GiftKind
from world.magic.models import (
    EffectType,
    Gift,
    GiftSubstance,
    PathGiftGrant,
    Technique,
    TechniqueCapabilityGrant,
)
from world.magic.services.capability_curve import get_capability_power_config
from world.mechanics.models import Application, Property, TraitCapabilityDerivation

#: How each way of moving reads after "by".
_GERUNDS: dict[str, str] = {
    CreatureTraversal.WALKS: "walking",
    CreatureTraversal.CLIMBS: "climbing",
    CreatureTraversal.LEAPS: "leaping",
    CreatureTraversal.FLIES: "flying",
    CreatureTraversal.BLINKS: "blinking",
    CreatureTraversal.PHASES: "phasing",
}

#: The success level one better than a bare success.
_ONE_LEVEL_BETTER = 2


@dataclass(frozen=True)
class Reference:
    """The reference character every strength is read at (the "Compare at" controls)."""

    power: int
    trait: int
    rank: int
    severity: int


@dataclass
class TechniqueRow:
    """One technique: in "Techniques that do it" or in one of the "One step away" lists."""

    technique: Technique
    gift_label: str
    path_label: str
    property_ids: set[int]
    candidates: list[Property]
    grant: TechniqueCapabilityGrant | None
    strength: int | None = None
    better: int | None = None
    edit_url: str = ""
    form: object = None

    @property
    def cost(self) -> str:
        return f"a cast: {self.technique.anima_cost} anima, its own roll"


@dataclass
class OtherRow:
    """One source that is not a technique: trained ability, a condition, a distinction."""

    kind: str
    name: str
    row: Model
    property_names: list[str]
    property_ids: set[int]
    strength: int
    does: bool
    reason: str
    link_url: str
    link_label: str
    #: The condition template whose properties this row edits, when it is the first
    #: row of its condition (a condition with two effects edits them once).
    template: ConditionTemplate | None = None
    #: The template's own property ids and the checkboxes it shows (its own, plus the
    #: application's property), set only alongside ``template``.
    template_property_ids: set[int] = field(default_factory=set)
    template_candidates: list[Property] = field(default_factory=list)
    form: object = None


@dataclass
class RailApplication:
    application: Application
    url: str
    summary: str
    count: int


@dataclass
class Band:
    label: str
    reach: str


@dataclass
class PowerPage:
    """Everything the page reads about one saved application."""

    capability: CapabilityType
    required: Property | None
    doing: list[TechniqueRow] = field(default_factory=list)
    lacks_property: list[TechniqueRow] = field(default_factory=list)
    lacks_grant: list[TechniqueRow] = field(default_factory=list)
    others: list[OtherRow] = field(default_factory=list)
    rail: list[RailApplication] = field(default_factory=list)
    default_effect_type: EffectType | None = None
    fatigue_cost: int = 0

    @property
    def technique_rows(self) -> list[TechniqueRow]:
        return [*self.doing, *self.lacks_property, *self.lacks_grant]

    @property
    def others_doing(self) -> int:
        return sum(1 for row in self.others if row.does)

    def kept_rows(self) -> list[Model]:
        """Every identity-mapped row the save can write onto, for a ``CacheGuard``."""
        rows: list[Model] = []
        for row in self.technique_rows:
            rows.append(row.technique)
            if row.grant is not None:
                rows.append(row.grant)
        for other in self.others:
            rows.append(other.row)
            if other.template is not None:
                rows.append(other.template)
        return rows


def movement_config() -> MovementConfig:
    """The movement settings row, or an unsaved one with the field defaults."""
    return MovementConfig.objects.cached_singleton() or MovementConfig()


def gift_label(gift: Gift) -> str:
    return f"{gift.name} (minor gift)" if gift.kind == GiftKind.MINOR else gift.name


def way_phrase(app: Application) -> str:
    return _GERUNDS.get(app.way_of_moving, app.get_way_of_moving_display().lower())


def plain_words(app: Application) -> str:
    """The application in one plain sentence (the page reads it under the fields)."""
    if app.capability_id is None:
        return "Pick a capability."
    source = f"a source of {app.capability.name}"
    if app.required_effect_property_id:
        source += f" carrying {app.required_effect_property.name}"
    if app.dodges:
        landing = f", landing by {way_phrase(app)}" if app.way_of_moving else ""
        does = f"dodges attacks automatically{landing}"
        cost = (
            " Each dodge with a technique is a cast of it; with anything else it costs "
            "physical fatigue."
        )
    elif app.way_of_moving:
        does = f"can move by {way_phrase(app)} on her turn"
        cost = (
            " Each move with a technique is a cast of it; with anything else it costs "
            "physical fatigue in a fight."
        )
    else:
        does = "can use this"
        cost = ""
    where = (
        f", where the target carries {app.target_property.name}" if app.target_property_id else ""
    )
    return f"In words: {source} {does}{where}.{cost}"


def application_summary(app: Application) -> str:
    """The rail's short reading: way of moving, where, needed property."""
    if app.dodges:
        parts = [f"dodges, landing by {way_phrase(app)}" if app.way_of_moving else "dodges"]
    elif app.way_of_moving:
        parts = [f"{app.get_way_of_moving_display().lower()} on her turn"]
    else:
        parts = ["not about moving"]
    if app.target_property_id:
        parts.append(f"where: {app.target_property.name}")
    if app.required_effect_property_id:
        parts.append(f"needs {app.required_effect_property.name}")
    else:
        parts.append("no property")
    return ", ".join(parts)


def bands() -> list[Band]:
    """How far a use reaches, from the movement settings' three thresholds."""
    row = movement_config()
    near, two, anywhere = row.reach_neighbour_at, row.reach_two_places_at, row.reach_anywhere_at
    return [
        Band(f"Strength below {near}", "stays in place"),
        Band(f"{near} to {two - 1}", "a neighbouring place"),
        Band(f"{two} to {anywhere - 1}", "two places away"),
        Band(f"{anywhere} or more", "anywhere in the room"),
    ]


def movement_settings_url() -> str:
    row = MovementConfig.objects.cached_singleton()
    if row is not None:
        return reverse("admin:arxii_movementconfig_change", args=[row.pk])
    return reverse("admin:arxii_movementconfig_add")


def _m2m_pairs(model: type[Model], name: str, ids: set[int]) -> list[tuple[int, int]]:
    """(owner pk, related pk) for every link of ``model.<name>`` from ``ids``: one query."""
    if not ids:
        return []
    m2m = model._meta.get_field(name)  # noqa: SLF001
    through = m2m.remote_field.through
    owner = f"{m2m.m2m_field_name()}_id"
    other = f"{m2m.m2m_reverse_field_name()}_id"
    return list(through.objects.filter(**{f"{owner}__in": ids}).values_list(owner, other))


def _group(pairs: list[tuple[int, int]]) -> dict[int, set[int]]:
    grouped: dict[int, set[int]] = {}
    for owner, other in pairs:
        grouped.setdefault(owner, set()).add(other)
    return grouped


def _paths_by_technique(technique_ids: set[int]) -> dict[int, list[str]]:
    """The paths whose gift grant lists each technique, by name: one query."""
    if not technique_ids:
        return {}
    m2m = PathGiftGrant._meta.get_field("starter_techniques")  # noqa: SLF001
    through = m2m.remote_field.through
    technique = f"{m2m.m2m_reverse_field_name()}_id"
    path_name = f"{m2m.m2m_field_name()}__path__name"
    paths: dict[int, list[str]] = {}
    rows = through.objects.filter(**{f"{technique}__in": technique_ids}).values_list(
        technique, path_name
    )
    for technique_id, name in rows:
        paths.setdefault(technique_id, []).append(name)
    return {pk: sorted(names) for pk, names in paths.items()}


def _carries(required: Property | None, property_ids: set[int]) -> bool:
    return required is None or required.pk in property_ids


def build_page(app: Application, ref: Reference) -> PowerPage:
    """Every source of ``app``'s capability, sorted into the page's lists."""
    page = PowerPage(
        capability=app.capability,
        required=app.required_effect_property,
        fatigue_cost=movement_config().dodge_fatigue_cost,
    )
    _add_techniques(page, ref)
    _add_others(page, ref)
    page.default_effect_type = (
        page.doing[0].technique.effect_type
        if page.doing
        else EffectType.objects.order_by("name").first()
    )
    page.rail = _rail(app, page)
    return page


def _candidates(
    ids: set[int], names: dict[int, Property], required: Property | None
) -> list[Property]:
    """A row's property ticks: what it carries, plus the application's property."""
    chosen = {names[pk] for pk in ids if pk in names}
    if required is not None:
        chosen.add(required)
    return sorted(chosen, key=lambda prop: prop.name)


def _technique_row(  # noqa: PLR0913 - one row's parts, named at the call
    technique: Technique,
    grant: TechniqueCapabilityGrant | None,
    ids: set[int],
    paths: list[str],
    names: dict[int, Property],
    required: Property | None,
) -> TechniqueRow:
    return TechniqueRow(
        technique=technique,
        gift_label=gift_label(technique.gift),
        path_label=", ".join(paths) or "no path",
        property_ids=ids,
        candidates=_candidates(ids, names, required),
        grant=grant,
        edit_url=reverse("admin:arxii_technique_change", args=[technique.pk]),
    )


def _add_techniques(page: PowerPage, ref: Reference) -> None:
    """The techniques that do it, and the two kinds that are one step away."""
    capability, required = page.capability, page.required
    grants = list(
        TechniqueCapabilityGrant.objects.filter(capability_id=capability.pk)
        .select_related("technique__gift", "technique__effect_type")
        .order_by("technique__gift__name", "technique__name")
    )
    not_granting: list[Technique] = []
    if required is not None:
        not_granting = list(
            Technique.objects.filter(properties=required)
            .exclude(capability_grants__capability_id=capability.pk)
            .select_related("gift")
            .order_by("gift__name", "name")
        )
    technique_ids = {g.technique_id for g in grants} | {t.pk for t in not_granting}
    properties_of = _group(_m2m_pairs(Technique, "properties", technique_ids))
    paths_of = _paths_by_technique(technique_ids)
    names = Property.objects.in_bulk({pk for ids in properties_of.values() for pk in ids})
    config = get_capability_power_config()
    for grant in grants:
        technique = grant.technique
        ids = properties_of.get(technique.pk, set())
        row = _technique_row(technique, grant, ids, paths_of.get(technique.pk, []), names, required)
        row.strength = grant.calculate_value(effective_power=ref.power, config=config)
        row.better = scaled_strength(row.strength, _ONE_LEVEL_BETTER)
        (page.doing if _carries(required, ids) else page.lacks_property).append(row)
    for technique in not_granting:
        ids = properties_of.get(technique.pk, set())
        page.lacks_grant.append(
            _technique_row(technique, None, ids, paths_of.get(technique.pk, []), names, required)
        )


def _add_others(page: PowerPage, ref: Reference) -> None:
    """Trained ability, conditions and distinctions that give the capability."""
    capability, required = page.capability, page.required
    derivations = list(
        TraitCapabilityDerivation.objects.filter(capability_id=capability.pk)
        .select_related("trait")
        .order_by("trait__name")
    )
    effects = list(
        ConditionCapabilityEffect.objects.filter(capability_id=capability.pk, value__gt=0)
        .select_related("condition", "stage__condition")
        .order_by("pk")
    )
    distinction_effects = list(
        DistinctionEffect.objects.filter(target__target_capability_id=capability.pk)
        .select_related("distinction")
        .order_by("distinction__name", "pk")
    )
    template_props = _group(
        _m2m_pairs(
            ConditionTemplate, "properties", {e.get_condition_template().pk for e in effects}
        )
    )
    stage_props = _group(
        _m2m_pairs(ConditionStage, "properties", {e.stage_id for e in effects if e.stage_id})
    )
    names = Property.objects.in_bulk(
        {pk for ids in (*template_props.values(), *stage_props.values()) for pk in ids}
    )
    for derivation in derivations:
        page.others.append(
            _other(
                SourceKind.TRAINED,
                derivation.trait.name,
                derivation,
                set(),
                names,
                derivation.calculate_value(ref.trait),
                required,
                admin_change_url("TraitCapabilityDerivation", derivation.pk) or "",
                "edit all",
            )
        )
    seen_templates: set[int] = set()
    for effect in effects:
        template = effect.get_condition_template()
        ids = template_props.get(template.pk, set()) | stage_props.get(effect.stage_id, set())
        strength = effect.value * ref.severity if effect.scales_with_severity else effect.value
        name = template.name
        if effect.stage_id is not None:
            name = f"{template.name} ({effect.stage.name})"
        row = _other(
            SourceKind.CONDITION,
            name,
            effect,
            ids,
            names,
            strength,
            required,
            reverse("admin:arxii_conditiontemplate_change", args=[template.pk]),
            "edit all",
        )
        if template.pk not in seen_templates:
            seen_templates.add(template.pk)
            row.template = template
            row.template_property_ids = template_props.get(template.pk, set())
            row.template_candidates = _candidates(row.template_property_ids, names, required)
        page.others.append(row)
    for effect in distinction_effects:
        page.others.append(
            _other(
                SourceKind.DISTINCTION,
                effect.distinction.name,
                effect,
                set(),
                names,
                effect.get_value_at_rank(ref.rank),
                required,
                reverse("admin_distinction_builder", args=[effect.distinction_id]),
                "Distinction Builder",
            )
        )


def _other(  # noqa: PLR0913 - one row's fields, named at the call
    kind: str,
    name: str,
    row: Model,
    ids: set[int],
    names: dict[int, Property],
    strength: int,
    required: Property | None,
    link_url: str,
    link_label: str,
) -> OtherRow:
    if not _carries(required, ids):
        does, reason = False, "no property"
    elif strength <= 0:
        does, reason = False, "no strength at this reference"
    else:
        does, reason = True, ""
    return OtherRow(
        kind=kind,
        name=name,
        row=row,
        property_names=sorted(names[pk].name for pk in ids if pk in names),
        property_ids=ids,
        strength=strength,
        does=does,
        reason=reason,
        link_url=link_url,
        link_label=link_label,
    )


def _rail(app: Application, page: PowerPage) -> list[RailApplication]:
    """The capability's other applications, each with how many sources do it."""
    source_sets = [row.property_ids for row in (*page.doing, *page.lacks_property)]
    source_sets += [row.property_ids for row in page.others]
    others = (
        Application.objects.filter(capability_id=app.capability_id)
        .exclude(pk=app.pk)
        .select_related("required_effect_property", "target_property", "capability")
        .order_by("name")
    )
    return [
        RailApplication(
            application=other,
            url=reverse("admin_power_builder", args=[other.pk]),
            summary=application_summary(other),
            count=sum(
                1
                for ids in source_sets
                if not other.required_effect_property_id or other.required_effect_property_id in ids
            ),
        )
        for other in others
    ]


def substance_by_gift(gifts: list[Gift]) -> dict[int, Property]:
    """Each gift's substance property (its own, else its nearest ancestor's): one query."""
    own = {
        row.gift_id: row.property
        for row in GiftSubstance.objects.filter(property__isnull=False).select_related("property")
    }
    by_pk = {gift.pk: gift for gift in gifts}
    found: dict[int, Property] = {}
    for gift in gifts:
        seen: set[int] = set()
        current: Gift | None = gift
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            if current.pk in own:
                found[gift.pk] = own[current.pk]
                break
            current = by_pk.get(current.parent_id) if current.parent_id else None
    return found
