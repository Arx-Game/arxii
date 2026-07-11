"""Read helper for the NpcRegard opinion axis (#1717).

One axis, one small module — mirrors ``world.npc_services.allegiance``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.npc_services.models import NpcRegardEvent, RegardEventConfig
    from world.scenes.models import Persona
    from world.societies.models import Organization, Society


def get_regard(holder_persona: Persona, target: Persona | Organization | Society) -> int:
    """Signed opinion ``holder_persona`` holds of ``target``; 0 if no active row."""
    from world.npc_services.models import NpcRegard  # noqa: PLC0415
    from world.scenes.models import Persona as PersonaModel  # noqa: PLC0415
    from world.societies.models import Organization, Society  # noqa: PLC0415

    if isinstance(target, PersonaModel):
        column = "target_persona"
    elif isinstance(target, Organization):
        column = "target_organization"
    elif isinstance(target, Society):
        column = "target_society"
    else:
        msg = f"Unsupported NpcRegard target type: {type(target)!r}"
        raise TypeError(msg)

    row = NpcRegard.objects.filter(
        holder_persona=holder_persona,
        ended_at__isnull=True,
        **{column: target},
    ).first()
    return row.value if row is not None else 0


def get_regard_event_config() -> RegardEventConfig:
    """Get-or-create the RegardEventConfig singleton (pk=1).

    Lazy-creates the singleton on first access. Mirrors ``get_bond_combat_config()``.
    """
    from world.npc_services.models import RegardEventConfig  # noqa: PLC0415

    cfg = RegardEventConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = RegardEventConfig.objects.get_or_create(pk=1)
    return cfg


def record_npc_regard_event(  # noqa: PLR0913 — keyword-only; each arg is a distinct citation fact
    *,
    holder_persona: Persona,
    target: Persona,
    amount: int,
    reason: str,
    source_pc_combat_action=None,
    source_npc_combat_action=None,
    source_scene=None,
    source_stake_resolution=None,
) -> NpcRegardEvent:
    """Record one typed, evidence-backed NpcRegardEvent and update NpcRegard.value (#2039).

    The single write seam for every buildup path — combat auto-hooks, the
    SHIFT_NPC_REGARD social effect, StakeResolution's pre-authored branches, GM
    manual calls, and chargen distinction seeding. ``amount`` is clamped to
    ``RegardEventConfig.max_event_delta`` (symmetric on both signs) before the
    event is created; ``NpcRegard.value`` is then clamped to REGARD_MIN/REGARD_MAX.
    Raises ``ValidationError`` (via ``full_clean()``) if ``reason``'s citation
    matrix isn't satisfied by the given source_* kwargs.

    The full write sequence (NpcRegard get-or-create, NpcRegardEvent
    full_clean+save, and the value update(s)) runs inside a single
    ``transaction.atomic()`` block so a ``full_clean()`` failure (e.g. a
    missing citation) cannot leave an orphan freshly-created NpcRegard row
    committed with no accompanying event.
    """
    from django.db import transaction  # noqa: PLC0415
    from django.db.models import F  # noqa: PLC0415

    from world.npc_services.constants import RegardTargetType  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        REGARD_MAX,
        REGARD_MIN,
        NpcRegard,
        NpcRegardEvent,
    )

    cfg = get_regard_event_config()
    clamped_amount = max(-cfg.max_event_delta, min(cfg.max_event_delta, amount))

    with transaction.atomic():
        regard, _created = NpcRegard.objects.get_or_create(
            holder_persona=holder_persona,
            target_type=RegardTargetType.PERSONA,
            target_persona=target,
            ended_at__isnull=True,
            defaults={"value": 0},
        )

        event = NpcRegardEvent(
            regard=regard,
            reason=reason,
            amount=clamped_amount,
            source_pc_combat_action=source_pc_combat_action,
            source_npc_combat_action=source_npc_combat_action,
            source_scene=source_scene,
            source_stake_resolution=source_stake_resolution,
        )
        event.full_clean()
        event.save()

        NpcRegard.objects.filter(pk=regard.pk).update(
            value=F("value") + clamped_amount,
        )
        regard.flush_from_cache(force=True)
        regard.refresh_from_db()
        if regard.value > REGARD_MAX or regard.value < REGARD_MIN:
            clamped_value = max(REGARD_MIN, min(REGARD_MAX, regard.value))
            NpcRegard.objects.filter(pk=regard.pk).update(value=clamped_value)
            regard.flush_from_cache(force=True)
            regard.refresh_from_db()

        from world.relationships.services import mirror_npc_regard_event_to_track  # noqa: PLC0415

        mirror_npc_regard_event_to_track(event)

    return event
