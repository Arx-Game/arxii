"""Non-teaching technique acquisition service (#1732).

learn_technique is the shared commit seam: it runs the gift-owned check,
prerequisite check, cap check, AP/XP spend, mints CharacterTechnique, and
announces. Called by item on-use and ritual SERVICE dispatch.

Gift ownership is the whole path gate (#2700). The former per-technique
path-style gate was removed: which techniques a path can reach is authored
on ``PathGiftGrant``/``TraditionGiftGrant`` at technique granularity, and
style now lives on the caster (``classes.Path.style``), where it gates
*casting* rather than *learning*.

**Prerequisite gate (#4097 fix round 2).** ``learn_technique`` used to mint
with no check of authored ``TechniqueKnownRequirement``/``GiftHeldRequirement``/
etc. rows — ``charge_and_learn`` ran the check, but this seam (item scrolls,
rituals, GM award) did not, so an item scroll or a ritual could teach a
technique whose prerequisites were never met. The gate now runs here too,
via the same ``enforce_technique_prerequisites`` helper ``charge_and_learn``
uses, skipped only for ``origin=AcquisitionOrigin.GM_GRANT`` (deliberate GM
fiat) and for a meter-completion mint (``completing_progress=True`` —
whichever path created the meter already ran this check at creation time;
re-checking at completion would let a character's paid-for progress rot the
moment they shed an unrelated prerequisite mid-training).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.achievements.constants import AccessChangeSource
from world.achievements.discovery import announce_access_change
from world.magic.constants import AcquisitionOrigin
from world.magic.exceptions import (
    GiftNotOwned,
    TechniqueCapExceeded,
)
from world.magic.services.gift_acquisition import (
    count_techniques_for_gift,
    enforce_not_ultimate,
    enforce_technique_prerequisites,
    get_technique_cap_for_gift,
    resolve_owned_gift,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterTechnique, Technique, TechniqueProgress


def _training_room_discounted_ap_cost(ap_cost: int, location: object | None) -> int:
    """Return ``ap_cost`` reduced by an active Training Room feature (#675).

    When ``location`` is provided and a ``RoomProfile`` with an active Training
    Room is found, the discount is ``level × TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL``
    (floored at 0). Otherwise the cost is unchanged.
    """
    if location is None:
        return ap_cost
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.room_features.constants import (  # noqa: PLC0415
        TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL,
    )
    from world.room_features.services import (  # noqa: PLC0415
        active_training_room_in,
    )

    room_profile = RoomProfile.objects.filter(objectdb=location).first()
    if room_profile is None:
        return ap_cost
    training_room = active_training_room_in(room_profile)
    if training_room is None:
        return ap_cost
    return max(0, ap_cost - training_room.level * TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL)


@transaction.atomic
def learn_technique(  # noqa: PLR0913
    learner: CharacterSheet,
    technique: Technique,
    *,
    source: AccessChangeSource,
    ap_cost: int = 0,
    xp_cost: int = 0,
    location: object | None = None,
    origin: AcquisitionOrigin = AcquisitionOrigin.TRAINED,
    completing_progress: bool = False,
) -> CharacterTechnique | TechniqueProgress:
    """Learn a technique from an owned gift (non-teaching path).

    When ``ap_cost > 0``: creates a ``TechniqueProgress`` meter instead of
    minting immediately (#2711). The learner fills the meter in subsequent
    sessions via ``contribute_to_technique_progress``.

    When ``ap_cost == 0``: mints the ``CharacterTechnique`` immediately
    (the meter-completion path, or a free grant). Runs: gift-owned check
    -> duplicate check -> prerequisite check -> cap check -> mint -> announce.

    Never implicitly acquires the gift — that is the teaching path's job.

    Args:
        learner: The character learning the technique.
        technique: The technique to learn.
        source: The AccessChangeSource for the announce message.
        ap_cost: AP to spend (0 = mint immediately; >0 = create meter).
        xp_cost: XP to spend (0 = free; not yet implemented — deferred).
        location: Optional room object the learner is in. When provided,
            an active Training Room feature in that room discounts the AP
            cost (#675).
        origin: The ``AcquisitionOrigin`` stamped on the minted
            ``CharacterTechnique`` (defaults to ``TRAINED``, unchanged for
            every existing caller). ``GMAwardAction`` (#3055 slice 1c) is the
            first caller to pass ``AcquisitionOrigin.GM_GRANT`` here, marking
            a technique granted by GM fiat rather than earned via
            training/teaching investment — a GM award is deliberate fiat, so
            it also skips the prerequisite check below (#4097 fix round 2).
        completing_progress: True when this call is minting the
            ``CharacterTechnique`` that fills an already-existing
            ``TechniqueProgress`` meter (``contribute_to_technique_progress``,
            #4097 fix round 2). The prerequisite check already ran whenever
            that meter was created (either here, in the ``ap_cost > 0``
            branch below, or in ``charge_and_learn``), so it is skipped here
            to avoid re-gating already-committed training.

    Returns:
        ``CharacterTechnique`` when ``ap_cost == 0`` (immediate mint),
        ``TechniqueProgress`` when ``ap_cost > 0`` (meter created).

    Raises:
        UltimateNotLearnable: ``technique.is_ultimate`` — ultimates are only
            reached by discovering them at Audere/Audere Majora (#4098), never
            through this seam, not even a GM award.
        GiftNotOwned: Learner doesn't own the technique's gift.
        TechniqueRequirementsNotMet: An active requirement targeting this
            technique (Path, gift, technique, skill, ...) is not met —
            skipped for ``origin=GM_GRANT`` and ``completing_progress=True``.
        TechniqueCapExceeded: At the cap for this gift at current thread level.
        ValueError: Learner already knows this technique.
    """
    from world.magic.models import (  # noqa: PLC0415
        CharacterTechnique,
        TechniqueProgress,
    )

    # 0. An ultimate is never learned through an ordinary route (#4098). Checked
    # first, even ahead of GM fiat: a GM award is deliberate, but ultimates are
    # reserved for the Audere reveal specifically, not for any other grant path.
    enforce_not_ultimate(technique)

    # 1. Gift-owned precondition. Ownership walks the gift lineage (#2891): a
    # character holding a child gift reaches its ancestors' techniques too, so
    # an exact `gift=technique.gift` match would refuse every inherited one.
    owned_gift = resolve_owned_gift(learner, technique.gift)
    if owned_gift is None:
        raise GiftNotOwned

    # 3. Duplicate check.
    if CharacterTechnique.objects.filter(character=learner, technique=technique).exists():
        msg = f"{learner} already knows {technique.name}."
        raise ValueError(msg)

    # 3b. Prerequisites (#4097 fix round 2): same gate charge_and_learn runs.
    # Skipped for GM fiat and for a meter-completion mint — see the
    # `origin`/`completing_progress` docstring entries above.
    if origin != AcquisitionOrigin.GM_GRANT and not completing_progress:
        enforce_technique_prerequisites(learner, technique)

    # 4. Cap check — against the gift the learner actually holds, since that is
    # where their one GIFT thread hangs and what its cap covers.
    current_count = count_techniques_for_gift(learner, owned_gift)
    cap = get_technique_cap_for_gift(learner, owned_gift)
    if current_count >= cap:
        raise TechniqueCapExceeded

    # 4b. If ap_cost > 0, create a progress meter instead of minting (#2711).
    if ap_cost > 0:
        effective_ap_cost = _training_room_discounted_ap_cost(ap_cost, location)
        return TechniqueProgress.objects.create(
            character_sheet=learner,
            technique=technique,
            total_required=effective_ap_cost,
            source=source,
        )

    # TODO(#1732-deferred): XP spend when xp_cost > 0 — needs XPTransaction wiring.
    _ = xp_cost

    # 6. Mint (ap_cost == 0 path — immediate). This is the shared mint seam for
    # a ritual TechniqueGrant dispatch, a completed TechniqueProgress meter, and
    # a GMAwardAction story grant (#3055 slice 1c) — origin defaults to TRAINED
    # (the "acquired via training/teaching investment" family) but the GM-award
    # caller passes AcquisitionOrigin.GM_GRANT to mark it as GM fiat instead.
    ct = CharacterTechnique.objects.create(character=learner, technique=technique, origin=origin)

    # 7. Announce.
    announce_access_change(
        learner,
        gained=[technique],
        lost=[],
        source=source,
    )

    return ct


def learn_technique_from_ritual(*, character_sheet, ritual, **_kwargs):
    """SERVICE-dispatch adapter: learn a technique via a ritual TechniqueGrant.

    Called by PerformRitualAction._dispatch_service when a ritual with
    execution_kind=SERVICE has service_function_path pointing here. The
    Ritual instance is forwarded by the dispatch (contract fix in Task 6).

    Args:
        character_sheet: The CharacterSheet of the ritual performer.
        ritual: The Ritual being performed (forwarded by _dispatch_service).

    Returns:
        The new CharacterTechnique.
    """
    from world.magic.models import TechniqueGrant  # noqa: PLC0415

    grant = TechniqueGrant.objects.select_related("technique").get(ritual=ritual)
    return learn_technique(
        character_sheet,
        grant.technique,
        source=AccessChangeSource.TECHNIQUE_GRANT,
        ap_cost=grant.acquisition_ap_cost,
        xp_cost=grant.acquisition_xp_cost,
        location=character_sheet.character.location,
    )
