"""Character creation's "make it yours" picks for a chosen technique (#4099, ADR-4099).

Offers, validates, prices and applies three catalog picks (a flourish, an early form,
a price) plus the player's own name and description. A null ``creation_point_cost``
means a row is not offered in creation. Everything is keyed by technique id; entries
for techniques the draft no longer selects are ignored.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

from world.magic.constants import CREATION_PERSONALIZATION_MAX_LEVEL, RestrictionKind
from world.magic.types.personalization import (
    PersonalizationOptionSet,
    PricedPersonalizationLine,
    TechniquePersonalizationPick,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Resonance, Restriction, SignatureMotifBonus, Technique
    from world.magic.specialization.models import TechniqueVariant

_PICK_INT_FIELDS = ("signature_bonus_id", "early_form_id", "price_id")
_PICK_TEXT_FIELDS = ("custom_name", "custom_description")


def parse_personalization_picks(
    raw: object, *, technique_ids: Iterable[int]
) -> list[TechniquePersonalizationPick]:
    """Read already-validated draft data; drops entries for unselected techniques."""
    if not isinstance(raw, dict):
        return []
    selected = set(technique_ids)
    picks: list[TechniquePersonalizationPick] = []
    for key, entry in raw.items():
        try:
            technique_id = int(key)
        except (TypeError, ValueError):
            # A key the serializer's own shape check would have rejected (e.g. a
            # non-decimal digit character `int()` can't parse) — skip rather than
            # crash every later read of this draft (#4099 fix round 1).
            continue
        if technique_id not in selected or not isinstance(entry, dict):
            continue
        picks.append(
            TechniquePersonalizationPick(
                technique_id=technique_id,
                **{name: entry.get(name) or "" for name in _PICK_TEXT_FIELDS},
                **{name: entry.get(name) for name in _PICK_INT_FIELDS},
            )
        )
    return picks


def _offered_flourishes(resonance_id: int | None) -> list[SignatureMotifBonus]:
    from world.magic.models import SignatureMotifBonus  # noqa: PLC0415

    if resonance_id is None:
        return []
    return list(
        SignatureMotifBonus.objects.filter(
            creation_point_cost__isnull=False,
            required_facet__isnull=True,
            required_resonance_id=resonance_id,
            min_crossing_level__lte=CREATION_PERSONALIZATION_MAX_LEVEL,
        ).order_by("creation_point_cost", "name")
    )


def _offered_prices() -> list[Restriction]:
    from world.magic.models import Restriction  # noqa: PLC0415

    return list(
        Restriction.objects.filter(kind=RestrictionKind.PRICE, creation_point_cost__isnull=False)
        .select_related("inflicted_condition")
        .order_by("creation_point_cost", "name")
    )


def _allowed_effect_type_ids_by_price(prices: Sequence[Restriction]) -> dict[int, set[int]]:
    """One bulk query over the M2M through table; never a cached read off the row itself.

    ``Restriction`` is a ``SharedMemoryModel``, so any form of prefetch caching that
    writes onto the instance (a ``Prefetch`` targeting an attribute, or plain
    prefetch-related caching) shares that cache across every later read of the same
    row for the life of the process - the same bug class ``CharacterTechnique.clean()``
    deliberately avoids by querying fresh (#4099 Task 1 review). Reading the through
    table directly sidesteps instance caching entirely.
    """
    from world.magic.models import Restriction  # noqa: PLC0415

    through = Restriction.allowed_effect_types.through
    pairs = through.objects.filter(restriction_id__in=[p.pk for p in prices]).values_list(
        "restriction_id", "effecttype_id"
    )
    result: dict[int, set[int]] = {}
    for restriction_id, effect_type_id in pairs:
        result.setdefault(restriction_id, set()).add(effect_type_id)
    return result


def _price_fits(
    price: Restriction, allowed_by_price: Mapping[int, set[int]], technique: Technique
) -> bool:
    allowed = allowed_by_price.get(price.pk)
    return not allowed or technique.effect_type_id in allowed


def creation_personalization_options(
    techniques: Sequence[Technique], *, resonance_id: int | None
) -> list[PersonalizationOptionSet]:
    """What creation offers per technique. A fixed number of queries regardless of count.

    Excludes any ``is_ultimate`` technique (#4099 fix round 1): a draft PATCH can put an
    ultimate's pk in ``selected_technique_ids`` with no gate at write time, and an
    ultimate's identity/options must stay undiscovered until Audere reveals it (#4098) —
    offering it here would leak its name and catalog options through the CG panel. Every
    caller is covered by filtering here rather than at each call site.
    """
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    techniques = [t for t in techniques if not t.is_ultimate]
    flourishes = _offered_flourishes(resonance_id)
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        price_components_by_price,
    )

    prices = _offered_prices()
    allowed_by_price = _allowed_effect_type_ids_by_price(prices)
    # #4099: each price's real cost, so the picker shows what it consumes. One query.
    price_components = price_components_by_price(p.pk for p in prices)
    forms: list[TechniqueVariant] = []
    if resonance_id is not None:
        forms = list(
            TechniqueVariant.objects.filter(
                parent_technique_id__in=[t.pk for t in techniques],
                resonance_id=resonance_id,
                creation_point_cost__isnull=False,
            )
            .select_related("resonance")
            .order_by("unlock_thread_level", "pk")
        )
    return [
        PersonalizationOptionSet(
            technique=technique,
            flourishes=flourishes,
            forms=[f for f in forms if f.parent_technique_id == technique.pk],
            prices=[p for p in prices if _price_fits(p, allowed_by_price, technique)],
            price_components=price_components,
        )
        for technique in techniques
    ]


def _technique_anchor_cap(technique: Technique) -> int:
    """The anchor cap a TECHNIQUE thread on ``technique`` is bound by.

    Delegates to ``compute_anchor_cap`` — the same function ``weave_creation_
    technique_thread`` checks against at finalize — via a transient, unsaved
    ``Thread`` (the TECHNIQUE branch only reads ``target_technique.level``, so no
    owner/resonance is needed). Never re-derives the formula by hand.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415
    from world.magic.services.threads import compute_anchor_cap  # noqa: PLC0415

    thread = Thread(target_kind=TargetKind.TECHNIQUE, target_technique=technique)
    return compute_anchor_cap(thread)


def _flourish_pick_error(
    pick: TechniquePersonalizationPick, option: PersonalizationOptionSet
) -> str | None:
    """The one error for this pick's flourish choice, or ``None``."""
    if pick.signature_bonus_id is None:
        return None
    bonus = next((f for f in option.flourishes if f.pk == pick.signature_bonus_id), None)
    if bonus is None:
        return "A chosen signature flourish is no longer available."
    if bonus.min_crossing_level > _technique_anchor_cap(option.technique):
        # A level-0 technique has anchor cap 0 (#4099 final fix): the weave at
        # finalize would reject this pick with AnchorCapExceeded, so it must fail
        # here instead, using the same cap function the weave uses.
        return "A chosen signature flourish needs a deeper thread than this technique allows."
    return None


def personalization_pick_errors(
    picks: Sequence[TechniquePersonalizationPick],
    *,
    techniques: Sequence[Technique],
    resonance_id: int | None,
) -> list[str]:
    """Every pick must still be on offer for its technique at the draft's resonance."""
    options = {
        o.technique.pk: o
        for o in creation_personalization_options(techniques, resonance_id=resonance_id)
    }
    # Catalog names of every selected technique, keyed by id (#4099 final fix): a
    # custom name that equals ANOTHER selected technique's catalog name,
    # case-insensitively, would collide at cast time (telnet `cast <name>` fires
    # the wrong technique) and in the web key the Spellbook keys technique rows
    # by. Renaming a technique to its OWN catalog name is a no-op, not a
    # collision, so each pick's comparison excludes its own technique.
    catalog_names_by_id = {t.pk: t.name.casefold() for t in techniques}
    errors: list[str] = []
    names: set[str] = set()
    for pick in picks:
        option = options.get(pick.technique_id)
        if option is None:
            continue
        flourish_error = _flourish_pick_error(pick, option)
        if flourish_error is not None:
            errors.append(flourish_error)
        if pick.early_form_id is not None and pick.early_form_id not in {
            f.pk for f in option.forms
        }:
            errors.append("A chosen specialized form is no longer available.")
        if pick.price_id is not None and pick.price_id not in {p.pk for p in option.prices}:
            errors.append("A chosen price is no longer available.")
        if pick.custom_name:
            folded = pick.custom_name.casefold()
            other_catalog_names = {
                name
                for technique_id, name in catalog_names_by_id.items()
                if technique_id != pick.technique_id
            }
            if folded in names:
                errors.append("Give each technique its own name.")
            elif folded in other_catalog_names:
                errors.append("That name already belongs to a technique you know.")
            names.add(folded)
    return errors


def priced_personalization_lines(
    picks: Sequence[TechniquePersonalizationPick],
    *,
    techniques_by_id: Mapping[int, Technique],
) -> list[PricedPersonalizationLine]:
    """One CG-points line per priced pick, at each row's own cost. Three bulk lookups."""
    from world.magic.models import Restriction, SignatureMotifBonus  # noqa: PLC0415
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    picks = [p for p in picks if p.technique_id in techniques_by_id]
    bonuses = SignatureMotifBonus.objects.in_bulk(
        [p.signature_bonus_id for p in picks if p.signature_bonus_id]
    )
    forms = TechniqueVariant.objects.in_bulk([p.early_form_id for p in picks if p.early_form_id])
    prices = Restriction.objects.in_bulk([p.price_id for p in picks if p.price_id])
    lines: list[PricedPersonalizationLine] = []
    for pick in picks:
        technique_name = techniques_by_id[pick.technique_id].name
        bonus = bonuses.get(pick.signature_bonus_id)
        if bonus is not None and bonus.creation_point_cost is not None:
            lines.append(
                PricedPersonalizationLine(
                    technique_name=technique_name,
                    option_name=bonus.name or technique_name,
                    cost=bonus.creation_point_cost,
                )
            )
        form = forms.get(pick.early_form_id)
        if form is not None and form.creation_point_cost is not None:
            lines.append(
                PricedPersonalizationLine(
                    technique_name=technique_name,
                    option_name=form.name_override or technique_name,
                    cost=form.creation_point_cost,
                )
            )
        price = prices.get(pick.price_id)
        if price is not None and price.creation_point_cost is not None:
            lines.append(
                PricedPersonalizationLine(
                    technique_name=technique_name,
                    option_name=price.name or technique_name,
                    cost=price.creation_point_cost,
                )
            )
    return lines


def apply_creation_personalizations(
    sheet: CharacterSheet,
    picks: Sequence[TechniquePersonalizationPick],
    *,
    resonance: Resonance | None,
) -> None:
    """Write validated picks onto the new character's holds (CG finalize).

    The flourish weaves the TECHNIQUE thread at the flourish's own level and signs it;
    the Motif must already carry the gift resonance (``seed_motif_from_gift_resonance``).
    """
    from world.magic.models import (  # noqa: PLC0415
        CharacterTechnique,
        Restriction,
        SignatureMotifBonus,
    )
    from world.magic.services.signature import set_signature_bonus  # noqa: PLC0415
    from world.magic.services.threads import weave_creation_technique_thread  # noqa: PLC0415
    from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

    if not picks:
        return
    holds = {
        h.technique_id: h
        for h in CharacterTechnique.objects.filter(
            character=sheet, technique_id__in=[p.technique_id for p in picks]
        ).select_related("technique")
    }
    bonuses = SignatureMotifBonus.objects.in_bulk(
        [p.signature_bonus_id for p in picks if p.signature_bonus_id]
    )
    forms = TechniqueVariant.objects.in_bulk([p.early_form_id for p in picks if p.early_form_id])
    prices = Restriction.objects.in_bulk([p.price_id for p in picks if p.price_id])
    for pick in picks:
        hold = holds.get(pick.technique_id)
        if hold is None:
            continue
        hold.custom_name = pick.custom_name
        hold.custom_description = pick.custom_description
        hold.price = prices.get(pick.price_id)
        hold.early_form = forms.get(pick.early_form_id)
        hold.full_clean()
        hold.save(update_fields=["custom_name", "custom_description", "price", "early_form"])
        bonus = bonuses.get(pick.signature_bonus_id)
        if bonus is not None and resonance is not None:
            thread = weave_creation_technique_thread(
                sheet, hold.technique, resonance, level=bonus.min_crossing_level
            )
            set_signature_bonus(thread, bonus)
    sheet.character.techniques.invalidate()
