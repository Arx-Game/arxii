"""Shared ritual-component validate/consume helper (#707).

Used by BOTH ``PerformRitualAction`` (the generic ritual-performance seam)
and ``SanctumInstallAction`` (Ritual of Sanctification's own bespoke seam —
verified it does NOT route through ``PerformRitualAction``, so this logic
must be callable independently of that action, not buried inside it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.exceptions import InsufficientMaterials
from world.items.services.materials import consume_pks, gather_consumable_pks
from world.magic.exceptions import RitualComponentError

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Resonance, Ritual


def _resolve_touchstone_pks(
    *,
    available: list[ItemInstance],
    requirements: list[object],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None,
    already_allocated: set[int],
) -> list[int]:
    """Resolve touchstone-mode requirements against ``available``.

    An instance satisfies a requirement when: it's attuned to
    ``performer_sheet``, its template's ``resonance_tier`` meets the
    requirement's ``min_touchstone_tier``, and its template's
    ``tied_resonance`` matches either ``resonance_context`` (when given) or
    any ``CharacterResonance`` the performer holds (the general case).

    Raises:
        RitualComponentError: On the first unsatisfied requirement.
    """
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    matched_pks: list[int] = []
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
            and inst.pk not in matched_pks
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
        matched_pks.append(candidates[0].pk)

    return matched_pks


def resolve_and_consume_ritual_components(
    *,
    ritual: Ritual,
    components: list[ItemInstance],
    performer_sheet: CharacterSheet,
    resonance_context: Resonance | None = None,
) -> None:
    """Validate and atomically consume ``ritual``'s components from ``components``.

    Partitions ``ritual.requirements.all()`` into template-mode
    (``item_template_id is not None``) and touchstone-mode
    (``min_touchstone_tier_id is not None``) rows. Template-mode rows use the
    existing ``gather_consumable_pks``; touchstone-mode rows resolve via
    ``_resolve_touchstone_pks``. All-or-nothing: raises before consuming
    anything if EITHER set of requirements is unsatisfied.

    Args:
        ritual: The Ritual whose requirements to check.
        components: ItemInstance rows the performer is contributing.
        performer_sheet: The performing character's CharacterSheet.
        resonance_context: When given, touchstone-mode requirements must match
            THIS Resonance specifically (e.g. Sanctification's chosen founding
            resonance), not just any Resonance the performer holds.

    Raises:
        RitualComponentError: If any requirement is unsatisfied. Nothing is
            consumed when this is raised.
    """
    requirements = list(
        ritual.requirements.select_related(
            "item_template", "min_quality_tier", "min_touchstone_tier"
        )
    )
    template_reqs = [r for r in requirements if r.item_template_id is not None]
    touchstone_reqs = [r for r in requirements if r.min_touchstone_tier_id is not None]

    try:
        template_pks = gather_consumable_pks(available=components, requirements=template_reqs)
    except InsufficientMaterials as exc:
        req = exc.requirement
        component_exc = RitualComponentError()
        component_exc.user_message = (
            f"Ritual '{ritual.name}' requires {req.quantity}x "
            f"'{req.item_template}' but only {exc.provided_qty} provided."
        )
        raise component_exc from exc

    touchstone_pks = _resolve_touchstone_pks(
        available=components,
        requirements=touchstone_reqs,
        performer_sheet=performer_sheet,
        resonance_context=resonance_context,
        already_allocated=set(template_pks),
    )

    consume_pks(list({*template_pks, *touchstone_pks}))
