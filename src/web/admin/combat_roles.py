"""The Combat roles panel on the admin front page (#4857, slice 1 of #4843).

Every page staff use to author a vow's combat kit, one click from the front page
("I wouldn't want to hunt around for things", owner ruling 2026-11-01). The combo
map arrived with slice 3 (#4891); later slices of #4843 add the kit view and
missing combat content rows here as they land.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Model
from django.urls import reverse


@dataclass(frozen=True)
class RowPicker:
    """A select of rows and an Open button, sent as a GET ``?pk=`` to ``action``.

    ``label`` names the select for a screen reader and goes on the button when a row
    holds more than one picker ("Open property", "Open condition").
    """

    action: str
    choices: list[tuple[int, str]] = field(default_factory=list)
    label: str = ""

    @property
    def button(self) -> str:
        return f"Open {self.label}" if self.label else "Open"


@dataclass(frozen=True)
class CombatRolesLink:
    """One row of the panel: where it goes, what is there now, and its pickers, if any.

    A row with no page of its own (the combo map opens on one row at a time) has a
    blank ``url`` and only its pickers.
    """

    label: str
    url: str
    note: str
    pickers: list[RowPicker] = field(default_factory=list)


def _changelist(model_name: str) -> str:
    return reverse(f"admin:arxii_{model_name}_changelist")


def _plural(noun: str) -> str:
    return f"{noun[:-1]}ies" if noun.endswith("y") else f"{noun}s"


def _counted(model: type[Model], label: str, noun: str) -> CombatRolesLink:
    count = model.objects.count()
    plural = noun if count == 1 else _plural(noun)
    url = _changelist(model.__name__.lower())
    return CombatRolesLink(label=label, url=url, note=f"{count} {plural}")


def _budget_link() -> CombatRolesLink:
    """The focus pick budget row: the singleton's change page, or its list until it exists."""
    from world.covenants.models import VowFocusPickConfig  # noqa: PLC0415

    config = VowFocusPickConfig.objects.cached_singleton()
    if config is None:
        default = VowFocusPickConfig().budget_per_level
        return CombatRolesLink(
            label="Focus pick budget",
            url=_changelist("vowfocuspickconfig"),
            note=f"{default} points per level (default)",
        )
    return CombatRolesLink(
        label="Focus pick budget",
        url=reverse("admin:arxii_vowfocuspickconfig_change", args=[config.pk]),
        note=f"{config.budget_per_level} points per level",
    )


def _vow_pages_link() -> CombatRolesLink:
    """The vow page row: a picker over every vow, opening its vow page (#4880)."""
    from world.covenants.models import CovenantRole  # noqa: PLC0415

    choices = list(CovenantRole.objects.order_by("name").values_list("pk", "name"))
    count = len(choices)
    return CombatRolesLink(
        label="Vow pages",
        url=_changelist("covenantrole"),
        note=f"{count} vow{'' if count == 1 else 's'}",
        pickers=[RowPicker(action=reverse("admin_vow_builder_pick"), choices=choices)],
    )


def _combo_map_link(user: AbstractBaseUser | AnonymousUser) -> CombatRolesLink | None:
    """The combo map row (#4891): a property picker and a condition picker, each gated."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    pickers: list[RowPicker] = []
    if can_view(user, Property):
        choices = list(Property.objects.order_by("name").values_list("pk", "name"))
        pickers.append(
            RowPicker(
                action=reverse("admin_combo_map_property_pick"), choices=choices, label="property"
            )
        )
    if can_view(user, ConditionTemplate):
        choices = list(ConditionTemplate.objects.order_by("name").values_list("pk", "name"))
        pickers.append(
            RowPicker(
                action=reverse("admin_combo_map_condition_pick"),
                choices=choices,
                label="condition",
            )
        )
    if not pickers:
        return None
    return CombatRolesLink(
        label="Combo map", url="", note="by property or condition", pickers=pickers
    )


def can_view(user: AbstractBaseUser | AnonymousUser, model: type[Model]) -> bool:
    """Whether ``user`` may open ``model``'s admin pages: a view or a change permission."""
    return user.has_perm(f"arxii.view_{model.__name__.lower()}") or user.has_perm(
        f"arxii.change_{model.__name__.lower()}"
    )


def combat_roles_links(user: AbstractBaseUser | AnonymousUser) -> list[CombatRolesLink]:
    """The panel's rows a user can open, in the order an author works through a vow.

    A row whose page would refuse the user is left out: a model they cannot view, and
    the vow pages and Required content (the Game Ops dashboard) for anyone but a
    superuser.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.covenants.models import (  # noqa: PLC0415
        CombatStyle,
        CovenantRole,
        VowAddedEffect,
        VowFocusPick,
        VowFocusPickConfig,
        VowSituationalPerk,
    )
    from world.mechanics.models import Property  # noqa: PLC0415

    counted = [
        (CovenantRole, "Covenant roles", "role"),
        (VowFocusPick, "Vow focus picks", "pick"),
        (VowAddedEffect, "Vow added effects", "effect"),
        (VowSituationalPerk, "Vow situational perks", "perk"),
        (CombatStyle, "Combat styles", "style"),
        (ConditionTemplate, "Conditions", "condition"),
        (Property, "Properties", "property"),
    ]
    links: list[CombatRolesLink] = []
    if user.is_superuser:
        # The vow page is superuser-only, like every builder page.
        links.append(_vow_pages_link())
    links.extend(
        _counted(model, label, noun) for model, label, noun in counted if can_view(user, model)
    )
    combo_map = _combo_map_link(user)
    if combo_map is not None:
        links.append(combo_map)
    if can_view(user, VowFocusPickConfig):
        links.append(_budget_link())
    if user.is_superuser:
        links.append(
            CombatRolesLink(
                label="Required content",
                url=reverse("admin_ops"),
                note="missing-content flags",
            )
        )
    return links
