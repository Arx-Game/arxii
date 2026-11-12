"""Vow focus pick prices and the rules a character's choice must pass (#4759).

A focus pick (``VowFocusPick``) is an option a vow holder chooses at pick level
1, 2 or 3. Its price is worked out from its ``value`` and its limits, never
stored; a character's chosen picks at one level must fit the budget on
``VowFocusPickConfig``. ``CharacterVowFocusPick.clean()`` calls
``validate_character_focus_pick`` so the admin refuses a choice that breaks a
rule, with the reason.

A player chooses through ``choose_vow_focus_pick`` (#4929), which runs the same
rules; ``vow_pick_catalogs`` is what the holder reads first (every pick by level,
the chosen ones marked, the locked ones with why), and ``new_picks_lines`` is the
line imbuing and joining print when a vow level opens new picks.

In play (slice 2), a payload row (``VowAddedEffect``, ``VowSituationalPerk``,
``VowStatScaling``) whose ``focus_pick`` is set fires only for a
holder who chose that pick; ``chosen_pick_ids_by_holder`` answers "which picks
has each holder chosen" for every reader in one query, and
``holder_has_pick`` is the gate each reader applies per row.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import prod
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from world.covenants.constants import (
    FOCUS_PICK_FREQUENCY_LIMIT_KINDS,
    FOCUS_PICK_LIMIT_FREQUENCY_FULL,
    FOCUS_PICK_REDUCTION_LIMIT_KINDS,
    VOW_FOCUS_PICK_LEVELS,
)
from world.covenants.exceptions import VowFocusPickRefusedError
from world.covenants.models import (
    CharacterCovenantRole,
    CharacterVowFocusPick,
    VowFocusPick,
    VowFocusPickConfig,
    VowFocusPickLimit,
)
from world.covenants.types import (
    NewPicks,
    ReswearOptions,
    ReswearResult,
    VowPickCatalog,
    VowPickEntry,
    VowPickLevel,
)

if TYPE_CHECKING:
    from world.action_points.models import ActionPointPool
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual, RitualComponentRequirement, Thread
    from world.magic.types.threads import ThreadImbueResult

#: The lowest price any pick can cost, however many limits it carries.
MIN_PICK_PRICE = 1


def vow_focus_pick_config() -> VowFocusPickConfig:
    """Return the VowFocusPickConfig singleton (pk=1), creating it with defaults."""
    config = VowFocusPickConfig.objects.cached_singleton()
    if config is None:
        config, _ = VowFocusPickConfig.objects.get_or_create(pk=1)
    return config


def focus_pick_budget() -> int:
    """The budget per pick level, read without creating the config row on a GET."""
    config = VowFocusPickConfig.objects.cached_singleton()
    if config is None:
        return VowFocusPickConfig().budget_per_level
    return config.budget_per_level


def pick_price(pick: VowFocusPick) -> int:
    """The price of a focus pick, worked out from its value and limits (#4759).

    ``max(1, floor(value x product(frequency_tenths / 10)) - sum(reduction))``. The
    frequency product runs over SELF, TARGET, SETTING and TIMING limits; the
    reductions over EXPOSURE and COST limits. Integer arithmetic throughout, so
    value 4 with one limit at frequency 5 is exactly 2.
    """
    return price_for(pick.value, pick.cached_limits)


def price_for(value: int, limits: Iterable[VowFocusPickLimit]) -> int:
    """The price formula itself, for a value and limits that need not be saved yet.

    ``pick_price`` calls it with a saved pick's own rows; the vow page (#4880) calls it
    with the value and limits an unsaved edit would leave, to warn holders before the
    save.
    """
    limits = list(limits)
    frequencies = [
        limit.frequency_tenths for limit in limits if limit.kind in FOCUS_PICK_FREQUENCY_LIMIT_KINDS
    ]
    reductions = sum(
        limit.reduction for limit in limits if limit.kind in FOCUS_PICK_REDUCTION_LIMIT_KINDS
    )
    scaled = value * prod(frequencies) // FOCUS_PICK_LIMIT_FREQUENCY_FULL ** len(frequencies)
    return max(MIN_PICK_PRICE, scaled - reductions)


def spent_by_membership_level(
    choices: Sequence[CharacterVowFocusPick],
) -> dict[tuple[int, int], int]:
    """What each membership has spent at each pick level, keyed ``(character_role_id, level)``.

    ``choices`` carry their ``pick`` (select_related by the caller). Each pick is priced
    through ``price_for``, the formula ``pick_price`` runs, from one query for the limits
    of every pick the choices name (none when there are no choices). Shared by the Holder
    over budget flag and the kit view (#4918), so both sum a level the same way.
    """
    pick_ids = {choice.pick_id for choice in choices}
    limits: dict[int, list[VowFocusPickLimit]] = defaultdict(list)
    for limit in VowFocusPickLimit.objects.filter(pick_id__in=pick_ids) if pick_ids else ():
        limits[limit.pick_id].append(limit)
    totals: dict[tuple[int, int], int] = defaultdict(int)
    for choice in choices:
        key = (choice.character_role_id, choice.pick.pick_level)
        totals[key] += price_for(choice.pick.value, limits[choice.pick_id])
    return dict(totals)


def chosen_pick_ids_by_holder(holder_ids: Iterable[int]) -> dict[int, set[int]]:
    """The focus picks each holder has chosen, keyed by CharacterSheet pk (#4759 slice 2).

    One query across every holder, counting only picks on a membership the
    holder has not left. A holder with no chosen pick is absent, so callers read
    ``.get(pk, set())``. No query when ``holder_ids`` is empty. Callers ask only
    when a row they fetched carries a pick, so a vow with no picks costs nothing.
    """
    ids = set(holder_ids)
    if not ids:
        return {}
    rows = CharacterVowFocusPick.objects.filter(
        character_role__character_sheet_id__in=ids,
        character_role__left_at__isnull=True,
    ).values_list("character_role__character_sheet_id", "pick_id")
    chosen: dict[int, set[int]] = {}
    for sheet_id, pick_id in rows:
        chosen.setdefault(sheet_id, set()).add(pick_id)
    return chosen


def holder_has_pick(focus_pick_id: int | None, holder_id: int, chosen: dict[int, set[int]]) -> bool:
    """True when a payload row with ``focus_pick_id`` applies to the holder (#4759 slice 2).

    A row with no pick is the base vow and applies to every holder. A row with a
    pick applies only when the holder chose it; ``chosen`` is the map
    ``chosen_pick_ids_by_holder`` returned.
    """
    return focus_pick_id is None or focus_pick_id in chosen.get(holder_id, ())


def vow_level(membership: CharacterCovenantRole) -> int:
    """The COVENANT_ROLE thread level behind a membership (#4759).

    Threads key on the anchor role, so a sub-role membership reads its parent's
    thread.
    """
    from world.covenants.services import _covenant_role_thread_level  # noqa: PLC0415

    role = membership.covenant_role
    anchor = role.parent_role if role.parent_role_id is not None else role
    return _covenant_role_thread_level(membership.character_sheet, anchor)


def choosable_role_ids(membership: CharacterCovenantRole) -> set[int]:
    """Roles whose catalogs this membership may choose from (#4759).

    The held role, its anchor (parent) role, and the sub-role the character has
    grown into on it, plus that sub-role's anchor. A sub-role holder chooses from
    the anchor vow's catalog and the sub-role's own.
    """
    from world.covenants.services import resolve_effective_role  # noqa: PLC0415

    held = membership.covenant_role
    role_ids = {held.pk}
    if held.parent_role_id is not None:
        role_ids.add(held.parent_role_id)
    effective = resolve_effective_role(character=membership.character_sheet.character, role=held)
    role_ids.add(effective.pk)
    if effective.parent_role_id is not None:
        role_ids.add(effective.parent_role_id)
    return role_ids


def validate_character_focus_pick(choice: CharacterVowFocusPick) -> None:
    """Refuse a chosen focus pick that breaks a rule, naming the reason (#4759).

    In order: the membership is a primary vow (a secondary vow gets no picks);
    the pick is in the held vow's catalog (or its anchor's, for a sub-role);
    the pick's level is no higher than the vow level; and the prices of the
    membership's picks at that level fit ``VowFocusPickConfig.budget_per_level``.
    """
    membership = choice.character_role
    pick = choice.pick
    if membership.is_secondary:
        raise ValidationError(
            {"character_role": "This is a secondary vow, and a secondary vow gets no focus picks."}
        )
    if pick.covenant_role_id not in choosable_role_ids(membership):
        raise ValidationError(
            {
                "pick": (
                    f"'{pick.name}' is a pick of {pick.covenant_role.name}, which is not "
                    f"this character's vow ({membership.covenant_role.name})."
                )
            }
        )
    level = vow_level(membership)
    if pick.pick_level > level:
        raise ValidationError(
            {
                "pick": (
                    f"'{pick.name}' is a level {pick.pick_level} pick, and this character's "
                    f"vow is at level {level}."
                )
            }
        )
    siblings = (
        CharacterVowFocusPick.objects.filter(
            character_role=membership, pick__pick_level=pick.pick_level
        )
        .exclude(pk=choice.pk)
        .select_related("pick")
    )
    spent = sum(pick_price(sibling.pick) for sibling in siblings)
    price = pick_price(pick)
    budget = vow_focus_pick_config().budget_per_level
    if spent + price > budget:
        raise ValidationError(
            {
                "pick": (
                    f"'{pick.name}' costs {price}, and this character has already spent "
                    f"{spent} of the {budget} points for level {pick.pick_level} picks."
                )
            }
        )


# ---------------------------------------------------------------------------
# A player choosing their own picks (#4929, slice 6 of #4844)


NO_LONGER_HELD_MESSAGE = "You no longer hold this vow."


def _lock_held(membership: CharacterCovenantRole) -> bool:
    """Lock ``membership``'s row; True while the database says the vow is still held.

    A filter, not get(): the identity map would answer get() without the lock. Called
    inside the caller's transaction, so the lock lasts until it commits.
    """
    locked = CharacterCovenantRole.objects.select_for_update().filter(pk=membership.pk)
    return bool(list(locked.filter(left_at__isnull=True).values_list("pk", flat=True)))


def _refusal_text(exc: ValidationError) -> str:
    """The first message of a validator refusal, which names the rule it broke."""
    return next(iter(exc.messages), VowFocusPickRefusedError.user_message)


def choose_vow_focus_pick(
    membership: CharacterCovenantRole, pick: VowFocusPick
) -> CharacterVowFocusPick:
    """Choose ``pick`` on ``membership`` for its holder, or refuse with the reason (#4929).

    The same rules as the admin (``validate_character_focus_pick``: a primary vow, the
    pick in its catalog, the level reached, the level's budget), plus two the admin
    form never meets: the vow is still held, and the pick is not already chosen. The
    membership row is locked first, so two choices sent at once cannot both spend the
    last of a level's budget. Unspent budget simply waits; there is no un-choose here
    (changing a chosen pick is the Rite of Re-swearing).

    Raises:
        VowFocusPickRefusedError: naming the rule the choice breaks.
    """
    with transaction.atomic():
        if not _lock_held(membership):
            raise VowFocusPickRefusedError(NO_LONGER_HELD_MESSAGE)
        if CharacterVowFocusPick.objects.filter(character_role=membership, pick=pick).exists():
            msg = f"You have already chosen {pick.name}."
            raise VowFocusPickRefusedError(msg)
        choice = CharacterVowFocusPick(character_role=membership, pick=pick)
        try:
            validate_character_focus_pick(choice)
        except ValidationError as exc:
            raise VowFocusPickRefusedError(_refusal_text(exc)) from exc
        choice.save()
    return choice


def spent_at_level(membership: CharacterCovenantRole, level: int) -> int:
    """What ``membership`` has spent on its picks at pick ``level``."""
    choices = list(
        CharacterVowFocusPick.objects.filter(
            character_role=membership, pick__pick_level=level
        ).select_related("pick")
    )
    return spent_by_membership_level(choices).get((membership.pk, level), 0)


def limit_line(limit: VowFocusPickLimit) -> str:
    """One limit as a holder reads it: "Target limit: a boss, met 3 times in 10"."""
    head = f"{limit.get_kind_display()} limit"
    if limit.description:
        head += f": {limit.description}"
    if limit.kind in FOCUS_PICK_FREQUENCY_LIMIT_KINDS:
        tail = f"met {limit.frequency_tenths} times in {FOCUS_PICK_LIMIT_FREQUENCY_FULL}"
    else:
        tail = f"price less {limit.reduction}"
    return f"{head}, {tail}"


def limits_line(limits: Iterable[VowFocusPickLimit]) -> str:
    """Every limit of a pick in one line, or "no limits"."""
    return " · ".join(limit_line(limit) for limit in limits) or "no limits"


def pick_effect_lines(pick_ids: set[int]) -> dict[int, list[str]]:
    """The plain-words line of every payload row on these picks, keyed by pick pk.

    The added effects, situational perks and stat scalings that name a pick are what
    it adds. A fixed number of queries however many picks are asked about, and none
    when none are.
    """
    from world.covenants.added_effect_summary import (  # noqa: PLC0415
        summarize_situational_perk,
        summarize_stat_scaling,
        summarize_vow_added_effect,
    )
    from world.covenants.added_effects import payload_prefetches  # noqa: PLC0415
    from world.covenants.models import (  # noqa: PLC0415
        VowAddedEffect,
        VowSituationalPerk,
        VowSituationalPerkRung,
        VowSituationalPerkSituation,
        VowStatScaling,
    )

    lines: dict[int, list[str]] = defaultdict(list)
    if not pick_ids:
        return lines
    effects = (
        VowAddedEffect.objects.filter(focus_pick_id__in=pick_ids)
        .select_related("gift", "technique")
        .prefetch_related(*payload_prefetches())
    )
    for effect in effects:
        lines[effect.focus_pick_id].append(summarize_vow_added_effect(effect))
    situations: dict[int, list[str]] = defaultdict(list)
    for row in VowSituationalPerkSituation.objects.filter(perk__focus_pick_id__in=pick_ids):
        situations[row.perk_id].append(row.get_situation_display())
    rungs: dict[int, list[VowSituationalPerkRung]] = defaultdict(list)
    for rung in VowSituationalPerkRung.objects.filter(perk__focus_pick_id__in=pick_ids).order_by(
        "perk_id", "rung_number"
    ):
        rungs[rung.perk_id].append(rung)
    for perk in VowSituationalPerk.objects.filter(focus_pick_id__in=pick_ids):
        lines[perk.focus_pick_id].append(
            summarize_situational_perk(perk, situations[perk.pk], rungs[perk.pk])
        )
    scalings = VowStatScaling.objects.filter(focus_pick_id__in=pick_ids).select_related(
        "modifier_target__category"
    )
    for scaling in scalings:
        lines[scaling.focus_pick_id].append(summarize_stat_scaling(scaling))
    return lines


def _locked_reason(pick: VowFocusPick, price: int, *, vow_level: int, left: int) -> str:
    """Why a pick not yet chosen cannot be chosen now, or blank when it can."""
    if pick.pick_level > vow_level:
        return f"opens at vow level {pick.pick_level}"
    if price > left:
        return "costs more than is left"
    return ""


@dataclass(frozen=True)
class _CatalogReads:
    """The rows every membership's catalog reads, each fetched once for them all."""

    picks: Sequence[VowFocusPick]
    limits: dict[int, list[VowFocusPickLimit]]
    spent: dict[tuple[int, int], int]
    effects: dict[int, list[str]]


def _catalog_for(
    membership: CharacterCovenantRole,
    role_ids: set[int],
    chosen_ids: set[int],
    reads: _CatalogReads,
) -> VowPickCatalog:
    budget = focus_pick_budget()
    current_vow_level = vow_level(membership)
    levels: list[VowPickLevel] = []
    for level in VOW_FOCUS_PICK_LEVELS:
        level_spent = reads.spent.get((membership.pk, level), 0)
        left = max(0, budget - level_spent)
        entries = []
        for pick in sorted(reads.picks, key=_anchor_first):
            if pick.pick_level != level or pick.covenant_role_id not in role_ids:
                continue
            pick_limits = reads.limits.get(pick.pk, [])
            price = price_for(pick.value, pick_limits)
            chosen = pick.pk in chosen_ids
            entries.append(
                VowPickEntry(
                    id=pick.pk,
                    vow=pick.covenant_role.name,
                    name=pick.name,
                    description=pick.description,
                    price=price,
                    effects=reads.effects.get(pick.pk, []),
                    limits=limits_line(pick_limits),
                    chosen=chosen,
                    locked_reason=(
                        ""
                        if chosen
                        else _locked_reason(pick, price, vow_level=current_vow_level, left=left)
                    ),
                )
            )
        levels.append(
            VowPickLevel(
                level=level,
                is_open=level <= current_vow_level,
                budget=budget,
                spent=level_spent,
                picks=entries,
            )
        )
    return VowPickCatalog(
        membership_id=membership.pk,
        covenant_id=membership.covenant_id,
        covenant=membership.covenant.name,
        vow=membership.covenant_role.name,
        vow_level=current_vow_level,
        vows=list(dict.fromkeys(entry.vow for level in levels for entry in level.picks)),
        levels=levels,
    )


def _anchor_first(pick: VowFocusPick) -> tuple[bool, str, str]:
    """The anchor vow's picks before a sub-role's, then by vow and pick name."""
    return (pick.covenant_role.parent_role_id is not None, pick.covenant_role.name, pick.name)


def vow_pick_catalogs(sheet: CharacterSheet) -> list[VowPickCatalog]:
    """Every focus pick each of the character's primary vows offers, by level (#4929).

    One catalog per active, non-secondary membership (a secondary vow gets no picks).
    Each level lists every pick the vow and its sub-role offer, the chosen ones marked
    and the others with why they are locked, beside the level's budget and spend. The
    picks, their limits, the choices and the payload lines are each one query for all
    the memberships; the vow level and sub-role are read per membership, and a
    character holds at most one membership per covenant.
    """
    memberships = list(
        CharacterCovenantRole.objects.filter(
            character_sheet=sheet, left_at__isnull=True, is_secondary=False
        )
        .select_related("covenant", "covenant_role")
        .order_by("covenant__name")
    )
    if not memberships:
        return []
    role_ids = {m.pk: choosable_role_ids(m) for m in memberships}
    every_role_id = set().union(*role_ids.values())
    picks = list(
        VowFocusPick.objects.filter(covenant_role_id__in=every_role_id)
        .select_related("covenant_role")
        .order_by("pick_level", "name")
    )
    limits: dict[int, list[VowFocusPickLimit]] = defaultdict(list)
    for limit in VowFocusPickLimit.objects.filter(pick__in=picks) if picks else ():
        limits[limit.pick_id].append(limit)
    choices = list(
        CharacterVowFocusPick.objects.filter(character_role__in=memberships).select_related("pick")
    )
    chosen: dict[int, set[int]] = defaultdict(set)
    for choice in choices:
        chosen[choice.character_role_id].add(choice.pick_id)
    spent = spent_by_membership_level(choices)
    effects = pick_effect_lines({pick.pk for pick in picks})
    reads = _CatalogReads(picks=picks, limits=limits, spent=spent, effects=effects)
    return [_catalog_for(m, role_ids[m.pk], chosen[m.pk], reads) for m in memberships]


def resolve_pick_for_choice(
    sheet: CharacterSheet,
    *,
    pick_id: int | None = None,
    pick_name: str = "",
    covenant_id: int | None = None,
) -> tuple[CharacterCovenantRole, VowFocusPick]:
    """The holder's membership and the pick they named, by id (web) or name (telnet).

    Only the caller's own active memberships are searched (one covenant when
    ``covenant_id`` is given), and only picks those vows offer, so a client cannot
    name another character's membership. A secondary vow is searched too, so the
    choice is refused with the rule's own reason rather than "no such pick".

    Raises:
        VowFocusPickRefusedError: no vow held, no such pick, or a name two vows share.
    """
    memberships = CharacterCovenantRole.objects.filter(
        character_sheet=sheet, left_at__isnull=True
    ).select_related("covenant", "covenant_role")
    if covenant_id is not None:
        memberships = memberships.filter(covenant_id=covenant_id)
    memberships = list(memberships)
    if not memberships:
        msg = "You hold no vow in that covenant." if covenant_id is not None else "You hold no vow."
        raise VowFocusPickRefusedError(msg)
    role_ids = {m.pk: choosable_role_ids(m) for m in memberships}
    every_role_id = set().union(*role_ids.values())
    picks = VowFocusPick.objects.filter(covenant_role_id__in=every_role_id)
    lookup = {"pk": pick_id} if pick_id is not None else {"name__iexact": pick_name}
    found = list(picks.filter(**lookup))
    if not found:
        named = f" named {pick_name}" if pick_name else ""
        msg = f"Your vow offers no pick{named}."
        raise VowFocusPickRefusedError(msg)
    holders = [
        (m, pick) for pick in found for m in memberships if pick.covenant_role_id in role_ids[m.pk]
    ]
    if len(holders) > 1:
        names = sorted({m.covenant.name for m, _ in holders})
        if len(names) == 1:
            msg = f"Your vow offers two picks named {pick_name}; choose one on your sheet."
        else:
            msg = f"Which covenant? Your vows offering it are in: {', '.join(names)}."
        raise VowFocusPickRefusedError(msg)
    return holders[0]


# ---------------------------------------------------------------------------
# Telling a holder a vow level opened new picks (#4929)


def opened_pick_levels(before: int, after: int) -> list[int]:
    """The pick levels a rise in vow level from ``before`` to ``after`` opens.

    Only pick levels 10, 20 and 30 exist, so a rise past 30 opens nothing more.
    """
    return [level for level in VOW_FOCUS_PICK_LEVELS if before < level <= after]


def new_picks(levels: Iterable[int]) -> list[NewPicks]:
    """Each opened pick level with the points it gives: the budget per level."""
    budget = focus_pick_budget()
    return [NewPicks(level=level, points=budget) for level in levels]


def new_picks_lines(levels: Iterable[int]) -> list[str]:
    """One "Vow level 20: 4 pts of new picks." line per opened pick level."""
    return [opened.line for opened in new_picks(levels)]


def picks_opened_by_imbuing(
    sheet: CharacterSheet, thread: Thread, result: ThreadImbueResult
) -> list[int]:
    """The pick levels an imbue of a vow thread opened for its holder (#4929).

    A vow thread keys on the anchor role, so a sub-role holder's thread counts too.
    Nothing for any other kind of thread, an imbue that gained no level, or a
    character who no longer holds the vow as a primary vow.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415

    if thread.target_kind != TargetKind.COVENANT_ROLE or result.levels_gained <= 0:
        return []
    anchor_id = thread.target_covenant_role_id
    holds_it = CharacterCovenantRole.objects.filter(
        Q(covenant_role_id=anchor_id) | Q(covenant_role__parent_role_id=anchor_id),
        character_sheet=sheet,
        left_at__isnull=True,
        is_secondary=False,
    ).exists()
    if not holds_it:
        return []
    before = result.new_level - result.levels_gained
    return opened_pick_levels(before, result.new_level)


def announce_open_vow_picks(membership: CharacterCovenantRole) -> None:
    """Tell a character who just took up a vow which pick levels are already open.

    A rejoin, or a vow whose thread was woven before, starts above level 0; a fresh
    joiner has no vow thread yet, so they are told nothing here and hear of their
    first picks when imbuing opens them. Sent once the joining commits, so a join
    that a later step of the same rite rolls back tells them nothing.
    """
    if membership.is_secondary:
        return
    lines = new_picks_lines(opened_pick_levels(0, vow_level(membership)))
    if not lines:
        return
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheet = membership.character_sheet
    transaction.on_commit(
        lambda: send_narrative_message(
            recipients=[sheet], body="\n".join(lines), category=NarrativeCategory.COVENANT
        )
    )


# ---------------------------------------------------------------------------
# The Rite of Re-swearing: changing a chosen pick (#4940, slice 7 of #4844)

#: The SERVICE ritual staff author for the rite carries this path; it is found by it.
RESWEAR_SERVICE_PATH = "world.covenants.focus_picks.reswear_vow_pick"

IN_A_FIGHT_MESSAGE = "You cannot re-swear a vow pick during a fight."
NAME_THE_OLD_PICK_MESSAGE = "Name the chosen pick to give up."
NAME_THE_NEW_PICK_MESSAGE = "Name the pick to take instead."
NOT_CHOSEN_MESSAGE = "You have not chosen that pick."
NO_SUCH_PICK_MESSAGE = "Your vow offers no such pick."
SECONDARY_VOW_MESSAGE = "This is a secondary vow, and a secondary vow gets no focus picks."
NO_RESWEAR_RITE_MESSAGE = "No ritual can change a chosen vow pick yet."


@dataclass(frozen=True)
class _Swap:
    """A swap the rite may make, as ``check_reswear`` found it. Nothing written yet."""

    membership: CharacterCovenantRole
    old_choice: CharacterVowFocusPick
    new_pick: VowFocusPick
    budget: int
    ap_cost: int
    ap_pool: ActionPointPool


def reswear_ritual() -> Ritual | None:
    """The authored SERVICE ritual that changes a chosen pick, or None while there is none.

    The lowest pk when staff have made more than one (Required content lists the rest).
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models import Ritual  # noqa: PLC0415

    return (
        Ritual.objects.filter(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path=RESWEAR_SERVICE_PATH,
        )
        .order_by("pk")
        .first()
    )


def _pick_id(raw: object) -> int | None:
    """An id kwarg as an int: a JSON number from the web, a typed number from telnet."""
    if isinstance(raw, bool) or not isinstance(raw, int | str):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def in_a_fight(sheet: CharacterSheet) -> bool:
    """True while the character is an active fighter in a combat encounter or a battle."""
    from world.battles.round_context import resolve_battle_round_context  # noqa: PLC0415
    from world.combat.round_context import resolve_combat_round_context  # noqa: PLC0415

    return (
        resolve_combat_round_context(sheet) is not None
        or resolve_battle_round_context(sheet) is not None
    )


def _chosen_old_pick(
    sheet: CharacterSheet, old_pick_id: int, covenant_id: int | None
) -> CharacterVowFocusPick:
    """The caller's own choice of the pick to give up, on whichever vow holds it."""
    choices = CharacterVowFocusPick.objects.filter(
        character_role__character_sheet=sheet, pick_id=old_pick_id
    ).select_related("pick", "character_role__covenant", "character_role__covenant_role")
    if covenant_id is not None:
        choices = choices.filter(character_role__covenant_id=covenant_id)
    found = list(choices)
    if not found:
        raise VowFocusPickRefusedError(NOT_CHOSEN_MESSAGE)
    if len(found) > 1:
        names = sorted(choice.character_role.covenant.name for choice in found)
        msg = f"Which covenant? You chose it in: {', '.join(names)}."
        raise VowFocusPickRefusedError(msg)
    return found[0]


def _pick_to_take(
    membership: CharacterCovenantRole, old: VowFocusPick, new_pick_id: int
) -> VowFocusPick:
    """The pick to take instead: offered by the vow, not yet chosen, at ``old``'s level."""
    new = VowFocusPick.objects.filter(
        pk=new_pick_id, covenant_role_id__in=choosable_role_ids(membership)
    ).first()
    if new is None:
        raise VowFocusPickRefusedError(NO_SUCH_PICK_MESSAGE)
    if CharacterVowFocusPick.objects.filter(character_role=membership, pick=new).exists():
        msg = f"You have already chosen {new.name}."
        raise VowFocusPickRefusedError(msg)
    if new.pick_level != old.pick_level:
        msg = (
            f"{new.name} is a level {new.pick_level} pick and {old.name} is level "
            f"{old.pick_level}; a pick changes only for one of the same level."
        )
        raise VowFocusPickRefusedError(msg)
    return new


def check_reswear(
    character_sheet: CharacterSheet,
    *,
    old_pick_id: object = None,
    new_pick_id: object = None,
    covenant_id: object = None,
) -> _Swap:
    """Refuse a swap the Rite of Re-swearing cannot make; return the swap. Writes nothing.

    ``PerformRitualAction`` calls this before it spends the rite's components and anima;
    ``reswear_vow_pick`` calls it again under the membership's lock. In order it refuses:
    a character in a fight; no pick named to give up or to take; a pick to give up the
    caller has not chosen; a vow they have left or a secondary vow; a pick their vow does
    not offer; one already chosen; one of another level; a swap that leaves the level
    over its budget; and too few action points for ``respec_ap_cost``.

    Raises:
        VowFocusPickRefusedError: naming the rule the swap breaks.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    if in_a_fight(character_sheet):
        raise VowFocusPickRefusedError(IN_A_FIGHT_MESSAGE)
    old_id = _pick_id(old_pick_id)
    if old_id is None:
        raise VowFocusPickRefusedError(NAME_THE_OLD_PICK_MESSAGE)
    new_id = _pick_id(new_pick_id)
    if new_id is None:
        raise VowFocusPickRefusedError(NAME_THE_NEW_PICK_MESSAGE)
    old_choice = _chosen_old_pick(character_sheet, old_id, _pick_id(covenant_id))
    membership = old_choice.character_role
    old = old_choice.pick
    if membership.left_at is not None:
        raise VowFocusPickRefusedError(NO_LONGER_HELD_MESSAGE)
    if membership.is_secondary:
        raise VowFocusPickRefusedError(SECONDARY_VOW_MESSAGE)
    new = _pick_to_take(membership, old, new_id)
    config = vow_focus_pick_config()
    left = config.budget_per_level - spent_at_level(membership, old.pick_level) + pick_price(old)
    price = pick_price(new)
    if price > left:
        msg = (
            f"{new.name} costs {price}; giving up {old.name} leaves {left} of the "
            f"{config.budget_per_level} points for level {old.pick_level} picks."
        )
        raise VowFocusPickRefusedError(msg)
    ap_cost = config.respec_ap_cost
    pool = ActionPointPool.get_or_create_for_character(character_sheet.character)
    if pool is None or not pool.can_afford(ap_cost):
        have = pool.current if pool is not None else 0
        msg = f"The rite takes {ap_cost} action points, and you have {have}."
        raise VowFocusPickRefusedError(msg)
    return _Swap(
        membership=membership,
        old_choice=old_choice,
        new_pick=new,
        budget=config.budget_per_level,
        ap_cost=ap_cost,
        ap_pool=pool,
    )


@transaction.atomic
def reswear_vow_pick(
    character_sheet: CharacterSheet,
    *,
    old_pick_id: object = None,
    new_pick_id: object = None,
    covenant_id: object = None,
    **_ritual_dispatch_kwargs: object,  # ritual dispatch also forwards ``ritual=``
) -> ReswearResult:
    """Swap one chosen pick for another of the same level, for the rite's action points.

    The SERVICE function of the Rite of Re-swearing (#4940). Locks the membership row,
    checks the swap again under the lock (``check_reswear``), deletes the given-up
    choice, runs the admin's own rules on the new one (``validate_character_focus_pick``)
    and saves it, then spends ``respec_ap_cost`` from the weekly pool. One transaction:
    a refusal at any step leaves the picks and the pool as they were. The rite's anima
    and components are spent by ``PerformRitualAction`` around this.

    Raises:
        VowFocusPickRefusedError: naming the rule the swap breaks.
    """
    ids = {"old_pick_id": old_pick_id, "new_pick_id": new_pick_id, "covenant_id": covenant_id}
    swap = check_reswear(character_sheet, **ids)
    if not _lock_held(swap.membership):
        raise VowFocusPickRefusedError(NO_LONGER_HELD_MESSAGE)
    # Again under the lock: a swap or a choice sent at the same moment may have landed.
    swap = check_reswear(character_sheet, **ids)
    old = swap.old_choice.pick
    swap.old_choice.delete()
    choice = CharacterVowFocusPick(character_role=swap.membership, pick=swap.new_pick)
    try:
        validate_character_focus_pick(choice)
    except ValidationError as exc:
        raise VowFocusPickRefusedError(_refusal_text(exc)) from exc
    choice.save()
    if not swap.ap_pool.spend(swap.ap_cost):
        msg = f"The rite takes {swap.ap_cost} action points, and you have {swap.ap_pool.current}."
        raise VowFocusPickRefusedError(msg)
    level = old.pick_level
    spent = spent_at_level(swap.membership, level)
    return ReswearResult(
        membership_id=swap.membership.pk,
        old_pick_id=old.pk,
        new_pick_id=swap.new_pick.pk,
        level=level,
        spent=spent,
        budget=swap.budget,
        ap_spent=swap.ap_cost,
        message=(
            f"You give up {old.name} and take {swap.new_pick.name}. Level {level}: "
            f"{spent} of {swap.budget}. {swap.ap_cost} AP spent."
        ),
    )


def _requirement_label(requirement: RitualComponentRequirement) -> str:
    """One component the rite asks for, as the dialog's Cost line names it."""
    if requirement.item_template_id is not None:
        name = requirement.item_template.name
    elif requirement.min_touchstone_tier_id is not None:
        name = f"an attuned touchstone of {requirement.min_touchstone_tier.name}"
    else:
        name = "an offering"
    return name if requirement.quantity == 1 else f"{name} x{requirement.quantity}"


def reswear_options(sheet: CharacterSheet) -> ReswearOptions:
    """The rite, its costs, and the carried items that pay it, for the sheet's dialog.

    Read-only: the AP pool is not created, nothing is spent. ``component_ids`` are what
    ``resolve_ritual_components`` picks from the character's carried items, the way
    telnet offers everything carried; empty when they do not cover the rite.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        HedgeInaccessibleError,
        RitualComponentError,
    )
    from world.magic.services.ritual_components import (  # noqa: PLC0415
        resolve_ritual_components,
    )
    from world.magic.services.ritual_pool import ritual_visible_to  # noqa: PLC0415

    config = VowFocusPickConfig.objects.cached_singleton() or VowFocusPickConfig()
    ritual = reswear_ritual()
    # The perform's own visibility rule: a rite the character cannot perform is not offered.
    reason = ""
    if ritual is None:
        reason = NO_RESWEAR_RITE_MESSAGE
    elif not ritual_visible_to(sheet, ritual):
        reason = HedgeInaccessibleError.user_message
    if ritual is None or reason:
        return ReswearOptions(
            ritual_id=None,
            ap_cost=config.respec_ap_cost,
            anima_cost=0,
            components=[],
            component_ids=[],
            unavailable_reason=reason,
        )
    requirements = list(
        ritual.requirements.select_related("item_template", "min_touchstone_tier").order_by("pk")
    )
    component_ids: list[int] = []
    if requirements:
        carried = list(
            ItemInstance.objects.filter(
                holder_character_sheet=sheet, destroyed_at__isnull=True
            ).select_related("template__resonance_tier")
        )
        try:
            allocations = resolve_ritual_components(
                ritual=ritual, components=carried, performer_sheet=sheet
            )
        except RitualComponentError:
            allocations = []
        component_ids = list(dict.fromkeys(item.pk for item, _ in allocations))
    return ReswearOptions(
        ritual_id=ritual.pk,
        ap_cost=config.respec_ap_cost,
        anima_cost=ritual.anima_requirement,
        components=[_requirement_label(requirement) for requirement in requirements],
        component_ids=component_ids,
        unavailable_reason="",
    )
