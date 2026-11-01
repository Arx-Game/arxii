"""The Combat roles panel on the admin front page (#4857, slice 1 of #4843).

Every page staff use to author a vow's combat kit, one click from the front page
("I wouldn't want to hunt around for things", owner ruling 2026-11-01). Later
slices of #4843 add the vow page, combo map, kit view and missing combat content
rows here as they land.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Model
from django.urls import reverse


@dataclass(frozen=True)
class CombatRolesLink:
    """One row of the panel: where it goes, and what is there now."""

    label: str
    url: str
    note: str


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


def combat_roles_links() -> list[CombatRolesLink]:
    """The panel's rows, in the order an author works through a vow."""
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.covenants.models import (  # noqa: PLC0415
        CombatStyle,
        CovenantRole,
        VowAddedEffect,
        VowFocusPick,
        VowSituationalPerk,
    )
    from world.mechanics.models import Property  # noqa: PLC0415

    return [
        _counted(CovenantRole, "Covenant roles", "role"),
        _counted(VowFocusPick, "Vow focus picks", "pick"),
        _counted(VowAddedEffect, "Vow added effects", "effect"),
        _counted(VowSituationalPerk, "Vow situational perks", "perk"),
        _counted(CombatStyle, "Combat styles", "style"),
        _counted(ConditionTemplate, "Conditions", "condition"),
        _counted(Property, "Properties", "property"),
        _budget_link(),
        CombatRolesLink(
            label="Required content",
            url=reverse("admin_ops"),
            note="missing-content flags",
        ),
    ]
