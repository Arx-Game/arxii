"""Player-driven legend spreading services (#745 — Spread a Tale).

`get_spreadable_deeds` powers the deed picker; the value formula + resolver
(added in later tasks) turn a scene-action check outcome into a `spread_deed`
call.
"""

from __future__ import annotations

from django.db.models import QuerySet

from world.scenes.action_resolvers import register_resolver
from world.societies.models import LegendEntry, OrganizationMembership

SPREAD_TALE_ACTION_KEY = "spread_a_tale"

# success_level -> fraction of base_value (failure / <=0 yields 0). Tunable.
TIER_PAYOFF: dict[int, float] = {0: 0.0, 1: 0.10, 2: 0.30, 3: 0.60, 4: 1.00}


def compute_spread_value(*, base_value: int, success_level: int, multiplier: float) -> int:
    """Legend value a single telling adds, before the per-deed cap clamp.

    ``base × tier_payoff(success_level) × traffic_multiplier``. Failures (or
    success_level <= 0) add nothing. success_level above the table tops out at
    the max payoff fraction.
    """
    if success_level <= 0:
        return 0
    payoff = TIER_PAYOFF.get(success_level, max(TIER_PAYOFF.values()))
    return round(base_value * payoff * multiplier)


def get_or_create_spread_a_tale_template():
    """Ensure the 'Spread a Tale' ActionTemplate exists, returning it.

    Idempotent. Uses the existing 'Performance' CheckType as the **placeholder**
    approach (the real bard/influence approach catalog is a flagged skill-audit
    decision — see #745 §9). Area action; charges 20 AP + light social fatigue.
    """
    from actions.constants import ActionTargetType, Pipeline  # noqa: PLC0415
    from actions.models.action_templates import ActionTemplate  # noqa: PLC0415
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(name="Social")
    check_type, _ = CheckType.objects.get_or_create(
        name="Performance", defaults={"category": category}
    )
    template, _ = ActionTemplate.objects.get_or_create(
        name="Spread a Tale",
        defaults={
            "check_type": check_type,
            "target_type": ActionTargetType.AREA,
            "category": "social",
            "pipeline": Pipeline.SINGLE,
            "ap_cost": 20,
            "social_fatigue_cost": 3,
            "accepts_pose_text": True,
            "icon": "megaphone",
        },
    )
    return template


def get_spreadable_deeds(persona) -> QuerySet[LegendEntry]:
    """Active deeds whose ``societies_aware`` intersects the persona's societies.

    A persona may spread tales known to any society they hold membership in
    (via an organization in that society). Inactive deeds and deeds no society
    of theirs knows of are excluded.
    """
    society_ids = OrganizationMembership.objects.filter(persona=persona).values_list(
        "organization__society_id", flat=True
    )
    return (
        LegendEntry.objects.filter(is_active=True, societies_aware__in=society_ids)
        .distinct()
        .order_by("-created_at")
    )


def _resolve_spread_tale(action_request, result) -> None:
    """Post-resolution side-effect for the ``spread_a_tale`` scene action.

    On a successful check, adds traffic-scaled legend to the deed (clamped to
    its cap by ``spread_deed``), bumps the subject's fame, and notifies them.
    No-op on failure, missing deed, or no check outcome.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.locations.activity_services import room_activity_band  # noqa: PLC0415
    from world.societies.renown import apply_spread_fame_bump  # noqa: PLC0415
    from world.societies.services import spread_deed  # noqa: PLC0415

    deed = action_request.spread_deed_target
    main = result.action_resolution.main_result
    if deed is None or main is None or main.check_result is None:
        return
    success_level = main.check_result.success_level
    if success_level <= 0:
        return

    room = action_request.scene.location if action_request.scene else None
    band = room_activity_band(room)
    value = compute_spread_value(
        base_value=deed.base_value, success_level=success_level, multiplier=band.multiplier
    )
    if value <= 0:
        return

    spread_deed(
        deed=deed,
        spreader_persona=action_request.initiator_persona,
        value_added=value,
        description=action_request.pose_text,
        method=action_request.action_key,
        audience_factor=Decimal(str(band.multiplier)),
        scene=action_request.scene,
    )
    apply_spread_fame_bump(
        deed, npc_audience=int(band.multiplier * 10), success_level=success_level
    )
    _notify_spread_subject(deed)


def _notify_spread_subject(deed) -> None:
    """Tell the deed's player-owned subject that their legend is spreading."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415
    from world.societies.notifications import _has_active_player  # noqa: PLC0415

    sheet = deed.persona.character_sheet
    if sheet is None or not _has_active_player(sheet):
        return
    send_narrative_message(
        recipients=[sheet],
        body="✦ A tale of your deed spreads — your legend grows.",
        category=NarrativeCategory.RENOWN,
    )


register_resolver(SPREAD_TALE_ACTION_KEY, _resolve_spread_tale)
