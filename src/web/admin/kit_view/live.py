"""What the kit view reads about one character, never writing (#4918, slice 5 of #4843).

One real character's techniques, each with what its vows add (the static view,
``vow_added_effects_on_techniques``, which ignores the unlock level, context, situation
and frequency by design), the focus picks it chose with each level's spend against the
budget, and the sheet facts a reader needs beside them: path, gifts, vows and the vow's
defense profile. The budget is read without creating the config row, the rule every
Combat roles page keeps on a GET.

The page's query count is fixed however many techniques, added effects or picks the
character has; it grows only with the character's live vow memberships.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.urls import reverse

from web.admin.vow_builder.live import focus_pick_budget
from world.covenants.added_effect_summary import summarize_vow_added_effect
from world.covenants.added_effects import (
    function_tags_by_technique,
    vow_added_effects_on_techniques,
)
from world.covenants.focus_picks import spent_by_membership_level
from world.covenants.models import CharacterVowFocusPick, CovenantRoleDefenseProfile
from world.covenants.perks.services import _SELF_BENEFICIARIES
from world.magic.constants import TargetKind, TechniqueFunction
from world.magic.models import CharacterGift, Technique, Thread
from world.magic.services.technique_effects import technique_payload_prefetches
from world.magic.services.threads import shown_thread_level

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CharacterCovenantRole, CovenantRole, VowAddedEffect

#: The group of a technique's vow lines that no focus pick owns.
BASE_GROUP = "Base"


@dataclass(frozen=True)
class Link:
    """A row's name and its admin page."""

    label: str
    url: str


@dataclass(frozen=True)
class VowLine:
    """One added effect on one technique, as the summary line staff read for it.

    ``unlocks_at`` is the row's unlock level (shown scale) when the character's thread
    on that vow is below it, else ``None``. ``rides`` names whose casts the row rides
    when that is not the character's own ("Covenant allies"), else "".
    """

    text: str
    unlocks_at: int | None = None
    rides: str = ""


@dataclass(frozen=True)
class VowGroup:
    """A technique's vow lines from the base vow, or from one chosen pick."""

    label: str
    lines: list[VowLine] = field(default_factory=list)


@dataclass(frozen=True)
class TechniqueLine:
    """One technique the character knows: what it does, and what the vows add to it.

    ``functions`` is its function tags' labels; ``base`` the plain-words line every
    surface shows for the technique. ``nothing`` says why no vow line is listed, and is
    "" when ``groups`` holds any.
    """

    technique: Link
    functions: str
    base: str
    groups: list[VowGroup] = field(default_factory=list)
    nothing: str = ""


@dataclass(frozen=True)
class PickLevel:
    """The picks one primary vow chose at one pick level, and their price against the budget."""

    vow: str
    level: int
    picks: list[Link]
    spent: int
    budget: int

    @property
    def over(self) -> bool:
        return self.spent > self.budget


@dataclass(frozen=True)
class HeldVow:
    """One live vow membership: the vow, its shown level, and its defense style.

    ``defense`` is the vow's defense profile style label (the resolved sub-role's own
    profile, else its anchor's), or "" when it has none.
    """

    vow: Link
    level: int
    is_secondary: bool
    engaged: bool
    defense: str


@dataclass(frozen=True)
class SheetFacts:
    """The sheet facts the kit view shows beside the techniques."""

    path: str
    gifts: list[str]
    vows: list[HeldVow]


@dataclass(frozen=True)
class Kit:
    """Everything the kit view shows for one character."""

    name: str
    sheet_url: str
    techniques: list[TechniqueLine]
    picks: list[PickLevel]
    picks_url: str
    sheet: SheetFacts

    @property
    def primary_vows(self) -> list[HeldVow]:
        return [vow for vow in self.sheet.vows if not vow.is_secondary]

    @property
    def level(self) -> int | None:
        """The one primary vow's shown level, for the column heading; ``None`` otherwise."""
        primary = self.primary_vows
        return primary[0].level if len(primary) == 1 else None


def _anchor_id(role: CovenantRole) -> int:
    return role.parent_role_id if role.parent_role_id is not None else role.pk


def known_techniques(sheet: CharacterSheet) -> list[Technique]:
    """Every technique the character knows, by name, with the payloads its summary reads.

    One query plus one per payload prefetch (``technique_payload_prefetches``, the shared
    set every summary surface uses), whatever the count.
    """
    return list(
        Technique.objects.filter(character_grants__character=sheet)
        .select_related("gift")
        .prefetch_related(*technique_payload_prefetches())
        .distinct()
        .order_by("name")
    )


def vow_levels(sheet: CharacterSheet) -> dict[int, int]:
    """The character's shown COVENANT_ROLE thread level per anchor role: one query."""
    rows = Thread.objects.filter(
        owner=sheet, target_kind=TargetKind.COVENANT_ROLE, retired_at__isnull=True
    ).values_list("target_covenant_role_id", "level")
    return {role_id: shown_thread_level(level) for role_id, level in rows}


def _vow_line(effect: VowAddedEffect, levels: dict[int, int]) -> VowLine:
    level = levels.get(_anchor_id(effect.covenant_role), 0)
    locked = effect.unlock_thread_level > level
    return VowLine(
        text=summarize_vow_added_effect(effect),
        unlocks_at=effect.unlock_thread_level if locked else None,
        rides="" if effect.beneficiary in _SELF_BENEFICIARIES else effect.get_beneficiary_display(),
    )


def _groups(
    effects: list[VowAddedEffect], levels: dict[int, int], *, name_vows: bool
) -> list[VowGroup]:
    """The base vow's lines first, then one group per chosen pick (by level, then name).

    With more than one live vow, the base group is named after the vow it comes from.
    """
    base: dict[str, list[VowLine]] = {}
    picks: dict[tuple[int, str], list[VowLine]] = {}
    for effect in effects:
        line = _vow_line(effect, levels)
        if effect.focus_pick_id is None:
            label = f"{effect.covenant_role.name} base" if name_vows else BASE_GROUP
            base.setdefault(label, []).append(line)
        else:
            pick = effect.focus_pick
            picks.setdefault((pick.pick_level, pick.name), []).append(line)
    groups = [VowGroup(label=label, lines=lines) for label, lines in sorted(base.items())]
    groups.extend(VowGroup(label=name, lines=picks[(lvl, name)]) for lvl, name in sorted(picks))
    return groups


def _nothing(tags: list[str], labels: str, engaged_vows: list[str]) -> str:
    if not tags:
        return "nothing: it carries no function tag"
    if not engaged_vows:
        return "nothing: no engaged vow"
    return f"nothing: {' and '.join(engaged_vows)} adds nothing to {labels}"


def _labels(tags: list[str], joiner: str) -> str:
    return joiner.join(str(TechniqueFunction(tag).label) for tag in tags)


def technique_lines(
    sheet: CharacterSheet, memberships: list[CharacterCovenantRole], levels: dict[int, int]
) -> list[TechniqueLine]:
    """One line per known technique, with its vow lines grouped base first, then by pick."""
    techniques = known_techniques(sheet)
    tags = function_tags_by_technique(techniques)
    effects = vow_added_effects_on_techniques(sheet, techniques, tags)
    engaged_vows = sorted({m.covenant_role.name for m in memberships if m.engaged})
    name_vows = len({_anchor_id(m.covenant_role) for m in memberships}) > 1
    lines: list[TechniqueLine] = []
    for technique in techniques:
        own_tags = tags[technique.pk]
        groups = _groups(effects[technique.pk], levels, name_vows=name_vows)
        lines.append(
            TechniqueLine(
                technique=Link(
                    label=technique.name,
                    url=reverse("admin:arxii_technique_change", args=[technique.pk]),
                ),
                functions=_labels(own_tags, " · "),
                base=technique.cached_effect_summary["summary"],
                groups=groups,
                nothing=""
                if groups
                else _nothing(own_tags, _labels(own_tags, " or "), engaged_vows),
            )
        )
    return lines


def pick_levels(memberships: list[CharacterCovenantRole]) -> list[PickLevel]:
    """Each live primary vow's chosen picks, one entry per level that has one.

    One query for the choices and one for their limits (none with no primary vow).
    """
    primary = {m.pk: m for m in memberships if not m.is_secondary}
    if not primary:
        return []
    choices = list(
        CharacterVowFocusPick.objects.filter(character_role_id__in=primary)
        .select_related("pick")
        .order_by("pick__pick_level", "pick__name")
    )
    spent = spent_by_membership_level(choices)
    budget = focus_pick_budget()
    by_level: dict[tuple[int, int], list[Link]] = {}
    for choice in choices:
        by_level.setdefault((choice.character_role_id, choice.pick.pick_level), []).append(
            Link(
                label=choice.pick.name,
                url=reverse("admin:arxii_vowfocuspick_change", args=[choice.pick_id]),
            )
        )
    return [
        PickLevel(
            vow=primary[membership_id].covenant_role.name,
            level=level,
            picks=links,
            spent=spent[(membership_id, level)],
            budget=budget,
        )
        for (membership_id, level), links in sorted(
            by_level.items(),
            key=lambda item: (primary[item[0][0]].covenant_role.name, item[0][1]),
        )
    ]


def held_vows(
    sheet: CharacterSheet, memberships: list[CharacterCovenantRole], levels: dict[int, int]
) -> list[HeldVow]:
    """Each live membership, primary first: one query for the defense profiles.

    A primary vow's defense is its resolved sub-role's own profile, else its anchor's
    (``engaged_primary_defense_profile``'s rule); a secondary vow reads its own role.
    """
    from world.covenants.services import resolve_effective_role  # noqa: PLC0415

    character = sheet.character
    resolved: dict[int, CovenantRole] = {
        m.pk: (
            m.covenant_role
            if m.is_secondary
            else resolve_effective_role(character=character, role=m.covenant_role)
        )
        for m in memberships
    }
    role_ids = {role.pk for role in resolved.values()} | {
        _anchor_id(role) for role in resolved.values()
    }
    profiles = {
        profile.covenant_role_id: profile
        for profile in CovenantRoleDefenseProfile.objects.filter(covenant_role_id__in=role_ids)
    }
    vows: list[HeldVow] = []
    for membership in sorted(memberships, key=lambda m: (m.is_secondary, m.covenant_role.name)):
        role = resolved[membership.pk]
        profile = profiles.get(role.pk) or profiles.get(_anchor_id(role))
        vows.append(
            HeldVow(
                vow=Link(
                    label=membership.covenant_role.name,
                    url=reverse("admin_vow_builder", args=[membership.covenant_role_id]),
                ),
                level=levels.get(_anchor_id(membership.covenant_role), 0),
                is_secondary=membership.is_secondary,
                engaged=membership.engaged,
                defense=profile.get_style_display() if profile is not None else "",
            )
        )
    return vows


def sheet_facts(
    sheet: CharacterSheet, memberships: list[CharacterCovenantRole], levels: dict[int, int]
) -> SheetFacts:
    """Path (the newest path history row), gifts by name, and the live vows."""
    history = sheet.cached_path_history
    gifts = (
        CharacterGift.objects.filter(character=sheet)
        .order_by("gift__name")
        .values_list("gift__name", flat=True)
    )
    return SheetFacts(
        path=history[0].path.name if history else "",
        gifts=list(gifts),
        vows=held_vows(sheet, memberships, levels),
    )


def kit_for(sheet: CharacterSheet) -> Kit:
    """The kit view of one character. Renders for a character with no vow or technique."""
    name = sheet.character.db_key
    memberships = list(sheet.character.covenant_roles.active_memberships)
    levels = vow_levels(sheet) if memberships else {}
    changelist = reverse("admin:arxii_charactervowfocuspick_changelist")
    return Kit(
        name=name,
        sheet_url=reverse("admin:arxii_charactersheet_change", args=[sheet.pk]),
        techniques=technique_lines(sheet, memberships, levels),
        picks=pick_levels(memberships),
        picks_url=f"{changelist}?{urlencode({'q': name})}",
        sheet=sheet_facts(sheet, memberships, levels),
    )
