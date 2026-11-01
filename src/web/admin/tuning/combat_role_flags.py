"""Missing combat content flags (#4906, slice 4 of #4843): gaps in a vow's combat kit.

Five Required content probes, each naming the rows it flags and the page that fixes each
one (``FlaggedRow``). They are tuning flags: the game runs with every one of them open,
nothing is blocked, and no save refuses a row for them. The two condition flags read the
combo map's own lists (``web.admin.combo_map.live``), so the flags and the map cannot
disagree about what sets or reads a condition.

Every probe runs a fixed number of queries however many vows, picks, holders or
conditions there are.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.db.models import Exists, OuterRef
from django.urls import reverse

from web.admin.tuning.required_content import (
    ContentDependency,
    CustomProbe,
    DependencyTier,
    FlaggedRow,
    ProbeResult,
)

if TYPE_CHECKING:
    from django.db.models import Model

    from world.conditions.models import ConditionTemplate
    from world.covenants.models import CharacterCovenantRole


def _flags(rows: list[FlaggedRow]) -> ProbeResult:
    """A probe result naming ``rows``: present when there are none."""
    if not rows:
        return ProbeResult(present=True)
    return ProbeResult(present=False, missing=tuple(row.text for row in rows), flagged=tuple(rows))


def _vow_page(role_id: int) -> str:
    return reverse("admin_vow_builder", args=[role_id])


def _condition_map(template_id: int) -> str:
    return reverse("admin_combo_map_condition", args=[template_id])


def _probe_vow_no_picks() -> ProbeResult:
    """A vow with no focus pick to choose: none of its own, and none on its anchor.

    A sub-role holder chooses from the anchor vow's catalog as well as the sub-role's
    own (``focus_picks._choosable_role_ids``), so a sub-role whose anchor has picks is
    not flagged. Two queries.
    """
    from world.covenants.models import CovenantRole, VowFocusPick  # noqa: PLC0415

    with_picks = set(VowFocusPick.objects.values_list("covenant_role_id", flat=True))
    rows = [
        FlaggedRow(text=role.name, url=_vow_page(role.pk))
        for role in CovenantRole.objects.order_by("name")
        if role.pk not in with_picks and role.parent_role_id not in with_picks
    ]
    return _flags(rows)


def _probe_holder_over_budget() -> ProbeResult:
    """A live primary membership whose chosen picks at one level cost more than the budget.

    The price is ``pick_price`` and the budget ``focus_pick_budget()``, the same numbers
    ``validate_character_focus_pick`` refuses a save with; a row gets past that check by
    a later price or budget change. A secondary vow gets no picks and a left membership
    counts for nothing, so neither is read. Two queries: the choices, and the limits of
    every pick they name, priced through ``price_for`` (the formula ``pick_price`` runs).
    """
    from web.admin.vow_builder.live import focus_pick_budget  # noqa: PLC0415
    from world.covenants.focus_picks import price_for  # noqa: PLC0415
    from world.covenants.models import CharacterVowFocusPick, VowFocusPickLimit  # noqa: PLC0415

    budget = focus_pick_budget()
    choices = list(
        CharacterVowFocusPick.objects.filter(
            character_role__left_at__isnull=True, character_role__is_secondary=False
        ).select_related(
            "character_role__character_sheet__character", "character_role__covenant_role", "pick"
        )
    )
    limits: dict[int, list[VowFocusPickLimit]] = defaultdict(list)
    pick_ids = {choice.pick_id for choice in choices}
    for limit in VowFocusPickLimit.objects.filter(pick_id__in=pick_ids) if pick_ids else ():
        limits[limit.pick_id].append(limit)
    totals: dict[tuple[int, int], int] = defaultdict(int)
    memberships: dict[int, CharacterCovenantRole] = {}
    for choice in choices:
        key = (choice.character_role_id, choice.pick.pick_level)
        totals[key] += price_for(choice.pick.value, limits[choice.pick_id])
        memberships[choice.character_role_id] = choice.character_role
    changelist = reverse("admin:arxii_charactervowfocuspick_changelist")
    over: list[tuple[str, int, FlaggedRow]] = []
    for (membership_id, level), total in totals.items():
        if total <= budget:
            continue
        membership = memberships[membership_id]
        holder = membership.character_sheet.character.db_key
        text = f"{holder}, {membership.covenant_role.name} level {level} ({total} of {budget})"
        url = f"{changelist}?{urlencode({'q': holder})}"
        over.append((holder, level, FlaggedRow(text=text, url=url)))
    over.sort(key=lambda item: (item[0], item[1], item[2].text))
    return _flags([row for _holder, _level, row in over])


@dataclass(frozen=True)
class _ConditionWiring:
    """What carries, sets and reads every condition that carries a property.

    ``carrying`` lists those templates by name; the maps are keyed by template pk
    (``setters`` holds the first setter's label and how many there are).
    """

    carrying: list[ConditionTemplate]
    read_properties: dict[int, list[str]]
    setters: dict[int, list[str]]


def _condition_wiring(*, with_condition_readers: bool) -> tuple[_ConditionWiring, set[int]]:
    """The combo map's reads for every property-carrying condition, batched.

    Returns the wiring and the pks of carrying templates something names directly (an
    empty set unless ``with_condition_readers``).
    """
    from web.admin.combo_map import live  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    templates = list(ConditionTemplate.objects.order_by("name"))
    carried = live.properties_carried_by(templates)
    carrying = [t for t in templates if carried[t.pk]]
    if not carrying:
        return _ConditionWiring(carrying=[], read_properties={}, setters={}), set()
    prop_ids = {row.pk for t in carrying for row in carried[t.pk]}
    readers = live.readers_for_properties(Property.objects.filter(pk__in=prop_ids))
    read_properties = {
        t.pk: [row.name for row in carried[t.pk] if readers[row.pk]] for t in carrying
    }
    setters: dict[int, list[str]] = defaultdict(list)
    for setter in live.setters_for_conditions(carrying):
        setters[setter.condition_pk].append(setter.source.label)
    named: set[int] = set()
    if with_condition_readers:
        by_condition = live.readers_for_conditions(carrying)
        named = {pk for pk, rows in by_condition.items() if rows}
    wiring = _ConditionWiring(carrying=carrying, read_properties=read_properties, setters=setters)
    return wiring, named


def _probe_condition_never_read() -> ProbeResult:
    """A condition something lands, carrying properties nothing reads, named by nothing.

    Its properties are what a perk situation, a vow effect or a modifier target reads
    on a carrier; with no reader of any of them and no row naming the condition itself,
    landing it changes nothing in play. A condition that carries no property is not
    flagged here. The same reads as the condition's combo map.
    """
    wiring, named = _condition_wiring(with_condition_readers=True)
    rows: list[FlaggedRow] = []
    for template in wiring.carrying:
        setters = wiring.setters.get(template.pk, [])
        if not setters or wiring.read_properties[template.pk] or template.pk in named:
            continue
        more = f" and {len(setters) - 1} more" if len(setters) > 1 else ""
        rows.append(
            FlaggedRow(
                text=f"{template.name} (set by {setters[0]}{more})",
                url=_condition_map(template.pk),
            )
        )
    return _flags(rows)


def _probe_condition_set_by_nothing() -> ProbeResult:
    """A condition carrying a property something reads, that no authored row lands.

    The reader waits on a carrier that never appears. The same reads as the
    condition's combo map.
    """
    wiring, _named = _condition_wiring(with_condition_readers=False)
    rows = [
        FlaggedRow(
            text=f"{template.name} ({', '.join(wiring.read_properties[template.pk])})",
            url=_condition_map(template.pk),
        )
        for template in wiring.carrying
        if wiring.read_properties[template.pk] and not wiring.setters.get(template.pk)
    ]
    return _flags(rows)


def _probe_pick_blank_payload() -> ProbeResult:
    """A focus pick with no stat scaling, situational perk or added effect of its own.

    A holder can choose it and spend budget on it, and it does nothing. One query.
    """
    from world.covenants.models import (  # noqa: PLC0415
        VowAddedEffect,
        VowFocusPick,
        VowSituationalPerk,
        VowStatScaling,
    )

    def payload(model: type[Model]) -> Exists:
        return Exists(model.objects.filter(focus_pick=OuterRef("pk")))

    picks = (
        VowFocusPick.objects.filter(
            ~payload(VowStatScaling), ~payload(VowSituationalPerk), ~payload(VowAddedEffect)
        )
        .select_related("covenant_role")
        .order_by("covenant_role__name", "pick_level", "name")
    )
    rows = [
        FlaggedRow(
            text=f"{pick.name} ({pick.covenant_role.name})", url=_vow_page(pick.covenant_role_id)
        )
        for pick in picks
    ]
    return _flags(rows)


_CONSUMER_PICKS = "world/covenants/focus_picks.py validate_character_focus_pick(), pick_price()"
_CONSUMER_COMBO = (
    "web/admin/combo_map/sources.py SETTER_SOURCES, READER_SOURCES "
    "(read through web/admin/combo_map/live.py)"
)


def combat_role_declarations() -> tuple[ContentDependency, ...]:
    """The five missing combat content flags, in the order an author works through a vow."""
    return (
        ContentDependency(
            key="combat_vow_no_picks",
            label="Vow with no picks",
            tier=DependencyTier.TUNING,
            consumer=_CONSUMER_PICKS,
            consequence=(
                "A holder of this vow has no focus pick to choose at any level, so the "
                "vow plays as its base kit only."
            ),
            probe=CustomProbe(fn=_probe_vow_no_picks),
            admin_model="CovenantRole",
        ),
        ContentDependency(
            key="combat_holder_over_budget",
            label="Holder over budget",
            tier=DependencyTier.TUNING,
            consumer=_CONSUMER_PICKS,
            consequence=(
                "The holder's picks at that level cost more than the budget, after a price "
                "or budget change; they keep every pick until staff trims one."
            ),
            probe=CustomProbe(fn=_probe_holder_over_budget),
            admin_model="CharacterVowFocusPick",
        ),
        ContentDependency(
            key="combat_condition_never_read",
            label="Condition set, never read",
            tier=DependencyTier.TUNING,
            consumer=_CONSUMER_COMBO,
            consequence=(
                "Something lands this condition, but nothing reads its properties or names "
                "it, so it changes nothing in play beyond its own effects."
            ),
            probe=CustomProbe(fn=_probe_condition_never_read),
            admin_model="ConditionTemplate",
        ),
        ContentDependency(
            key="combat_condition_set_by_nothing",
            label="Condition carrying a read property, set by nothing",
            tier=DependencyTier.TUNING,
            consumer=_CONSUMER_COMBO,
            consequence=(
                "A perk, effect or modifier reads a property this condition carries, but "
                "no technique, vow effect or other row lands the condition, so the reader "
                "never finds a carrier through it."
            ),
            probe=CustomProbe(fn=_probe_condition_set_by_nothing),
            admin_model="ConditionTemplate",
        ),
        ContentDependency(
            key="combat_pick_blank_payload",
            label="Pick with a blank payload",
            tier=DependencyTier.TUNING,
            consumer="world/covenants/focus_picks.py holder_has_pick()",
            consequence=(
                "A holder can choose this pick and spend budget on it, and it adds nothing: "
                "no stat scaling, situational perk or added effect names it."
            ),
            probe=CustomProbe(fn=_probe_pick_blank_payload),
            admin_model="VowFocusPick",
        ),
    )
