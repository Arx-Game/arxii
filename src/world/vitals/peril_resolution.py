"""Death-permission gate for the acute-peril dying state (#1479, Task 3).

Determines whether a lethal outcome is structurally permitted for a given
victim/source pair. Two hard rules apply before any risk math:

- PC source (ADR-0023): PvP is structurally non-lethal — death never permitted.
- Active death_deferred condition: a deferred-death condition blocks the outcome.
- Absent/None source: treated as a non-lethal environmental context — not permitted.

A non-PC (significant-NPC) source with no death-deferral active on the victim
is the only configuration that returns True.

Task 7 (#1479) adds the involved-party narrowing helpers used by scene-round
resolution: ``hostile_drove_round`` (did the encounter that downed the victim act
this round?), ``potential_rescuer_present`` (could anyone present stabilize them?),
and the ``mark_abandoned`` / ``clear_abandoned`` markers that stamp/clear
``ConditionInstance.abandoned_since_round``.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from actions.models.consequence_pools import ConsequencePool
    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionInstance
    from world.scenes.models import SceneRound


def _acute_peril_condition_names() -> list[str]:
    """The condition names subject to the #1479 involved-party HOLD / abandonment.

    This is the HOLD/ABANDONMENT classification — "whose peril depends on who is
    menacing them and whether anyone will rescue them." That is BLEED_OUT only.

    PLUMMETING is deliberately EXCLUDED: a fall is environmental and
    self-completing — gravity does not care who is watching, so a plummeting
    character is never "held" waiting for a hostile/rescuer and is never resolved
    through an abandonment consequence pool. Their fall always advances to impact
    (per-round descent while a round ticks, or immediate resolution when no round
    drives it — see ``world.areas.positioning.plummet``).

    Note this NO LONGER mirrors ``round_services._danger_persists``, which still
    keys a DANGER round on BLEED_OUT *and* PLUMMETING so the round keeps ticking
    the descent until impact clears the Plummeting condition. The two sets diverge
    on purpose: ``_danger_persists`` = "keep the round alive"; this = "hold/abandon
    a downed victim."
    """
    from world.conditions.constants import BLEED_OUT_CONDITION_NAME  # noqa: PLC0415

    return [BLEED_OUT_CONDITION_NAME]


def acute_peril_instances(victim_sheet: "CharacterSheet") -> "QuerySet[ConditionInstance]":
    """Return the victim's active hold/abandonment-eligible ConditionInstances (Bleeding Out).

    Plummeting is excluded by ``_acute_peril_condition_names`` — see its docstring.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target_id=victim_sheet.character_id,
        condition__name__in=_acute_peril_condition_names(),
    )


def _acute_peril_source_ids(victim_sheet: "CharacterSheet") -> set[int]:
    """ObjectDB ids of the characters who inflicted the victim's acute peril."""
    return {
        inst.source_character_id
        for inst in acute_peril_instances(victim_sheet)
        if inst.source_character_id is not None
    }


def hostile_drove_round(
    victim_sheet: "CharacterSheet",
    scene_round: "SceneRound",
    declared_ids: set[int],
) -> bool:
    """Return True when a hostile party drove THIS round against a downed victim.

    A downed victim's acute peril (e.g. Bleeding Out) advances on the END tick only
    while "the encounter that downed them is still acting." That is true when the
    character who inflicted the peril (``ConditionInstance.source_character``) is a
    participant of this round who declared this round — i.e. their participant pk is
    in ``declared_ids`` (the snapshot taken before declarations are resolved/deleted).

    ``declared_ids`` is the set of SceneRoundParticipant pks with a deferred
    declaration this round (``round_services.resolve_scene_round`` builds it).
    """
    source_ids = _acute_peril_source_ids(victim_sheet)
    if not source_ids:
        return False

    from world.scenes.models import SceneRoundParticipant  # noqa: PLC0415

    source_participant_ids = set(
        SceneRoundParticipant.objects.filter(
            scene_round=scene_round,
            character_sheet__character_id__in=source_ids,
        ).values_list("pk", flat=True)
    )
    return bool(source_participant_ids & declared_ids)


def potential_rescuer_present(
    victim_sheet: "CharacterSheet",
    room: "ObjectDB",  # noqa: OBJECTDB_PARAM
    *,
    exclude_character_id: int | None = None,
) -> bool:
    """Return True when someone present could plausibly stabilize the downed victim.

    A potential rescuer is any character in ``room`` who is conscious (``can_act``),
    is NOT the victim, and is NOT the hostile source of the victim's peril (an
    ally/neutral bystander). The abandonment marker is only stamped when such a
    rescuer exists — if nobody could help, "abandoned" is not the right framing.

    ``exclude_character_id`` omits one further character from the rescuer set —
    used by the solo-departure path (``Room.at_object_leave`` fires while the
    mover is still in ``room.contents``, so the departing character must not be
    counted as a remaining rescuer). Thin wrapper over the shared
    ``conscious_bystander_present`` core (#1813); the hostile-source exclusion is
    resolved here (not moved into the shared helper) since it is specific to acute
    peril's involved-party classification.
    """
    from world.vitals.services import conscious_bystander_present  # noqa: PLC0415

    source_ids = _acute_peril_source_ids(victim_sheet)
    exclude_ids = frozenset(
        source_ids | ({exclude_character_id} if exclude_character_id is not None else set())
    )
    return conscious_bystander_present(
        room, subject_id=victim_sheet.character_id, exclude_ids=exclude_ids
    )


def mark_abandoned(victim_sheet: "CharacterSheet", scene_round: "SceneRound") -> None:
    """Stamp ``abandoned_since_round`` on the victim's acute-peril instances (once).

    Only stamps when a potential rescuer is present (see ``potential_rescuer_present``)
    and never overwrites an existing stamp — the marker records the FIRST round the
    victim was left to hold, not the latest.
    """
    room = victim_sheet.character.location
    if room is None or not potential_rescuer_present(victim_sheet, room):
        return
    for inst in acute_peril_instances(victim_sheet).filter(abandoned_since_round__isnull=True):
        inst.abandoned_since_round = scene_round.round_number
        inst.save(update_fields=["abandoned_since_round"])


def clear_abandoned(victim_sheet: "CharacterSheet") -> None:
    """Clear ``abandoned_since_round`` — a hostile party is driving the round again."""
    for inst in acute_peril_instances(victim_sheet).filter(abandoned_since_round__isnull=False):
        inst.abandoned_since_round = None
        inst.save(update_fields=["abandoned_since_round"])


def is_pc_source(source_character: "ObjectDB | None") -> bool:  # noqa: OBJECTDB_PARAM
    """Return True when source_character is a player-controlled character.

    Uses the canonical PC-detection convention: a character is player-controlled
    iff ``character.db_account`` is not None (mirrors ``_persona_is_npc`` in
    ``world.scenes.action_services``). Returns False for None sources.
    """
    if source_character is None:
        return False
    return source_character.db_account is not None


def death_is_permitted(
    *,
    victim_sheet: "CharacterSheet",
    source_character: "ObjectDB | None",  # noqa: OBJECTDB_PARAM
) -> bool:
    """Return True only when death is a structurally valid outcome.

    Returns False (not permitted) when ANY of:
    - source_character is None (absent/non-lethal environmental context).
    - source_character is a PC (ADR-0023: PvP is non-lethal).
    - The victim carries an active death_deferred condition.
    - The victim is story-critical and the source is not a participant (#1874).

    Returns True only for a non-PC source with no active death_deferred on
    the victim and no story-criticality protection (i.e. a significant-NPC
    attacker in a lethal encounter, where the victim is not load-bearing
    for any active story).
    """
    if source_character is None:
        return False

    if is_pc_source(source_character):
        return False

    from world.conditions.services import has_death_deferred  # noqa: PLC0415

    if has_death_deferred(victim_sheet.character):
        return False

    from world.stories.npc_protection import (  # noqa: PLC0415
        is_death_prevented_by_story,
    )

    if is_death_prevented_by_story(victim_sheet, source_character):
        return False

    return True


def select_abandonment_pool(
    source_character: "ObjectDB | None",  # noqa: OBJECTDB_PARAM
) -> "ConsequencePool":
    """Return the abandonment ConsequencePool appropriate for the source type.

    Routes to one of three pre-authored pools by source character kind:
    - PC source → ``abandonment_pvp`` pool (ADR-0023: die row filtered at runtime).
    - Non-PC (NPC) source → ``abandonment_enemy`` pool.
    - None source → ``abandonment_environmental`` pool.

    The pools must be seeded in the database (via
    ``world.vitals.factories.create_abandonment_pools``) before this
    function is called.  Raises ``ConsequencePool.DoesNotExist`` if the
    named pool is absent — treat that as a seeding gap, not a logic error.
    """
    from actions.models import ConsequencePool  # noqa: PLC0415
    from world.vitals.constants import (  # noqa: PLC0415
        POOL_ABANDONMENT_ENEMY,
        POOL_ABANDONMENT_ENVIRONMENTAL,
        POOL_ABANDONMENT_PVP,
    )

    if is_pc_source(source_character):
        pool_name = POOL_ABANDONMENT_PVP
    elif source_character is not None:
        pool_name = POOL_ABANDONMENT_ENEMY
    else:
        pool_name = POOL_ABANDONMENT_ENVIRONMENTAL

    return ConsequencePool.objects.get(name=pool_name)
