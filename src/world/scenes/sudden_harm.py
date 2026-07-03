"""Out-of-combat sudden-harm arming (#1316) — the non-combat sibling of combat's Interpose.

Mirrors world.areas.positioning.plummet.begin_plummet's bystander-present/absent branch:
alone (or below the significance threshold), harm resolves immediately, byte-identical to
today. With a bystander present, the harm is held (PendingSuddenHarm) and a DANGER round is
bootstrapped so they can ready Interpose before it resolves.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import DamageType


logger = logging.getLogger(__name__)


def _potential_interposer_present(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    exclude_character_id: int | None = None,
) -> bool:
    """True if anyone other than *target* is present and conscious enough to interpose.

    Mirrors world.areas.positioning.plummet._potential_catcher_present's shape — sudden
    harm has no "hostile source to exclude" concept the way bleed-out/abandonment does
    (a trap has no attacker), so the simpler catcher-presence check is the right fit.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.vitals.services import can_act  # noqa: PLC0415

    room = target.location
    if room is None:
        return False
    for obj in room.contents:
        if obj.id == target.id or (
            exclude_character_id is not None and obj.id == exclude_character_id
        ):
            continue
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        if can_act(sheet):
            return True
    return False


def _bind_interpose_challenge(target: ObjectDB) -> bool:  # noqa: OBJECTDB_PARAM
    """Bind the seeded Interpose ChallengeInstance to *target* (idempotent).

    Mirrors world.areas.positioning.plummet._create_catch_challenge_for's bind shape.
    Returns True once bound, False if the Interpose ChallengeTemplate isn't seeded
    (caller should degrade to immediate resolution rather than hold harm no Interpose
    option can ever surface for).
    """
    from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME  # noqa: PLC0415
    from world.mechanics.models import ChallengeInstance, ChallengeTemplate  # noqa: PLC0415

    try:
        template = ChallengeTemplate.objects.get(name=INTERPOSE_CHALLENGE_NAME)
    except ChallengeTemplate.DoesNotExist:
        logger.warning(
            "Interpose ChallengeTemplate not seeded; skipping challenge binding for sudden harm "
            "on %s.",
            target,
        )
        return False

    location = target.location
    ChallengeInstance.objects.get_or_create(
        template=template,
        target_object=target,
        is_active=True,
        defaults={"location": location, "is_revealed": True},
    )
    return True


def arm_or_apply_sudden_harm(
    target: ObjectDB,  # noqa: OBJECTDB_PARAM
    amount: int,
    damage_type: DamageType | None,
    *,
    source_description: str = "",
) -> None:
    """Apply sudden out-of-combat harm now, or hold it for one reactive Interpose beat.

    Mirrors begin_plummet's two-branch shape. Below the configured significance threshold,
    or with nobody present who could plausibly interpose, harm applies immediately via
    apply_resolved_damage (byte-identical to the pre-#1316 behavior). Otherwise, the harm
    is held in a PendingSuddenHarm row, an Interpose ChallengeInstance is bound to the
    target, and a DANGER round is bootstrapped (or ridden, if one is already active) —
    resolve_pending_interpose_harm resolves it at that round's resolution.
    """
    from world.mechanics.effect_handlers import apply_resolved_damage  # noqa: PLC0415
    from world.scenes.models import get_scene_round_defaults_config  # noqa: PLC0415
    from world.scenes.round_services import ensure_round_for_acute_condition  # noqa: PLC0415

    def _resolve_immediately() -> None:
        apply_resolved_damage(target, amount, damage_type)

    config = get_scene_round_defaults_config()
    if amount < config.sudden_harm_interpose_threshold or not _potential_interposer_present(target):
        _resolve_immediately()
        return

    if not _bind_interpose_challenge(target):
        # Interpose ChallengeTemplate isn't seeded — holding the harm would leave a
        # PendingSuddenHarm no Interpose option can ever surface for. Graceful degrade.
        _resolve_immediately()
        return

    from world.scenes.models import PendingSuddenHarm  # noqa: PLC0415

    scene_round = ensure_round_for_acute_condition(target.sheet_data)
    if scene_round is None:
        # No room to hold a round in (shouldn't happen alongside a presence check that
        # itself requires a room, but degrade to immediate resolution defensively).
        _resolve_immediately()
        return

    PendingSuddenHarm.objects.create(
        target_sheet=target.sheet_data,
        scene_round=scene_round,
        amount=amount,
        damage_type=damage_type,
        source_description=source_description,
    )
