"""Cron batch service for deferred reward payouts (Phase 5b.2).

Phase 5b.1 wrote :class:`MissionRewardQueue` rows for every POST_CRON
reward line. Phase 5b.2 is the *cron* that walks those queued rows and
grants the underlying reward downstream. Both sinks are implemented:

  * RESONANCE (#1737) — resolves the recipient's CharacterSheet and calls
    grant_resonance with source=GainSource.MISSION_REWARD.
  * LEGEND_POINTS (#3468) — prices the award against the mission's own
    risk_tier and the earner's station, then mints a solo deed. Stub-sealed
    until #3468; DESIGN §13.3 recorded the blocker as "richer line shape"
    (persona walk + LegendSourceType + title), all of which the queue row
    always reached through ``row.line``. What was genuinely missing was a
    *price*, which #3463/ADR-0249 supplied.

Both helpers succeed and flip the row to ``applied=True``. A LEGEND_POINTS
row that prices to zero — an over-levelled earner, or a mission below the
Legend floor — still applies, because "correctly priced to nothing" is a
settled outcome and not a fault. Leaving it unapplied would recreate the bug
#3468 fixed: a row that fails forever and silently never pays.

Per-row :func:`transaction.atomic` keeps a fault on row N from corrupting
adjacent rows; the batch returns separate applied/failed tuples for each
outcome.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.models import MissionRewardQueue
from world.missions.services.rewards import MissionRewardRoutingError
from world.missions.types import RewardBatchResult

logger = logging.getLogger(__name__)

# Lazy-row LegendSourceType name for mission-earned Legend, following the
# get_or_create idiom every other deed source uses (LegendSourceType has no
# fixed enum of members, so rows are created on first use, not fixture-seeded).
_MISSION_SOURCE_TYPE_NAME = "Mission"

# MissionRewardQueue.failure_reason is a CharField(max_length=500); clip
# anything longer when we surface unexpected exceptions.
_FAILURE_REASON_MAX = 500


def _grant_legend_points(row: MissionRewardQueue) -> None:
    """Pay the Legend a mission deed's LEGEND_POINTS line promised (#3468).

    Stub-sealed until now. The blocker DESIGN §13.3 recorded was that the queue
    row lacked "a per-persona walk plus a LegendSourceType plus a title" — all
    three are reachable from ``row.line`` today, and #3463 supplied the missing
    fourth thing nobody had written down: a *price*.

    Priced, never asserted (ADR-0249). ``line.amount`` is the author's declared
    ceiling; the mission's own ``risk_tier`` is the settled reality; Legend pays
    the weaker, capped by the earner's station and floored at nothing below
    ``LEGEND_RISK_FLOOR``.

    **A zero price still applies the row.** An over-levelled earner, or a
    mission below the floor, is a *settled outcome* — not a fault. Leaving the
    row unapplied would recreate this issue's own bug (a queue row that fails
    forever and silently never pays) in a new disguise, so the only difference
    is whether a deed is minted.
    """
    from world.missions.services.legend_pricing import (  # noqa: PLC0415
        mission_settlement_context,
        priced_legend_value,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.models import LegendSourceType  # noqa: PLC0415
    from world.societies.services import create_solo_deed  # noqa: PLC0415

    line = row.line
    sheet = line.recipient
    template = line.deed.instance.template
    settled_risk, station = mission_settlement_context(template, sheet)
    value = priced_legend_value(line.amount or 0, settled_risk, station)
    if value <= 0:
        logger.info(
            "Mission LP row %s priced to zero (tier=%s, band_max=%s, station=%s) — "
            "applied with no deed minted.",
            row.pk,
            template.risk_tier,
            template.level_band_max,
            station,
        )
        return

    persona = active_persona_for_sheet(sheet) or sheet.primary_persona
    source_type, _created = LegendSourceType.objects.get_or_create(
        name=_MISSION_SOURCE_TYPE_NAME,
        defaults={"description": "Deeds done on contract — missions run and survived."},
    )
    create_solo_deed(
        persona,
        f"Mission deed: {template.name}",
        source_type,
        value,
        earned_at_level=station,
    )


def _grant_resonance(row: MissionRewardQueue) -> None:
    """Grant the resonance a mission deed's RESONANCE-sink line promised.

    Resolves the recipient's CharacterSheet from the line's recipient
    ObjectDB, then calls the canonical grant_resonance() with
    source=GainSource.MISSION_REWARD (#1737).
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    line = row.line
    sheet = line.recipient
    grant_resonance(
        sheet,
        line.resonance,
        line.amount,
        source=GainSource.MISSION_REWARD,
        mission_deed_reward_line=line,
    )


def _apply_one(row: MissionRewardQueue) -> str | None:
    """Try to grant one queue row's reward downstream.

    Returns ``None`` on success (the row was flipped to ``applied=True``)
    or a non-empty failure-reason string when the grant raised. Per-row
    :func:`transaction.atomic` is wrapped by the caller, not here — so an
    inner write that succeeds before a later raise also rolls back inside
    the savepoint.
    """
    if row.kind == DeedRewardKind.POST_CRON and row.sink == DeedRewardSink.LEGEND_POINTS:
        _grant_legend_points(row)
    elif row.kind == DeedRewardKind.POST_CRON and row.sink == DeedRewardSink.RESONANCE:
        _grant_resonance(row)
    else:
        # Defensive: ``apply_deed_rewards`` only enqueues the two POST_CRON
        # sinks, so this arm should be unreachable. Raise a typed routing
        # error so the cron's catch-all records a clear failure_reason.
        raise MissionRewardRoutingError(
            kind=row.kind,
            sink=row.sink,
            line_pk=row.line_id,
        )

    # Success path, reached by both sinks since #3468 — including a
    # LEGEND_POINTS row that priced to zero, which is settled, not failed.
    row.applied = True
    row.applied_at = timezone.now()
    row.failure_reason = ""
    row.save(update_fields=["applied", "applied_at", "failure_reason"])
    return None


def _record_failure(row: MissionRewardQueue, reason: str) -> None:
    """Persist a per-row failure reason without flipping ``applied``."""
    row.failure_reason = reason[:_FAILURE_REASON_MAX]
    row.save(update_fields=["failure_reason"])


def apply_mission_reward_batch() -> RewardBatchResult:
    """Walk every ``applied=False`` :class:`MissionRewardQueue` row and try to grant it.

    Each row is processed in its own savepoint (:func:`transaction.atomic`)
    so a fault on row N does not corrupt rows N-1 or N+1. Both
    ``_grant_legend_points`` (#3468) and ``_grant_resonance`` (#1737) succeed
    and flip the row to ``applied=True``.

    Idempotency is now uniform across both sinks (#3468 — LEGEND_POINTS rows
    used to never flip ``applied``, so the batch re-selected and re-failed
    them forever). It holds because (1) the ``applied=False`` filter below
    stops re-selecting a row once it succeeds, and (2) each grant is itself
    wrapped in :func:`transaction.atomic`, so a row can never end up applied
    without its grant having actually committed (or vice versa) — a crash
    mid-grant leaves the row unapplied and safe to retry.

    Returns:
        A typed :class:`RewardBatchResult` carrying the queue rows that
        succeeded (RESONANCE rows that granted cleanly, #1737) and the rows
        that failed (LEGEND_POINTS rows, plus any RESONANCE row whose grant
        raised).
    """
    # select_related: _grant_resonance dereferences row.line.recipient.sheet_data
    # per row (#1737), which would otherwise be two extra queries per RESONANCE
    # row. "line" and "line__recipient" are forward FKs off MissionRewardQueue
    # and MissionDeedRewardLine respectively, so they select_related directly.
    # "line__recipient__sheet_data" is a *reverse* OneToOne accessor
    # (CharacterSheet.character -> ObjectDB, related_name="sheet_data") — Django
    # supports select_related() across reverse OneToOne the same as forward FKs
    # (LEFT OUTER JOIN, verified via .query), so it's included too rather than
    # left as a per-row query.
    unapplied = list(
        MissionRewardQueue.objects.filter(applied=False)
        .select_related("line", "line__recipient")
        .order_by("pk")
    )

    applied: list[MissionRewardQueue] = []
    failed: list[MissionRewardQueue] = []

    for row in unapplied:
        try:
            with transaction.atomic():
                outcome = _apply_one(row)
        except MissionRewardRoutingError as exc:
            _record_failure(row, exc.user_message)
            failed.append(row)
            continue
        except Exception as exc:
            logger.exception("Mission reward routing failed for queue row %s", row.pk)
            _record_failure(row, f"{type(exc).__name__}: {exc}")
            failed.append(row)
            continue

        if outcome is None:
            applied.append(row)
        else:
            # Defensive path for the future: a helper that signals
            # soft-failure via a returned message rather than raising.
            _record_failure(row, outcome)
            failed.append(row)

    return RewardBatchResult(applied=tuple(applied), failed=tuple(failed))


__all__ = ("apply_mission_reward_batch", "resolve_expired_group_votes")


def resolve_expired_group_votes() -> int:
    """Backstop sweep: resolve group nodes whose vote window has elapsed (#1036).

    The play surface lazily resolves an expired group node on the next access,
    which covers the common case. This sweep catches groups where *every*
    participant walked away without anyone hitting the beat again. Idempotent:
    a resolved node advances ``current_node`` and deletes its ballots, so a
    second sweep finds nothing. A row whose instance has moved on (node no longer
    current / run ended) has its stale ballots dropped so it doesn't re-scan
    forever; one node failing to resolve is logged and skipped so it can't starve
    the rest. Returns the number of nodes resolved.
    """
    from datetime import timedelta  # noqa: PLC0415
    import logging  # noqa: PLC0415

    from django.db.models import Min  # noqa: PLC0415

    from world.missions.constants import GROUP_VOTE_TIMEOUT_SECONDS, MissionStatus  # noqa: PLC0415
    from world.missions.models import (  # noqa: PLC0415
        MissionGroupBallot,
        MissionInstance,
        MissionNode,
    )
    from world.missions.services.multiplayer import resolve_group_node  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    cutoff = timezone.now() - timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS)
    expired = (
        MissionGroupBallot.objects.values("instance_id", "node_id")
        .annotate(first=Min("created_at"))
        .filter(first__lte=cutoff)
    )
    resolved = 0
    for row in expired:
        instance = MissionInstance.objects.filter(pk=row["instance_id"]).first()
        node = MissionNode.objects.filter(pk=row["node_id"]).first()
        live = (
            instance is not None
            and node is not None
            and instance.current_node_id == node.pk
            and instance.status == MissionStatus.ACTIVE
        )
        if instance is None or node is None or not live:
            # Node moved on / run ended — drop stale ballots so they don't
            # re-scan on every future sweep.
            MissionGroupBallot.objects.filter(
                instance_id=row["instance_id"], node_id=row["node_id"]
            ).delete()
            continue
        try:
            resolve_group_node(instance, node)
        except Exception:
            logger.exception(
                "group-vote sweep failed: instance=%s node=%s",
                row["instance_id"],
                row["node_id"],
            )
            continue
        resolved += 1
    return resolved
