"""What the kit view reads about one character, never writing (#4918, slice 5 of #4843).

One real character's techniques, each with what its vows add (the static view,
``vow_added_effects_on_techniques``, which ignores the unlock level, context, situation
and frequency by design) and its power preview (#4930), the focus picks it chose with
each level's spend against the budget, and the sheet facts a reader needs beside them:
path, gifts, vows, the vow's defense profile and the combat style (#4932). The budget is
read without creating the config row, the rule every Combat roles page keeps on a GET.

The page's query count is fixed however many added effects or picks the character has;
it grows with the character's live vow memberships, and by the power evaluator's own
per-technique reads for each known technique (the Preview column, #4930).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.urls import reverse

from web.admin.authoring.combat_styles import StyleOnVow, style_change_url, style_on_vow
from web.admin.authoring.power_preview import PreviewFrame, preview_de, preview_frame
from web.admin.vow_builder.live import focus_pick_budget
from world.covenants.added_effect_summary import summarize_vow_added_effect
from world.covenants.added_effects import (
    function_tags_by_technique,
    vow_added_effects_on_techniques,
)
from world.covenants.focus_picks import spent_by_membership_level
from world.covenants.models import CharacterVowFocusPick, CovenantRoleDefenseProfile
from world.covenants.perks.services import _SELF_BENEFICIARIES
from world.covenants.style_fit import style_vow_ids
from world.magic.constants import TargetKind, TechniqueFunction
from world.magic.models import CharacterGift, Technique, Thread
from world.magic.services.technique_effects import technique_payload_prefetches
from world.magic.services.threads import shown_thread_level

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import (
        CharacterCovenantRole,
        CombatStyle,
        CovenantRole,
        VowAddedEffect,
    )

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
    "" when ``groups`` holds any. ``preview`` is the power preview (#4930): "N DE" with
    the character's own vow lines at its vow level (``power_preview.preview_de``), the
    technique's own DE with no line, or "n/a" for a technique with no function tag.
    """

    technique: Link
    functions: str
    base: str
    groups: list[VowGroup] = field(default_factory=list)
    nothing: str = ""
    preview: str = ""


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
    profile, else its anchor's), or "" when it has none. ``style`` says whether the
    character's combat style works with a primary vow (#4932, the resolved sub-role
    against ``style_fit``'s rule); None for a secondary vow or a character with no style.
    """

    vow: Link
    level: int
    is_secondary: bool
    engaged: bool
    defense: str
    style: StyleOnVow | None = None


@dataclass(frozen=True)
class SheetFacts:
    """The sheet facts the kit view shows beside the techniques.

    ``style`` is the character's combat style, linked to its change page, or None.
    """

    path: str
    gifts: list[str]
    vows: list[HeldVow]
    style: Link | None = None

    @property
    def style_lines(self) -> list[str]:
        """Whether the style works with each held primary vow, in words."""
        return [vow.style.text for vow in self.vows if vow.style is not None]


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
        .select_related("gift", "effect_type")
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


#: The Preview cell of a technique with no function tag: no vow line can ride it.
NO_PREVIEW = "n/a"


def _preview(
    technique: Technique,
    tags: list[str],
    effects: list[VowAddedEffect],
    levels: dict[int, int],
    frame: PreviewFrame,
) -> str:
    """The technique's DE with its vow lines, at the highest level among their vows."""
    if not tags:
        return NO_PREVIEW
    level = max((levels.get(_anchor_id(e.covenant_role), 0) for e in effects), default=0)
    return f"{preview_de(technique, frame, effects, level)} DE"


def technique_lines(
    sheet: CharacterSheet, memberships: list[CharacterCovenantRole], levels: dict[int, int]
) -> list[TechniqueLine]:
    """One line per known technique, with its vow lines grouped base first, then by pick."""
    techniques = known_techniques(sheet)
    tags = function_tags_by_technique(techniques)
    effects = vow_added_effects_on_techniques(sheet, techniques, tags)
    engaged_vows = sorted({m.covenant_role.name for m in memberships if m.engaged})
    name_vows = len({_anchor_id(m.covenant_role) for m in memberships}) > 1
    frame = preview_frame() if techniques else None
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
                preview=_preview(technique, own_tags, effects[technique.pk], levels, frame)
                if frame is not None
                else "",
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
    sheet: CharacterSheet,
    memberships: list[CharacterCovenantRole],
    levels: dict[int, int],
    style: CombatStyle | None = None,
) -> list[HeldVow]:
    """Each live membership, primary first: one query for the defense profiles.

    A primary vow's defense is its resolved sub-role's own profile, else its anchor's
    (``engaged_primary_defense_profile``'s rule); a secondary vow reads its own role.
    With ``style``, each primary vow also says whether the style works with it (one
    query for the vows the style lists, ``style_vow_ids``, however many vows are held).
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
    listed = style_vow_ids(style) if style is not None else set()
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
                style=(
                    style_on_vow(style, role, listed)
                    if style is not None and not membership.is_secondary
                    else None
                ),
            )
        )
    return vows


def sheet_facts(
    sheet: CharacterSheet, memberships: list[CharacterCovenantRole], levels: dict[int, int]
) -> SheetFacts:
    """Path (the newest path history row), gifts by name, the live vows and the style.

    No query for the style when the sheet has none.
    """
    style = sheet.combat_style if sheet.combat_style_id is not None else None
    history = sheet.cached_path_history
    gifts = (
        CharacterGift.objects.filter(character=sheet)
        .order_by("gift__name")
        .values_list("gift__name", flat=True)
    )
    return SheetFacts(
        path=history[0].path.name if history else "",
        gifts=list(gifts),
        vows=held_vows(sheet, memberships, levels, style),
        style=Link(label=style.name, url=style_change_url(style)) if style is not None else None,
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
