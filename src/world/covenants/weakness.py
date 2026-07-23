"""The Sage's weakness-reading rider (#2665).

Ratified design: ``design/covenant-vows-consolidated.md`` (lore repo). The
Sage vow character reads a boss during combat and actualizes one of its
authored candidate weaknesses — a standing enemy-side condition that the
party can exploit for the rest of the encounter.

Rides an existing PERCEPTION-tagged technique cast per the riding rule
(no new button for the trigger). The player chooses which weakness to
actualize via the ``select`` command, which resolves the PendingSelection
this rider creates.

Mirrors ``world.covenants.insight``'s structure (the Insight is the closest
sibling). Key differences: player chooses (not random draw), per-boss pool
(not global), persistent condition (not one-round).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatOpponent, CombatParticipant, PendingSelection
    from world.covenants.models import CovenantRole, WeaknessPoolEntry
    from world.magic.models import Technique


def maybe_create_weakness_selection(  # noqa: PLR0911
    caster_sheet: CharacterSheet,
    technique: Technique,
    resolution_participant: CombatParticipant,
    target_opponent: CombatOpponent | None,
) -> bool:
    """Maybe fire the weakness-reading rider for a resolved combat technique cast.

    Conditions (all must hold, else silently returns False — this is a
    rider, never a hard requirement of the cast it rides):

    - ``technique`` carries the PERCEPTION ``TechniqueFunctionTag``.
    - ``target_opponent`` is a BOSS-tier ``CombatOpponent`` with a
      ``creature_template`` that has at least one active
      ``WeaknessPoolEntry``.
    - ``caster_sheet`` has an active engaged ``CharacterCovenantRole``
      whose ``covenant_role`` (or that role's ``parent_role``) has
      ``reveals_weakness=True``.
    - ``resolution_participant.weakness_reading_used`` is False (once per
      encounter).

    On success: creates a ``PendingSelection`` with the boss's active
    ``WeaknessPoolEntry`` rows as options (option id = the entry's
    natural-key ``name``), stamps ``weakness_reading_used=True``,
    announces the reading to the player, and returns True.
    """
    from world.combat.constants import OpponentTier  # noqa: PLC0415
    from world.magic.constants import TechniqueFunction  # noqa: PLC0415

    if not any(
        tag.function == TechniqueFunction.PERCEPTION for tag in technique.cached_function_tags
    ):
        return False

    if target_opponent is None:
        return False

    if target_opponent.tier != OpponentTier.BOSS:
        return False

    if target_opponent.creature_template is None:
        return False

    if not _has_engaged_weakness_role(caster_sheet):
        return False

    if resolution_participant.weakness_reading_used:
        return False

    entries = _get_pool_entries(target_opponent)
    if not entries:
        return False

    _create_selection(
        caster_sheet=caster_sheet,
        participant=resolution_participant,
        opponent=target_opponent,
        entries=entries,
    )

    resolution_participant.weakness_reading_used = True
    resolution_participant.save(update_fields=["weakness_reading_used"])
    return True


def _has_engaged_weakness_role(caster_sheet: CharacterSheet) -> bool:
    """True if the sheet holds an active engaged membership riding reveals_weakness."""
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    memberships = CharacterCovenantRole.objects.filter(
        character_sheet=caster_sheet,
        engaged=True,
        left_at__isnull=True,
    ).select_related("covenant_role", "covenant_role__parent_role")
    return any(_role_reveals_weakness(membership.covenant_role) for membership in memberships)


def _role_reveals_weakness(role: CovenantRole) -> bool:
    """True if the role itself reveals weakness, or it rides its parent's flag."""
    if role.reveals_weakness:
        return True
    return role.parent_role_id is not None and role.parent_role.reveals_weakness


def _get_pool_entries(opponent: CombatOpponent) -> list:
    """Active WeaknessPoolEntry rows for the opponent's creature template."""
    from world.covenants.models import WeaknessPoolEntry  # noqa: PLC0415

    return list(
        WeaknessPoolEntry.objects.filter(
            creature_template=opponent.creature_template,
            is_active=True,
        )
    )


def _create_selection(
    *,
    caster_sheet: CharacterSheet,
    participant: CombatParticipant,
    opponent: CombatOpponent,
    entries: list,
) -> None:
    """Create a PendingSelection with the pool entries as options."""
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from world.combat.constants import SelectionType  # noqa: PLC0415
    from world.combat.models import PendingSelection  # noqa: PLC0415

    options = [
        {"id": entry.name, "label": entry.name, "description": entry.prose} for entry in entries
    ]
    ct = ContentType.objects.get_for_model(opponent)
    PendingSelection.objects.create(
        participant=participant,
        encounter=participant.encounter,
        selection_type=SelectionType.WEAKNESS,
        options_json=options,
        source_content_type=ct,
        source_object_id=opponent.pk,
        target_opponent=opponent,
    )
    _announce_reading(caster_sheet=caster_sheet, opponent=opponent, entries=entries)


def _announce_reading(
    *,
    caster_sheet: CharacterSheet,
    opponent: CombatOpponent,
    entries: list,
) -> None:
    """Announce the reading to the player (web + telnet)."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    caster_name = _character_name(caster_sheet)
    boss_name = opponent.name
    option_list = "\n".join(f"  [{i + 1}] {entry.name}" for i, entry in enumerate(entries))
    narration = (
        f"{caster_name} reads {boss_name}, finding cracks in its defenses.\n"
        f"Choose a weakness to actualize:\n{option_list}"
    )
    encounter = opponent.encounter
    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None and narration:
        room.msg_contents(narration)


def _character_name(sheet: CharacterSheet) -> str:
    character = sheet.character
    return character.key if character is not None else str(sheet)


def resolve_weakness_selection(
    selection: PendingSelection,
    chosen_option_id: str,
) -> bool:
    """Resolve a weakness-reading PendingSelection.

    Looks up the chosen WeaknessPoolEntry by its natural-key ``name``
    (matching the option id stored in options_json), applies its condition to
    the boss opponent's ObjectDB via ``apply_condition`` (persistent — no
    duration override), stamps ``selection.resolved_at``, and announces the
    actualized weakness on both web and telnet channels.

    Returns False if the selection is already resolved, the option id is
    invalid, the target opponent no longer exists, or the encounter is
    completed.
    """
    from django.utils import timezone  # noqa: PLC0415

    if selection.is_resolved:
        return False

    # Reject if encounter is completed
    encounter = selection.encounter
    if encounter.outcome:
        return False

    opponent = selection.target_opponent
    if opponent is None or opponent.objectdb_id is None:
        return False

    # Validate the chosen option
    option_ids = {opt["id"] for opt in selection.options_json}
    if chosen_option_id not in option_ids:
        return False

    from world.covenants.models import WeaknessPoolEntry  # noqa: PLC0415

    try:
        entry = WeaknessPoolEntry.objects.get(name=chosen_option_id)
    except WeaknessPoolEntry.DoesNotExist:
        return False

    from world.conditions.services import apply_condition  # noqa: PLC0415

    caster_character = selection.participant.character_sheet.character
    apply_condition(
        target=opponent.objectdb,
        condition=entry.condition,
        source_character=caster_character,
    )

    selection.selected_option_id = chosen_option_id
    selection.resolved_at = timezone.now()
    selection.save(update_fields=["selected_option_id", "resolved_at"])

    _announce_actualization(
        entry=entry,
        caster_sheet=selection.participant.character_sheet,
        opponent=opponent,
    )
    return True


def _announce_actualization(
    *,
    entry: WeaknessPoolEntry,
    caster_sheet: CharacterSheet,
    opponent: CombatOpponent,
) -> None:
    """Announce the actualized weakness on both web and telnet channels."""
    from world.combat.interaction_services import broadcast_action_outcome  # noqa: PLC0415

    caster_name = _character_name(caster_sheet)
    target_name = opponent.name
    narration = entry.prose.format(caster=caster_name, target=target_name)

    encounter = opponent.encounter
    broadcast_action_outcome(encounter=encounter, narration=narration)
    room = encounter.room
    if room is not None and narration:
        room.msg_contents(narration)
