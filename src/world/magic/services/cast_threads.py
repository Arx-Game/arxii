"""Compute applicable threads for an out-of-combat technique cast (#768).

Passive tier-0 in-scope threads (via the canonical ``_anchor_in_action``
predicate) plus an optional declared paid pull, merged charge-free into the
``ApplicableThread`` list consumed by ``thread_power_term``. Charging of a
declared pull happens later, inside ``use_technique``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.models import Thread
from world.magic.services.magic_skills import cast_involved_trait_ids
from world.magic.services.power_terms import ApplicableThread
from world.magic.services.resonance import (
    _anchor_ambiently_active,
    _anchor_in_action,
    resolve_gift_ids_by_technique,
)
from world.magic.types.pull import PullActionContext

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique
    from world.magic.types.magic_skills import CastCheck
    from world.magic.types.pull import CastPullDeclaration


def applicable_threads_for_cast(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — caster is any game object; resolved to a sheet
    technique: Technique | None,
    *,
    cast_pull: CastPullDeclaration | None = None,
    cast_check: CastCheck | None = None,
) -> list[ApplicableThread] | None:
    """Resolve a caster's applicable threads for an out-of-combat cast.

    Convenience wrapper for the non-combat cast callers: resolves the caster's
    ``CharacterSheet`` and current room from the ObjectDB ``character``, then
    delegates to :func:`build_cast_applicable_threads`. Returns ``None`` for an
    NPC without a sheet (so ``use_technique`` falls back to its baseline path).
    ``cast_check`` is the check the caller already resolved for this cast (#4450).
    """
    from world.magic.services.techniques import _get_character_sheet  # noqa: PLC0415

    sheet = _get_character_sheet(character)
    if sheet is None:
        return None
    location = character.location
    location_id = location.pk if location is not None else None
    return build_cast_applicable_threads(
        sheet, technique, location_id=location_id, cast_pull=cast_pull, cast_check=cast_check
    )


def build_applicable_threads(
    sheet: CharacterSheet,
    ctx: PullActionContext,
    *,
    ambient: bool = False,
    cast_pull: CastPullDeclaration | None = None,
) -> list[ApplicableThread]:
    """Return merged ApplicableThreads for ``ctx``. Charge-free.

    ``ambient=False`` (default) uses ``_anchor_in_action`` — the paid-pull predicate, the
    behaviour every pre-#2708 caller relies on. ``ambient=True`` uses
    ``_anchor_ambiently_active``, the stricter passive predicate (#2708).

    **``ambient=True`` has no production caller** (#2708 C1 review, M4):
    ``build_cast_applicable_threads`` — the only production wrapper — always passes
    ``ambient=False``. The capability magnitude curve's own ambient sweep
    (``_technique_capability_values`` / ``_get_technique_sources``) reads
    ``CharacterThreadHandler.contextual_thread_power`` directly instead of going through
    this function. ``ambient=True`` is kept deliberately (not dead code to delete) as a
    standalone-testability seam for ``_anchor_ambiently_active``'s merge-into-
    ``ApplicableThread`` behaviour, independent of the capability oracles' own tests —
    see ``world/magic/tests/test_cast_threads.py``. If a future caller needs the ambient
    predicate merged into an ``ApplicableThread`` list outside a test, this is where it
    should reach; until then, do not treat the branch as unreachable/removable.
    """
    by_thread: dict[int, int] = {}
    threads = list(
        Thread.objects.filter(owner=sheet, retired_at__isnull=True).select_related(
            "resonance",
            "target_technique",
            "target_mantle__item_instance",
            "target_sanctum_details__feature_instance__room_profile",
            "target_relationship",
            "target_capstone__relationship",
        )
    )
    # Resolved once per batch (not per thread) so a character with several GIFT threads
    # doesn't fire one Technique query per thread in the loop below (#2708 review).
    gift_id_by_technique = (
        resolve_gift_ids_by_technique(ctx.involved_techniques) if ambient else None
    )
    for thread in threads:
        if ambient:
            is_applicable = _anchor_ambiently_active(
                thread, ctx, character=sheet.character, gift_id_by_technique=gift_id_by_technique
            )
        else:
            is_applicable = _anchor_in_action(thread, ctx)
        if is_applicable:
            by_thread[thread.pk] = 0
    resolved_threads = {t.pk: t for t in threads}
    if cast_pull is not None:
        for thread in cast_pull.threads:
            resolved_threads[thread.pk] = thread
            by_thread[thread.pk] = max(by_thread.get(thread.pk, 0), cast_pull.tier)
    return [
        ApplicableThread(thread=resolved_threads[pk], pull_tier=tier)
        for pk, tier in sorted(by_thread.items())
    ]


def build_cast_applicable_threads(
    sheet: CharacterSheet,
    technique: Technique | None,
    *,
    location_id: int | None = None,
    cast_pull: CastPullDeclaration | None = None,
    cast_check: CastCheck | None = None,
) -> list[ApplicableThread]:
    """Return merged ApplicableThreads (passive tier-0 + declared pull). Charge-free.

    Cast path only — always the paid-pull predicate (``ambient=False``). A thin wrapper
    over :func:`build_applicable_threads`.

    ``cast_check`` is what the cast rolls (#4450): its check type's traits and skill terms
    become the context's ``involved_traits``, so a TRAIT thread on the caster's stat, a
    personal skill or the technique skill is in the cast's action. Without it no trait is
    involved, as before.
    """
    ctx = PullActionContext(
        combat_encounter=None,
        involved_techniques=(technique.pk,) if technique is not None else (),
        involved_objects=(location_id,) if location_id is not None else (),
        involved_traits=cast_involved_trait_ids(cast_check),
    )
    return build_applicable_threads(sheet, ctx, ambient=False, cast_pull=cast_pull)
