"""Causal Legend recognition for ordinary story settlement (#3914).

Recognition is an authored evidence ledger, not a proxy for severity, damage, or
roll quality.  Sources explicitly record successful causes; settlement may attach
zero-value labels to the existing shared deed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.societies.models import LegendEntry, LegendRecognitionEvidence, LegendRecognitionRule
    from world.stories.models import Stake, StakeContractActivation

BRIDGE_HOLD = "bridge_hold"
ENVOY_RESCUE = "envoy_rescue"
CREATED_OPENING = "created_opening"


@dataclass(frozen=True)
class RecognitionLabel:
    """Safe, player-facing recognition data; no source or success metadata."""

    key: str
    label: str
    description: str


def _rule(key: str, source_kind: str) -> LegendRecognitionRule | None:
    from world.societies.models import LegendRecognitionRule  # noqa: PLC0415

    return LegendRecognitionRule.objects.filter(
        key=key, source_kind=source_kind, is_active=True
    ).first()


def record_causal_evidence(  # noqa: PLR0913
    activation: StakeContractActivation,
    actor_sheet: CharacterSheet,
    *,
    key: str,
    source_kind: str,
    source_id: int,
    source_action_id: int | None = None,
    protected_sheet: CharacterSheet | None = None,
    context: dict | None = None,
) -> LegendRecognitionEvidence | None:
    """Persist one explicit successful cause, or no-op without an authored rule.

    The caller must invoke this only after the source action succeeded.  This
    function intentionally has no inference path from a check, damage amount,
    reaction declaration, or scene severity.
    """
    if source_id <= 0:
        message = "source_id must be a positive server-side identifier"
        raise ValueError(message)
    rule = _rule(key, source_kind)
    if rule is None:
        return None
    from world.societies.models import LegendRecognitionEvidence  # noqa: PLC0415

    values = {
        "source_action_id": source_action_id,
        "protected_sheet": protected_sheet,
        "context": context or {},
    }
    try:
        with transaction.atomic():
            evidence, _created = LegendRecognitionEvidence.objects.get_or_create(
                activation=activation,
                actor_sheet=actor_sheet,
                rule=rule,
                source_kind=source_kind,
                source_id=source_id,
                defaults=values,
            )
    except IntegrityError:
        # Concurrent completion/retry races are equivalent to the first write.
        evidence = LegendRecognitionEvidence.objects.get(
            activation=activation,
            actor_sheet=actor_sheet,
            rule=rule,
            source_kind=source_kind,
            source_id=source_id,
        )
    return evidence


def record_envoy_rescue(
    activation: StakeContractActivation,
    actor_sheet: CharacterSheet,
    *,
    source_id: int,
    source_action_id: int,
    protected_sheet: CharacterSheet,
) -> LegendRecognitionEvidence | None:
    """Record a successful guardian/interpose rescue with its protected PC."""
    return record_causal_evidence(
        activation,
        actor_sheet,
        key=ENVOY_RESCUE,
        source_kind="rescue",
        source_id=source_id,
        source_action_id=source_action_id,
        protected_sheet=protected_sheet,
    )


def record_created_opening(
    activation: StakeContractActivation,
    actor_sheet: CharacterSheet,
    *,
    source_id: int,
    contribution_kind: str,
) -> LegendRecognitionEvidence | None:
    """Record a boss-break contribution that actually reached zero."""
    if not contribution_kind:
        message = "contribution_kind is required"
        raise ValueError(message)
    return record_causal_evidence(
        activation,
        actor_sheet,
        key=CREATED_OPENING,
        source_kind="break_bar",
        source_id=source_id,
        context={"kind": contribution_kind},
    )


def _stake_label(stake: Stake) -> str:
    """Return authored objective text used by a staff-authored match rule."""
    values = [stake.subject_label, stake.player_summary]
    if stake.template is not None:
        values.append(stake.template.name)
    return " ".join(values).lower()


def emit_authored_bridge_holds(activation: StakeContractActivation) -> int:
    """Emit bridge-hold evidence only for winning authored objectives.

    A matching staff rule supplies the objective label fragment and threshold;
    therefore a high ordinary check in a severe scene cannot qualify by itself.
    """
    from world.societies.models import LegendContribution  # noqa: PLC0415
    from world.stories.constants import StakeResolutionColumn  # noqa: PLC0415
    from world.stories.models import StakeOutcome  # noqa: PLC0415

    rule = _rule(BRIDGE_HOLD, "stake")
    if rule is None:
        return 0
    winning_stakes = set(
        StakeOutcome.objects.filter(
            activation=activation,
            column=StakeResolutionColumn.WIN,
        ).values_list("stake_id", flat=True)
    )
    if not winning_stakes:
        return 0
    rows = LegendContribution.objects.filter(
        activation=activation,
        stake_id__in=winning_stakes,
        success_level__gte=rule.minimum_success_level,
    ).select_related("character_sheet", "stake", "stake__template")
    count = 0
    for row in rows:
        if rule.subject_label_contains.lower() not in _stake_label(row.stake):
            continue
        if (
            record_causal_evidence(
                activation,
                row.character_sheet,
                key=BRIDGE_HOLD,
                source_kind="stake",
                source_id=row.pk,
            )
            is not None
        ):
            count += 1
    return count


def collect_recognition_evidence(
    activation: StakeContractActivation,
) -> list[LegendRecognitionEvidence]:
    """Materialize authored objective evidence and return all ledger rows."""
    emit_authored_bridge_holds(activation)
    from world.societies.models import LegendRecognitionEvidence  # noqa: PLC0415

    return list(
        LegendRecognitionEvidence.objects.filter(activation=activation)
        .select_related("rule", "actor_sheet")
        .order_by("created_at", "pk")
    )


def labels_for_entry(entry: LegendEntry) -> list[RecognitionLabel]:
    """Return safe labels for one entry, ordered and deduplicated."""
    from world.societies.models import LegendEntryRecognition  # noqa: PLC0415

    rows = LegendEntryRecognition.objects.filter(entry=entry).select_related("evidence__rule")
    return [
        RecognitionLabel(key=row.key, label=row.label, description=row.description) for row in rows
    ]


def attach_recognition_labels(
    entries: list[LegendEntry], activation: StakeContractActivation
) -> dict[int, list[RecognitionLabel]]:
    """Attach each actor's evidence to their existing entry, without value changes.

    This is the pure settlement adapter boundary: #3911 can call it after its
    authoritative settlement report.  It never creates a deed or alters value.
    """
    from world.societies.models import LegendEntryRecognition  # noqa: PLC0415

    evidence = collect_recognition_evidence(activation)
    by_sheet: dict[int, list[LegendRecognitionEvidence]] = {}
    for row in evidence:
        by_sheet.setdefault(row.actor_sheet_id, []).append(row)
    result: dict[int, list[RecognitionLabel]] = {}
    for entry in entries:
        sheet_id = entry.persona.character_sheet_id
        for row in by_sheet.get(sheet_id, []):
            label = LegendEntryRecognition.objects.get_or_create(
                entry=entry,
                evidence=row,
                defaults={
                    "key": row.rule.key,
                    "label": row.rule.label,
                    "description": row.rule.description,
                },
            )[0]
            result.setdefault(entry.pk, []).append(
                RecognitionLabel(key=label.key, label=label.label, description=label.description)
            )
    return result
