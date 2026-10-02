"""A character's own name, look and price for a technique they hold (#4099, ADR-4099).

Personalization lives on the hold (``CharacterTechnique``), never on the shared
catalog row. Names are display only: every lookup keeps reading ``Technique.name``.
All reads go through the cached ``character.techniques`` handler.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING
import unicodedata

from django.db import transaction

from core.identifier_dashes import contains_dash
from world.magic.constants import (
    CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH,
    CUSTOM_TECHNIQUE_NAME_MAX_LENGTH,
)
from world.magic.exceptions import InvalidPersonalText
from world.magic.types.personalization import PricePayment
from world.magic.types.technique_effects import PriceComponentPayload

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import (
        CharacterTechnique,
        MotifResonance,
        PriceComponentRequirement,
        Resonance,
        Restriction,
        Technique,
    )

_MARKUP_CHARACTER = "|"


def _has_control_character(value: str, *, allow_newline: bool) -> bool:
    return any(
        # "Cc" is stdlib unicodedata's own category code, not an app identifier.
        unicodedata.category(ch) == "Cc"  # noqa: STRING_LITERAL
        and not (allow_newline and ch == "\n")
        for ch in value
    )


def clean_custom_technique_name(value: str) -> str:
    """Normalize a player's own technique name; ``""`` means use the catalog name."""
    cleaned = " ".join(value.split())
    if len(cleaned) > CUSTOM_TECHNIQUE_NAME_MAX_LENGTH:
        msg = f"A technique's name is at most {CUSTOM_TECHNIQUE_NAME_MAX_LENGTH} characters."
        raise InvalidPersonalText(msg)
    if contains_dash(cleaned):
        msg = "Use a plain hyphen in a technique's name, not a long dash."
        raise InvalidPersonalText(msg)
    if _MARKUP_CHARACTER in cleaned or _has_control_character(cleaned, allow_newline=False):
        msg = "A technique's name cannot contain '|' or control characters."
        raise InvalidPersonalText(msg)
    return cleaned


def clean_custom_technique_description(value: str) -> str:
    """Normalize a player's own technique description; ``""`` means the catalog's."""
    cleaned = value.strip()
    if len(cleaned) > CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH:
        msg = (
            "A technique's description is at most "
            f"{CUSTOM_TECHNIQUE_DESCRIPTION_MAX_LENGTH} characters."
        )
        raise InvalidPersonalText(msg)
    if _has_control_character(cleaned, allow_newline=True):
        msg = "A technique's description cannot contain control characters."
        raise InvalidPersonalText(msg)
    return cleaned


def hold_display_name(hold: CharacterTechnique | None, *, fallback: str) -> str:
    """The owner's name for a hold, else ``fallback`` (a variant name or the catalog name).

    Delegates to ``CharacterTechnique.display_name`` — the single implementation of
    "custom name, else the catalog's" — rather than re-deriving it here.
    """
    if hold is not None:
        return hold.display_name
    return fallback


def technique_display_name(character, technique: Technique, *, fallback: str | None = None) -> str:
    """What ``character`` calls ``technique``: their own name, else ``fallback``, else catalog."""
    hold = character.techniques.hold_for(technique)
    return hold_display_name(hold, fallback=fallback if fallback is not None else technique.name)


def technique_price_for(character, technique: Technique) -> Restriction | None:
    """The PRICE the character pays to cast ``technique``, or ``None``.

    Checks the row's CURRENT ``kind`` fresh, not just that the hold's FK is set:
    staff may re-author a ``Restriction`` row from PRICE to DESIGN after a
    character already bought it, and a stale hold must stop granting power the
    moment that happens (#4099 final fix) — never re-derived from whatever
    ``kind`` the row carried when the hold was created.
    """
    from world.magic.constants import RestrictionKind  # noqa: PLC0415

    hold = character.techniques.hold_for(technique)
    if hold is None or hold.price_id is None:
        return None
    return hold.price if hold.price.kind == RestrictionKind.PRICE else None


def price_components_by_price(
    price_ids: Iterable[int],
) -> dict[int, list[PriceComponentRequirement]]:
    """Each price's consumed components, keyed by price pk. One query; none for no ids.

    Read from the requirement table directly rather than through a cached accessor on
    the idmapper-shared ``Restriction``, so a staff edit to a price's components is
    seen on the next read (the same reason ``_allowed_effect_type_ids_by_price`` reads
    its through table).
    """
    from world.magic.models import PriceComponentRequirement  # noqa: PLC0415

    ids = set(price_ids)
    if not ids:
        return {}
    rows = (
        PriceComponentRequirement.objects.filter(restriction_id__in=ids)
        .select_related("item_template", "min_quality_tier")
        .order_by("pk")
    )
    result: dict[int, list[PriceComponentRequirement]] = {}
    for row in rows:
        result.setdefault(row.restriction_id, []).append(row)
    return result


def price_consumes_payload(
    components: Iterable[PriceComponentRequirement],
) -> list[PriceComponentPayload]:
    """What a price consumes per paid cast, for display. Authored template names only."""
    return [
        PriceComponentPayload(name=c.item_template.name, quantity=c.quantity) for c in components
    ]


def price_inflicts_name(price: Restriction) -> str | None:
    """The authored name of the condition a paid cast inflicts, or ``None``."""
    if price.inflicted_condition_id is None:
        return None
    return price.inflicted_condition.name


def price_paid_for_cast(character, technique: Technique) -> PricePayment | None:
    """THE decision: does this cast pay the caster's price? (#4099, ADR-4099).

    The only place it is made. A price with no consumed component always pays. A
    price with components pays only when the caster carries every one of them
    (matched by the same ``gather_consumable_pks`` rituals and crafting use); the
    allocation it finds is carried on the result, so the consumption at resolution
    spends exactly what this decision counted. Without the components the cast still
    happens, just without the price: no power, no clause, no condition, nothing
    spent. A player never loses a technique by running out of a component.
    """
    from world.items.exceptions import InsufficientMaterials  # noqa: PLC0415
    from world.items.services.materials import gather_consumable_pks  # noqa: PLC0415

    price = technique_price_for(character, technique)
    if price is None:
        return None
    requirements = price_components_by_price([price.pk]).get(price.pk, [])
    if not requirements:
        return PricePayment(price=price)
    try:
        allocations = gather_consumable_pks(
            available=character.carried_items.all(), requirements=requirements
        )
    except InsufficientMaterials:
        return None
    return PricePayment(price=price, allocations=tuple(allocations))


def confirm_price_payment(character, payment: PricePayment | None) -> PricePayment | None:
    """Re-lock and re-check a paid decision's allocation at settlement (#4099 review).

    ``price_paid_for_cast`` decides early (power is derived from it), but the cast resolves
    later. If another cast by the same character spent the component in between, the
    allocation is stale. This locks the allocated rows (``select_for_update``) and reads
    their stored values (never the identity-mapped instances, which can be stale). Each
    row must still be in play, still carried by the caster, and hold enough. On success
    the cached instances are synced to the locked quantity and the payment is returned.
    Otherwise this returns ``None`` and the cast settles unpaid without raising. The caller
    withdraws the price's power from the cast. Must run inside the settlement's
    transaction so the lock holds through consumption.
    """
    from world.items.models import ItemInstance  # noqa: PLC0415

    if payment is None or not payment.allocations:
        return payment
    pks = [instance.pk for instance, _ in payment.allocations]
    if any(pk is None for pk in pks):
        return None
    locked = {
        pk: (quantity, destroyed_at, location_id)
        for pk, quantity, destroyed_at, location_id in ItemInstance.objects.select_for_update(
            of=("self",)
        )
        .filter(pk__in=pks)
        .values_list("pk", "quantity", "destroyed_at", "game_object__db_location_id")
    }
    for instance, amount in payment.allocations:
        row = locked.get(instance.pk)
        if row is None:
            return None
        quantity, destroyed_at, location_id = row
        if destroyed_at is not None or location_id != character.pk or quantity < amount:
            return None
    for instance, _ in payment.allocations:
        instance.quantity = locked[instance.pk][0]
    return payment


def settle_price_payment(*, character, technique: Technique, payment: PricePayment | None) -> None:
    """Spend what a paid price costs, once the cast has resolved (#4099).

    Consumes the decision's allocated components through the shared
    ``consume_materials`` and applies the price's inflicted condition to the caster
    through ``apply_condition``. A no-op for an unpaid cast. Called only from inside
    ``use_technique``'s resolution savepoint, after ``confirm_price_payment`` has
    re-locked the allocation, and never before the cast resolves.
    """
    if payment is None:
        return
    from world.conditions.services import apply_condition  # noqa: PLC0415
    from world.items.services.materials import consume_materials  # noqa: PLC0415

    with transaction.atomic():
        if payment.allocations:
            consume_materials(list(payment.allocations))
            character.carried_items.invalidate()
        price = payment.price
        if price.inflicted_condition_id is not None:
            apply_condition(
                character,
                price.inflicted_condition,
                source_character=character,
                source_technique=technique,
                source_description=price.name,
            )


def paid_price_snippet(price: Restriction | None) -> str | None:
    """The cast-narration clause for a PAID price: authored line, else its name.

    Takes the price the cast actually paid (``TechniqueUseResult.price_paid``), never
    the hold's price, so an unpaid cast never narrates a cost it did not pay.
    """
    if price is None:
        return None
    return price.cast_narration or price.name


def seed_motif_from_gift_resonance(sheet: CharacterSheet, resonance: Resonance) -> MotifResonance:
    """Ensure ``sheet``'s Motif carries ``resonance`` as a gift resonance (idempotent).

    ``MotifResonance.is_from_gift`` documents that gift resonances are auto-populated,
    but nothing did it; without a Motif no ``SignatureMotifBonus`` ever qualifies
    (``SignatureMotifBonus.qualifies_for``). Called at CG finalize (#4099).
    """
    from world.magic.models import Motif, MotifResonance  # noqa: PLC0415

    with transaction.atomic():
        motif, _ = Motif.objects.get_or_create(character=sheet)
        motif_resonance, _ = MotifResonance.objects.get_or_create(
            motif=motif, resonance=resonance, defaults={"is_from_gift": True}
        )
    return motif_resonance
