"""Vow focus pick prices and the rules a character's choice must pass (#4759).

A focus pick (``VowFocusPick``) is an option a vow holder chooses at pick level
1, 2 or 3. Its price is worked out from its ``value`` and its limits, never
stored; a character's chosen picks at one level must fit the budget on
``VowFocusPickConfig``. ``CharacterVowFocusPick.clean()`` calls
``validate_character_focus_pick`` so the admin refuses a choice that breaks a
rule, with the reason.

In play (slice 2), a payload row (``VowAddedEffect``, ``VowSituationalPerk``,
``VowStatScaling``) whose ``focus_pick`` is set fires only for a
holder who chose that pick; ``chosen_pick_ids_by_holder`` answers "which picks
has each holder chosen" for every reader in one query, and
``holder_has_pick`` is the gate each reader applies per row.
"""

from __future__ import annotations

from collections.abc import Iterable
from math import prod
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.covenants.constants import (
    FOCUS_PICK_FREQUENCY_LIMIT_KINDS,
    FOCUS_PICK_LIMIT_FREQUENCY_FULL,
    FOCUS_PICK_REDUCTION_LIMIT_KINDS,
)
from world.covenants.models import CharacterVowFocusPick, VowFocusPickConfig

if TYPE_CHECKING:
    from world.covenants.models import CharacterCovenantRole, VowFocusPick

#: The lowest price any pick can cost, however many limits it carries.
MIN_PICK_PRICE = 1


def vow_focus_pick_config() -> VowFocusPickConfig:
    """Return the VowFocusPickConfig singleton (pk=1), creating it with defaults."""
    config = VowFocusPickConfig.objects.cached_singleton()
    if config is None:
        config, _ = VowFocusPickConfig.objects.get_or_create(pk=1)
    return config


def pick_price(pick: VowFocusPick) -> int:
    """The price of a focus pick, worked out from its value and limits (#4759).

    ``max(1, floor(value x product(frequency_tenths / 10)) - sum(reduction))``. The
    frequency product runs over SELF, TARGET, SETTING and TIMING limits; the
    reductions over EXPOSURE and COST limits. Integer arithmetic throughout, so
    value 4 with one limit at frequency 5 is exactly 2.
    """
    limits = pick.cached_limits
    frequencies = [
        limit.frequency_tenths for limit in limits if limit.kind in FOCUS_PICK_FREQUENCY_LIMIT_KINDS
    ]
    reductions = sum(
        limit.reduction for limit in limits if limit.kind in FOCUS_PICK_REDUCTION_LIMIT_KINDS
    )
    scaled = pick.value * prod(frequencies) // FOCUS_PICK_LIMIT_FREQUENCY_FULL ** len(frequencies)
    return max(MIN_PICK_PRICE, scaled - reductions)


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


def shown_vow_level(membership: CharacterCovenantRole) -> int:
    """The shown COVENANT_ROLE thread level behind a membership (#4759).

    Threads key on the anchor role, so a sub-role membership reads its parent's
    thread. Shown scale: a thread stored at 20 shows 2.
    """
    from world.covenants.services import _covenant_role_thread_level  # noqa: PLC0415
    from world.magic.services.threads import shown_thread_level  # noqa: PLC0415

    role = membership.covenant_role
    anchor = role.parent_role if role.parent_role_id is not None else role
    return shown_thread_level(_covenant_role_thread_level(membership.character_sheet, anchor))


def _choosable_role_ids(membership: CharacterCovenantRole) -> set[int]:
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
    the pick's level is no higher than the shown vow level; and the prices of the
    membership's picks at that level fit ``VowFocusPickConfig.budget_per_level``.
    """
    membership = choice.character_role
    pick = choice.pick
    if membership.is_secondary:
        raise ValidationError(
            {"character_role": "This is a secondary vow, and a secondary vow gets no focus picks."}
        )
    if pick.covenant_role_id not in _choosable_role_ids(membership):
        raise ValidationError(
            {
                "pick": (
                    f"'{pick.name}' is a pick of {pick.covenant_role.name}, which is not "
                    f"this character's vow ({membership.covenant_role.name})."
                )
            }
        )
    level = shown_vow_level(membership)
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
