"""Filter compilation + group delivery for AmbientEmoteLine (#2471 v2).

compile_line_filter translates an AmbientEmoteLine's AmbientEmoteCondition rows into the
Trigger system's own filter-DSL shape — condition matching lives here (declaratively) and
in the DSL evaluator, not duplicated as bespoke Python branching.

deliver_ambient_group is what a derived Flow's CALL_SERVICE_FUNCTION step calls once its
Trigger's filter has ALREADY matched (see core_management.grid_import._install_ambient_triggers
for how the Trigger/Flow pair gets derived and installed). This function never re-decides
whether a condition holds — it only picks among an already-matched group's own lines,
subject to cooldown and a fire-chance roll, then delivers.
"""

from __future__ import annotations

from datetime import timedelta
import random

from django.utils import timezone

from world.narrative.constants import ConditionConnector, ConditionType, NarrativeCategory
from world.narrative.models import AmbientEmoteCondition, AmbientEmoteLine


def _compile_condition_leaf(condition: AmbientEmoteCondition) -> dict:
    if condition.condition_type == ConditionType.SPECIES:
        return {
            "path": "character.item_data.species.name",
            "op": "==",
            "value": condition.species.name,
        }
    if condition.condition_type == ConditionType.RESONANCE_MIN:
        return {
            "path": "character",
            "op": "has_resonance_at_least",
            "value": {"resonance": condition.resonance.name, "minimum": condition.minimum_value},
        }
    if condition.condition_type == ConditionType.DISTINCTION:
        return {
            "path": "character",
            "op": "has_public_distinction",
            "value": condition.distinction.slug,
        }
    if condition.condition_type == ConditionType.RENOWN_MIN:
        return {
            "path": "character",
            "op": "fame_tier_at_least",
            "value": {
                "min_tier": condition.min_fame_tier,
                "perceiving_society": (
                    condition.perceiving_society.name if condition.perceiving_society_id else None
                ),
            },
        }
    msg = f"Unknown condition_type: {condition.condition_type}"
    raise ValueError(msg)


def compile_line_filter(line: AmbientEmoteLine) -> dict | None:
    """Compile a line's conditions into a DSL filter dict, or None (always matches) for zero."""
    conditions = list(
        line.conditions.select_related("species", "resonance", "distinction", "perceiving_society")
    )
    if not conditions:
        return None
    leaves = [_compile_condition_leaf(condition) for condition in conditions]
    if len(leaves) == 1:
        return leaves[0]
    connector = "and" if line.condition_connector == ConditionConnector.AND else "or"
    return {connector: leaves}


def _has_renown_condition(line: AmbientEmoteLine) -> bool:
    return line.conditions.filter(condition_type=ConditionType.RENOWN_MIN).exists()


def _deliver_line(line: AmbientEmoteLine, character: object, room: object) -> None:
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    category = (
        NarrativeCategory.RENOWN if _has_renown_condition(line) else NarrativeCategory.ATMOSPHERE
    )
    if line.bystander_body:
        bystander_sheets = []
        for obj in room.contents:
            if obj.pk == character.pk:
                continue
            sheet = obj.character_sheet
            if sheet is not None:
                bystander_sheets.append(sheet)
        if bystander_sheets:
            send_narrative_message(
                recipients=bystander_sheets,
                body=line.bystander_body,
                category=category,
                ooc_note="Ambient room reaction (bystander register, #2471).",
            )
    if line.arriver_body:
        arriver_sheet = character.character_sheet
        if arriver_sheet is not None:
            send_narrative_message(
                recipients=[arriver_sheet],
                body=line.arriver_body,
                category=category,
                ooc_note="Ambient room reaction (arriver register, #2471).",
            )


def deliver_ambient_group(*, payload: object, line_ids: list[int]) -> bool:
    """Pick + deliver one line from an already-matched condition group (#2471 v2).

    Called by a derived Flow's CALL_SERVICE_FUNCTION step once its Trigger's filter has
    already matched — this function never re-decides whether the condition holds, only
    which line (among ``line_ids``) fires, subject to cooldown and a fire-chance roll.
    Returns True when a line fired (for tests); False on any quiet exit.
    """
    character = payload.character
    room = payload.destination
    if character is None or room is None:
        return False
    if character.character_sheet is None:
        return False

    now = timezone.now()
    lines = list(AmbientEmoteLine.objects.filter(pk__in=line_ids, is_active=True))
    fireable = [
        line
        for line in lines
        if line.last_fired_at is None
        or now >= line.last_fired_at + timedelta(minutes=line.cooldown_minutes)
    ]
    if not fireable:
        return False

    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    line = select_weighted(fireable)
    if random.randint(1, 100) > line.fire_chance:  # noqa: S311
        return False

    _deliver_line(line, character, room)
    line.last_fired_at = now
    line.save(update_fields=["last_fired_at"])
    return True
