"""Staff edit mode's distinction writes (#4221, #3988 piece B).

Staff building or repairing a sheet add, re-rank and remove distinctions with no
XP and no ``SheetUpdateRequest``. Structural rules hold: mutual and variant
exclusions, a per-feature distinction aimed at exactly one feature, and the rank
range. An addition also carries what CG's grant carries: the default Secret for a
secret-by-default distinction, its codex grants, and the Glimpse link when the
character has a Glimpse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.character_creation.sheet_writers import SheetWriteError, grant_distinction_codex
from world.distinctions.types import DistinctionOrigin

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import CharacterDistinction, Distinction
    from world.forms.models import FormMarking, FormTrait


def staff_add_distinction(
    sheet: CharacterSheet,
    distinction: Distinction,
    *,
    rank: int = 1,
    feature_trait: FormTrait | None = None,
    feature_marking: FormMarking | None = None,
) -> CharacterDistinction:
    """Add a distinction at ``rank`` through ``grant_distinction`` (origin STAFF)."""
    from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
    from world.distinctions.services import (  # noqa: PLC0415
        grant_distinction,
        mint_distinction_secret,
    )
    from world.magic.models import CharacterAura  # noqa: PLC0415
    from world.magic.services.glimpse import link_distinction_to_glimpse  # noqa: PLC0415

    features = int(feature_trait is not None) + int(feature_marking is not None)
    if distinction.taken_per_feature and features != 1:
        msg = f"{distinction.name} is taken for one feature: name the trait or the marking."
        raise SheetWriteError(msg)
    if not distinction.taken_per_feature and features:
        msg = f"{distinction.name} is not taken per feature."
        raise SheetWriteError(msg)
    if not 1 <= rank <= distinction.max_rank:
        msg = f"{distinction.name} ranks from 1 to {distinction.max_rank}."
        raise SheetWriteError(msg)
    try:
        with transaction.atomic():
            held = grant_distinction(
                sheet,
                distinction,
                origin=DistinctionOrigin.STAFF,
                rank=rank,
                feature_trait=feature_trait,
                feature_marking=feature_marking,
            )
            if distinction.secret_by_default:
                mint_distinction_secret(held)
            grant_distinction_codex(sheet, [distinction])
            aura = CharacterAura.objects.filter(character=sheet).first()
            if aura is not None and aura.glimpse_story:
                link_distinction_to_glimpse(held, aura)
    except DistinctionExclusionError as exc:
        raise SheetWriteError(str(exc.user_message)) from exc
    return held


def staff_set_distinction_rank(held: CharacterDistinction, rank: int) -> None:
    """Set a held distinction's rank, up or down, recalculating its modifiers. No XP."""
    from world.mechanics.services import update_distinction_rank  # noqa: PLC0415

    if not 1 <= rank <= held.distinction.max_rank:
        msg = f"{held.distinction.name} ranks from 1 to {held.distinction.max_rank}."
        raise SheetWriteError(msg)
    if rank == held.rank:
        return
    with transaction.atomic():
        held.rank = rank
        held.save(update_fields=["rank", "updated_at"])
        update_distinction_rank(held)


def staff_remove_distinction(held: CharacterDistinction) -> None:
    """Remove a held distinction: its modifiers, its Secret, the row. No XP, no request.

    What ``remove_distinction`` keeps, this keeps: resonance currency, NPC assets and
    codex knowledge are not clawed back.
    """
    from world.distinctions.services import clear_distinction_secret  # noqa: PLC0415
    from world.mechanics.services import delete_distinction_modifiers  # noqa: PLC0415

    with transaction.atomic():
        delete_distinction_modifiers(held)
        clear_distinction_secret(held)
        held.delete()
