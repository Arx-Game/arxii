"""Shared ritual-component validate/consume helper (#707).

Used by BOTH ``PerformRitualAction`` (the generic ritual-performance seam)
and ``SanctumInstallAction`` (Ritual of Sanctification's own bespoke seam —
verified it does NOT route through ``PerformRitualAction``, so this logic
must be callable independently of that action, not buried inside it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.exceptions import InsufficientMaterials
from world.items.services.materials import consume_materials, gather_consumable_pks
from world.magic.exceptions import RitualComponentError
from world.magic.services.drift import qualifying_components

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Resonance, Ritual, RitualComponentRequirement


def _resolve_touchstone_pks(
    *,
    available: list[ItemInstance],
    requirements: list[object],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None,
    already_allocated: set[int],
) -> list[ItemInstance]:
    """Resolve touchstone-mode requirements against ``available``.

    An instance satisfies a requirement when: it's attuned to
    ``performer_sheet``, its template's ``resonance_tier`` meets the
    requirement's ``min_touchstone_tier``, and its template's
    ``tied_resonance`` matches either ``resonance_context`` (when given) or
    any ``CharacterResonance`` the performer holds (the general case).

    Returns:
        List of matched ``ItemInstance`` objects (one per requirement).

    Raises:
        RitualComponentError: On the first unsatisfied requirement.
    """
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    matched_instances: list[ItemInstance] = []
    claimed_resonance_ids = set(
        CharacterResonance.objects.filter(character_sheet=performer_sheet).values_list(
            "resonance_id", flat=True
        )
    )

    for req in requirements:
        candidates = [
            inst
            for inst in available
            if inst.pk not in already_allocated
            and inst.pk not in {i.pk for i in matched_instances}
            # #4099: a spent (soft-deleted) touchstone never satisfies a requirement again.
            and inst.destroyed_at is None
            and inst.quantity > 0
            and inst.attuned_to_character_sheet_id == performer_sheet.pk
            and inst.template.tied_resonance_id is not None
            and inst.template.resonance_tier_id is not None
            and inst.template.resonance_tier.tier_level >= req.min_touchstone_tier.tier_level
            and (
                inst.template.tied_resonance_id == resonance_context.pk
                if resonance_context is not None
                else inst.template.tied_resonance_id in claimed_resonance_ids
            )
        ]
        if not candidates:
            exc = RitualComponentError()
            exc.user_message = (
                f"Ritual '{req.ritual.name}' requires an attuned touchstone "
                f"(tier >= {req.min_touchstone_tier.name}) that you don't have."
            )
            raise exc
        matched_instances.append(candidates[0])

    return matched_instances


def _resolve_target_resonance_allocations(
    *,
    available: list[ItemInstance],
    requirements: list[RitualComponentRequirement],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None,
    already_allocated: set[int],
) -> list[tuple[ItemInstance, int]]:
    """Resolve target-resonance requirements against ``available`` (#4733).

    A requirement takes ``quantity`` units from the items that ``qualifying_components``
    admits for ``resonance_context`` (its three routes, with the requirement's own
    ``min_item_meaning`` bar). Units are counted the way template rows count them, so a
    stack of three can pay a quantity of three. An item already allocated to a template or
    touchstone row, or to an earlier target row, is not offered again.

    Returns:
        ``(item, amount)`` allocations for ``consume_materials``.

    Raises:
        RitualComponentError: With no ``resonance_context``, or on the first unsatisfied
            requirement.
    """
    if not requirements:
        return []
    if resonance_context is None:
        exc = RitualComponentError()
        exc.user_message = f"Ritual '{requirements[0].ritual.name}' needs a target resonance."
        raise exc

    taken: dict[int, int] = {}
    allocations: list[tuple[ItemInstance, int]] = []
    for req in requirements:
        offered = qualifying_components(
            performer_sheet,
            resonance_context,
            [inst for inst in available if inst.pk not in already_allocated],
            min_item_meaning=req.min_item_meaning,
        )
        needed = req.quantity
        for component in offered:
            if needed == 0:
                break
            item = component.item
            amount = min(item.quantity - taken.get(item.pk, 0), needed)
            if amount <= 0:
                continue
            taken[item.pk] = taken.get(item.pk, 0) + amount
            allocations.append((item, amount))
            needed -= amount
        if needed:
            exc = RitualComponentError()
            exc.user_message = (
                f"Ritual '{req.ritual.name}' requires {req.quantity}x offering "
                f"for {resonance_context.name} that you don't have."
            )
            raise exc
    return allocations


def _partition_requirements(
    ritual: Ritual, requirements: list[RitualComponentRequirement]
) -> tuple[
    list[RitualComponentRequirement],
    list[RitualComponentRequirement],
    list[RitualComponentRequirement],
]:
    """Split ``requirements`` into (template, touchstone, target-resonance) rows.

    The database allows exactly one mode per row. A row that matches none raises rather
    than being skipped, so a mode added later cannot be silently ignored here.
    """
    template_reqs: list[RitualComponentRequirement] = []
    touchstone_reqs: list[RitualComponentRequirement] = []
    target_reqs: list[RitualComponentRequirement] = []
    for req in requirements:
        if req.item_template_id is not None:
            template_reqs.append(req)
        elif req.min_touchstone_tier_id is not None:
            touchstone_reqs.append(req)
        elif req.matches_target_resonance:
            target_reqs.append(req)
        else:
            exc = RitualComponentError()
            exc.user_message = (
                f"Ritual '{ritual.name}' has a component requirement this system "
                "cannot check; tell staff."
            )
            raise exc
    return template_reqs, touchstone_reqs, target_reqs


def resolve_ritual_components(
    *,
    ritual: Ritual,
    components: list[ItemInstance],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None = None,
) -> list[tuple[ItemInstance, int]]:
    """Work out which of ``components`` pay ``ritual``'s requirements, writing nothing.

    Partitions ``ritual.requirements.all()`` into template-mode
    (``item_template_id is not None``), touchstone-mode
    (``min_touchstone_tier_id is not None``) and target-resonance-mode
    (``matches_target_resonance``) rows. Template-mode rows use the
    existing ``gather_consumable_pks``; touchstone-mode rows resolve via
    ``_resolve_touchstone_pks``; target-resonance rows via
    ``_resolve_target_resonance_allocations``.

    Args:
        ritual: The Ritual whose requirements to check.
        components: ItemInstance rows the performer is contributing.
        performer_sheet: The performing character's CharacterSheet.
        resonance_context: When given, touchstone-mode requirements must match
            THIS Resonance specifically (e.g. Sanctification's chosen founding
            resonance), not just any Resonance the performer holds. It is also the
            resonance a target-resonance-mode requirement is converting toward, and
            is required for such a requirement.

    Returns:
        ``(item, amount)`` allocations for ``consume_materials``. A touchstone is
        allocated an amount of 1.

    Raises:
        RitualComponentError: If any requirement is unsatisfied.
    """
    requirements = list(
        ritual.requirements.select_related(
            "item_template", "min_quality_tier", "min_touchstone_tier"
        )
    )
    template_reqs, touchstone_reqs, target_reqs = _partition_requirements(ritual, requirements)

    try:
        template_allocations = gather_consumable_pks(
            available=components, requirements=template_reqs
        )
    except InsufficientMaterials as exc:
        req = exc.requirement
        component_exc = RitualComponentError()
        component_exc.user_message = (
            f"Ritual '{ritual.name}' requires {req.quantity}x "
            f"'{req.item_template}' but only {exc.provided_qty} provided."
        )
        raise component_exc from exc

    touchstone_instances = _resolve_touchstone_pks(
        available=components,
        requirements=touchstone_reqs,
        performer_sheet=performer_sheet,
        resonance_context=resonance_context,
        already_allocated={inst.pk for inst, _ in template_allocations},
    )

    target_allocations = _resolve_target_resonance_allocations(
        available=components,
        requirements=target_reqs,
        performer_sheet=performer_sheet,
        resonance_context=resonance_context,
        already_allocated={
            *(inst.pk for inst, _ in template_allocations),
            *(inst.pk for inst in touchstone_instances),
        },
    )

    # Touchstones are non-stackable (quantity=1); consuming amount=1 decrements to 0 -> delete.
    return [
        *template_allocations,
        *((inst, 1) for inst in touchstone_instances),
        *target_allocations,
    ]


def resolve_and_consume_ritual_components(
    *,
    ritual: Ritual,
    components: list[ItemInstance],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None = None,
) -> None:
    """Validate and atomically consume ``ritual``'s components from ``components``.

    ``resolve_ritual_components`` then ``consume_materials``. All-or-nothing: raises
    before consuming anything if ANY set of requirements is unsatisfied. A caller with a
    raising step between choosing the offering and spending it (a roll) calls the two
    halves itself, so nothing is spent before that step can refuse.

    Raises:
        RitualComponentError: If any requirement is unsatisfied. Nothing is
            consumed when this is raised.
    """
    consume_materials(
        resolve_ritual_components(
            ritual=ritual,
            components=components,
            performer_sheet=performer_sheet,
            resonance_context=resonance_context,
        )
    )
