"""Which combat styles work with a vow, and what a mismatch costs (#4932).

Slice 7 of #4843. The vow page's "Combat styles that work with this vow" module and the
kit view's Style row read it. Whether a style works with a vow is
``world.covenants.style_fit``'s rule (``styles_listing_vow`` / ``style_lists_vow``): a
style works with a vow it lists, and with a sub-role whose anchor it lists. What a
mismatch costs is the same module's lapse rule: a held vow the style does not list turns
the style skill off on attack and defense rolls, while its hit stat and defense type
still apply. A style with no skill, or an inactive one, has no skill term to lose.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.urls import reverse

from world.covenants.models import CharacterCovenantRole, CombatStyle
from world.covenants.style_fit import style_lists_vow, styles_listing_vow

if TYPE_CHECKING:
    from world.covenants.models import CovenantRole

#: What a mismatch costs for a style with no active skill.
NO_SKILL_COST = "No style skill to lose; its hit stat and defense type apply as usual."


def _skill_name(style: CombatStyle) -> str | None:
    """The style's active skill's name, or None when it has none to add to a roll."""
    skill = style.skill
    if skill is None or not skill.is_active:
        return None
    return skill.name


def style_change_url(style: CombatStyle) -> str:
    """The style's stock admin change page."""
    return reverse("admin:arxii_combatstyle_change", args=[style.pk])


@dataclass(frozen=True)
class StyleRow:
    """One combat style as the vow page lists it against one vow.

    ``works`` is whether the style lists the vow (a sub-role by its anchor).
    ``skill_name`` is the style's active skill, or None. ``holders`` counts the vow's
    live primary holders whose sheet fights this style.
    """

    name: str
    url: str
    works: bool
    skill_name: str | None
    holders: int

    @property
    def mismatch(self) -> str:
        """What fighting this style costs a holder of the vow; "" for a style that works."""
        return "" if self.works else mismatch_line(self)


def mismatch_line(row: StyleRow) -> str:
    """The cost of a style that does not work with the vow, in plain words."""
    if row.skill_name is None:
        return NO_SKILL_COST
    return (
        f"A holder fighting this style loses {row.skill_name} on attack and defense rolls; "
        "its hit stat and defense type still apply."
    )


def _holders_by_style(role: CovenantRole) -> Counter[int]:
    """How many live primary holders of ``role`` fight each style: one query.

    A character holding the vow in two covenants counts once.
    """
    rows = (
        CharacterCovenantRole.objects.filter(
            covenant_role=role,
            left_at__isnull=True,
            is_secondary=False,
            character_sheet__combat_style__isnull=False,
        )
        .values_list("character_sheet_id", "character_sheet__combat_style_id")
        .distinct()
    )
    return Counter(style_id for _sheet_id, style_id in rows)


def styles_for_vow(role: CovenantRole) -> list[StyleRow]:
    """Every combat style by name, each against ``role``.

    Three queries however many styles: the styles with their skills, the styles listing
    the vow, and the holders per style.
    """
    styles = list(CombatStyle.objects.select_related("skill__trait").order_by("name"))
    if not styles:
        return []
    listing = styles_listing_vow(role)
    holders = _holders_by_style(role)
    return [
        StyleRow(
            name=style.name,
            url=style_change_url(style),
            works=style.pk in listing,
            skill_name=_skill_name(style),
            holders=holders.get(style.pk, 0),
        )
        for style in styles
    ]


@dataclass(frozen=True)
class StyleOnVow:
    """Whether a character's style works with one of its held primary vows, in words."""

    vow: str
    works: bool
    text: str


def style_on_vow(style: CombatStyle, role: CovenantRole) -> StyleOnVow:
    """The kit view's line for ``style`` against one held primary vow (``role`` resolved).

    One query (``style_lists_vow``).
    """
    if style_lists_vow(style, role):
        return StyleOnVow(vow=role.name, works=True, text=f"works with {role.name}")
    text = f"not a style for {role.name}"
    if _skill_name(style) is not None:
        text += ": its skill does not count on attack and defense rolls"
    return StyleOnVow(vow=role.name, works=False, text=text)
