"""The Insight — the Know need's once-per-fight ace (#2645).

Ratified design: ``design/covenant-vows-consolidated.md`` §5 (lore repo). The
Know character (scout/loremaster vows) reads the fight and shares a large,
narrowly-scoped, ONE-ROUND effect with an ally or the team — once per
encounter. Rides an existing PERCEPTION-tagged technique cast per the riding
rule (no new button); the skill expression is TIMING — holding the ace for
the moment that turns the fight, distinct in weight from the light "Look
out!" callout (#2637): the callout is frequent/small/names-no-counter, the
Insight is rare/large/specific.

**Never instant-win** — enforced editorially by curation of
``InsightTableEntry.condition`` rows (never a kill/win effect authored
there), not by any engine check in this module.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from world.covenants.constants import InsightTargetKind

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatParticipant
    from world.covenants.models import CovenantRole, InsightTableEntry
    from world.magic.models import Technique


def maybe_produce_insight(
    caster_sheet: CharacterSheet,
    technique: Technique,
    resolution_participant: CombatParticipant,
) -> bool:
    """Maybe fire the Insight rider for a resolved combat technique cast.

    Conditions (all must hold, else silently returns False — this is a
    rider, never a hard requirement of the cast it rides):

    - ``technique`` carries the PERCEPTION ``TechniqueFunctionTag``.
    - ``caster_sheet`` has an active engaged ``CharacterCovenantRole`` whose
      ``covenant_role`` (or that role's ``parent_role``) has
      ``grants_insight=True``.
    - ``resolution_participant.insight_used`` is False (once per encounter).
    - At least one active ``InsightTableEntry`` row exists to draw from.

    On success: draws a weighted-random active entry, applies its condition
    to the resolved target(s), announces the entry's prose on both channels,
    stamps ``resolution_participant.insight_used = True``, and returns True.
    """
    from world.magic.constants import TechniqueFunction  # noqa: PLC0415

    if not any(
        tag.function == TechniqueFunction.PERCEPTION for tag in technique.cached_function_tags
    ):
        return False

    if resolution_participant.insight_used:
        return False

    if not _has_engaged_insight_role(caster_sheet):
        return False

    entry = _draw_entry()
    if entry is None:
        return False

    _apply_insight(entry, caster_sheet=caster_sheet, participant=resolution_participant)

    resolution_participant.insight_used = True
    resolution_participant.save(update_fields=["insight_used"])
    return True


def _has_engaged_insight_role(caster_sheet: CharacterSheet) -> bool:
    """True if the sheet holds an active engaged membership riding grants_insight."""
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    memberships = CharacterCovenantRole.objects.filter(
        character_sheet=caster_sheet,
        engaged=True,
        left_at__isnull=True,
    ).select_related("covenant_role", "covenant_role__parent_role")
    return any(_role_grants_insight(membership.covenant_role) for membership in memberships)


def _role_grants_insight(role: CovenantRole) -> bool:
    """True if the role itself grants Insight, or it rides its parent's grant."""
    if role.grants_insight:
        return True
    return role.parent_role_id is not None and role.parent_role.grants_insight


def _draw_entry() -> InsightTableEntry | None:
    """Weighted-random draw over active InsightTableEntry rows; None if empty."""
    from world.covenants.models import InsightTableEntry  # noqa: PLC0415

    entries = list(InsightTableEntry.objects.filter(is_active=True))
    if not entries:
        return None
    weights = [entry.weight for entry in entries]
    # Curated table, not a cryptographic use of random.
    return random.choices(entries, weights=weights, k=1)[0]  # noqa: S311 # NOSONAR game RNG


def _resolve_targets(
    entry: InsightTableEntry,
    *,
    participant: CombatParticipant,
) -> list[CombatParticipant]:
    """Resolve the drawn entry's target_kind to concrete CombatParticipant rows.

    ALLY reads the current round's declared ally target off the caster's own
    CombatRoundAction, falling back to the caster when none was declared.
    TEAM is every ACTIVE PC-side participant in the encounter (CombatParticipant
    rows are inherently PC-side per the model's own docstring).
    """
    if entry.target_kind == InsightTargetKind.SELF:
        return [participant]

    if entry.target_kind == InsightTargetKind.TEAM:
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415

        return list(participant.encounter.participants.filter(status=ParticipantStatus.ACTIVE))

    # ALLY
    action = participant.round_actions.filter(
        round_number=participant.encounter.round_number
    ).first()
    ally = action.focused_ally_target if action is not None else None
    return [ally] if ally is not None else [participant]


def _character_name(sheet: CharacterSheet) -> str:
    character = sheet.character
    return character.key if character is not None else str(sheet)


def _apply_insight(
    entry: InsightTableEntry,
    *,
    caster_sheet: CharacterSheet,
    participant: CombatParticipant,
) -> None:
    """Apply the entry's condition to every resolved target, then announce."""
    from world.conditions.services import apply_condition  # noqa: PLC0415

    targets = _resolve_targets(entry, participant=participant)
    caster_character = caster_sheet.character
    for target_participant in targets:
        apply_condition(
            target=target_participant.character_sheet.character,
            condition=entry.condition,
            source_character=caster_character,
        )
    _announce_insight(entry, caster_sheet=caster_sheet, targets=targets, participant=participant)


def _announce_insight(
    entry: InsightTableEntry,
    *,
    caster_sheet: CharacterSheet,
    targets: list[CombatParticipant],
    participant: CombatParticipant,
) -> None:
    """Announce the fired entry's prose on BOTH the web and telnet channels.

    Mirrors ``world.combat.escalation``'s room-wide surge narration: the web
    broadcast goes through ``broadcast_action_outcome`` (WS-only), and the
    ``encounter.room.msg_contents`` call is the telnet-parity companion —
    ``broadcast_action_outcome`` alone does not reach bare telnet clients.
    """
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    caster_name = _character_name(caster_sheet)
    if len(targets) == 1:
        target_name = _character_name(targets[0].character_sheet)
    else:
        target_name = "the team"
    narration = entry.prose.format(caster=caster_name, target=target_name)

    encounter = participant.encounter
    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None and narration:
        room.msg_contents(narration)
