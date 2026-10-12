"""Declare-action services for flee, cover, items, interpose, and social verbs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.errors import ActionDispatchError
from world.combat.constants import CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.fatigue.constants import EffortLevel
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.combat.models import CombatMark
    from world.items.models import ItemInstance
    from world.magic.models import Technique


def declare_flee(participant: CombatParticipant) -> CombatRoundAction:
    """Declare intent to flee -- passives-only maneuver, auto-ready.

    Creates or replaces the current round's CombatRoundAction with no
    focused action and maneuver=FLEE. Flee resolves as a real check at
    round resolution (_resolve_flee); the participant remains ACTIVE until
    the check succeeds.
    """
    from world.combat.berserk_compulsion import reject_if_berserk  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    reject_if_berserk(participant, "flee")
    encounter = participant.encounter

    # Encounter status check
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot flee: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot flee: participant is no longer active in this encounter."
        raise ValueError(msg)

    # Vitality check — dead characters cannot flee. Unconscious / dying
    # characters may still be dragged out (flee is passives-only).
    if is_dead(participant.character_sheet):
        msg = "Cannot flee: character is dead."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.FLEE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def toggle_action_ready(action: CombatRoundAction) -> CombatRoundAction:
    """Flip the ready flag on a round action and persist it.

    Extracted from the inline toggle that lived in the web ``ready`` endpoint so
    both the telnet/web shared ``ReadyAction`` and any caller use one code path.
    """
    action.is_ready = not action.is_ready
    action.save(update_fields=["is_ready"])
    return action


def declare_cover(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a covering maneuver for an ally -- passives-only, auto-ready.

    Cover resolves as a no-op on its own; its effect is the FleeConfig
    cover_bonus it contributes to the ally's flee check in _resolve_flee.
    Covering an ally who never declares flee simply wastes the action.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot cover: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot cover: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot cover: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot cover yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Cover target must be an active participant in this encounter."
        raise ValueError(msg)
    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.COVER,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_use_item(
    participant: CombatParticipant,
    item_instance: ItemInstance,
    *,
    target: CombatParticipant | CombatOpponent | None = None,
) -> CombatRoundAction:
    """Declare using a held on-use item as this round's action (#2023, #2120).

    Unlike FLEE/COVER (passives-only), USE_ITEM is a primary maneuver -- it is
    mutually exclusive with a declared focused technique, consuming the round's
    action slot. ``target`` may be a ``CombatParticipant`` (ally/self target) or
    a ``CombatOpponent`` (enemy target); it is resolved into
    ``focused_ally_target``/``focused_opponent_target`` respectively, reusing
    the existing FK slots rather than adding a new field. Resolution
    (``_resolve_use_item``) dispatches the existing ``UseItemAction`` machinery.
    """
    from flows.object_states.item_state import ItemState  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot use item: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot use item: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot use item: character is dead."
        raise ValueError(msg)

    character = participant.character_sheet.character
    # Same wrap-without-context call HoldsItemPrerequisite uses for possession checks.
    item_state = ItemState(item_instance, context=None)  # ty: ignore[invalid-argument-type]
    if not item_state.is_in_possession(character):
        msg = "Cannot use item: you aren't holding it."
        raise ValueError(msg)

    ally_target: CombatParticipant | None = None
    opponent_target: CombatOpponent | None = None
    if isinstance(target, CombatParticipant):
        if target.encounter_id != encounter.pk or target.status != ParticipantStatus.ACTIVE:
            msg = "Use-item target must be an active participant in this encounter."
            raise ValueError(msg)
        ally_target = target
    elif isinstance(target, CombatOpponent):
        if target.encounter_id != encounter.pk or target.status != OpponentStatus.ACTIVE:
            msg = "Use-item target must be an active opponent in this encounter."
            raise ValueError(msg)
        opponent_target = target
    elif target is not None:
        msg = "Invalid use-item target type."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent_target,
            "focused_ally_target": ally_target,
            "maneuver": CombatManeuver.USE_ITEM,
            "item_instance": item_instance,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def resolve_cast_position_params(
    participant: CombatParticipant,
    technique: Technique,
    position_params: dict[str, int],
) -> dict[str, Position | None]:
    """Validate declared cast positions against the encounter's room + technique reach.

    ``position_params`` is the raw dispatch payload — either a single
    ``destination_position_id`` (single-position techniques such as Phase Jump /
    Force Grip / zone hazards) or a ``position_a_id``/``position_b_id`` pair
    (Barricade-style two-endpoint techniques). Both shapes are optional and
    mutually independent; an empty/absent ``position_params`` resolves to all-None.

    Raises ``ActionDispatchError`` (mirroring the existing ally-target /
    positional-reach error path used elsewhere in this module):

    - ``UNKNOWN_ACTION_REF`` — a supplied position id does not resolve to a
      ``Position`` in the encounter's own room, the a/b pair is only
      half-supplied, or the a/b pair is identical (a barrier needs two
      different endpoints).
    - ``TARGET_OUT_OF_REACH`` — the declared destination is beyond
      ``technique.reach`` from the caster's current position. Skipped when the
      caster is unplaced (no current_position) — lenient, same rationale as
      ``_validate_technique_reach``.
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import position_reachable  # noqa: PLC0415

    room = participant.encounter.room
    resolved: dict[str, Position | None] = {
        "cast_destination": None,
        "cast_position_a": None,
        "cast_position_b": None,
    }

    def _get(pk: int) -> Position:
        pos = Position.objects.filter(pk=pk, room=room).first()
        if pos is None:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        return pos

    dest_id = position_params.get("destination_position_id")
    if dest_id:
        dest = _get(dest_id)
        origin = participant.current_position
        if origin is not None and not position_reachable(
            origin, dest, technique.reach, reach_hops=technique.reach_hops
        ):
            raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)
        resolved["cast_destination"] = dest

    a_id = position_params.get("position_a_id")
    b_id = position_params.get("position_b_id")
    if bool(a_id) != bool(b_id):
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
    if a_id and b_id:
        if a_id == b_id:
            # A barrier needs two different endpoints — reject a degenerate pair
            # before it ever reaches the resolver.
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        resolved["cast_position_a"] = _get(a_id)
        resolved["cast_position_b"] = _get(b_id)

    return resolved


def _validate_redirect_declaration(
    encounter: CombatEncounter,
    redirect_opponent_target: CombatOpponent | None,
    redirect_object_target: ObjectDB | None,  # noqa: OBJECTDB_PARAM
) -> None:
    """Validate a redirect declaration's destination kwargs (#2210).

    Extracted from :func:`declare_interpose` to keep its complexity in check.
    Mutually exclusive; each populated kwarg is validated against the
    encounter it's being declared into. Both ``None`` ("away") needs no
    validation.
    """
    from world.mechanics.services import volatile_object_property  # noqa: PLC0415

    if redirect_opponent_target is not None and redirect_object_target is not None:
        msg = "Cannot interpose: choose at most one redirect destination."
        raise ValueError(msg)

    if redirect_opponent_target is not None and (
        redirect_opponent_target.encounter_id != encounter.pk
        or redirect_opponent_target.status != OpponentStatus.ACTIVE
    ):
        msg = "Redirect target must be an active opponent in this encounter."
        raise ValueError(msg)

    if redirect_object_target is not None:
        if redirect_object_target.db_location_id != encounter.room_id:
            msg = "Redirect target must be an object in the encounter room."
            raise ValueError(msg)
        if volatile_object_property(redirect_object_target) is None:
            msg = "Redirect target is not volatile."
            raise ValueError(msg)


def declare_interpose(  # noqa: PLR0913 - interpose declaration requires all redirect/consent fields
    participant: CombatParticipant,
    ally: CombatParticipant | None = None,
    technique: Technique | None = None,
    redirect_opponent_target: CombatOpponent | None = None,
    redirect_object_target: ObjectDB | None = None,  # noqa: OBJECTDB_PARAM
    *,
    confirm_soulfray_risk: bool = False,
) -> CombatRoundAction:
    """Declare an interposing maneuver — passives-only, auto-ready.

    ``ally=None`` means the participant will guard any ally hit this round;
    when a specific ally is given they must be active and in the same encounter.

    ``technique=None`` (default) declares a plain interpose exactly as before
    #2207 — passives only, ``focused_action`` zeroed. Supplying a *technique*
    carries a protective reactive-trigger technique into the declaration: the
    participant must know it (``CharacterTechnique``) and it must classify to a
    protective flavor via ``protective_flavor`` (barrier/blink/redirect,
    `world/magic/services/targeting.py`).

    ``redirect_opponent_target``/``redirect_object_target`` (#2210) declare the
    destination for saved damage when the guardian's technique resolves as a
    REDIRECT flavor (Mirror Ward-style reflection) — declaration-time choice
    per ADR-0032. Mutually exclusive; both ``None`` means "away," the universal
    fallback destination. ``redirect_opponent_target`` must be an active
    (not-defeated) opponent in this same encounter. ``redirect_object_target``
    must be an ObjectDB located in the encounter's room AND "volatile" — it
    carries an ``ObjectProperty`` whose ``Property`` has a ``PropertyDetonation``
    row (see ``world.mechanics.services.volatile_object_property``). These
    kwargs are accepted regardless of the declared technique's flavor (harmless
    no-ops for non-REDIRECT declarations); resolution
    (``_try_technique_interpose``) only reads them on the REDIRECT branch.

    ``confirm_soulfray_risk`` (#3573) records the guardian's consent to keep the
    reaction firing past zero anima at the cost of Soulfray; read by
    ``_try_technique_interpose``.
    """
    from world.magic.models import CharacterTechnique  # noqa: PLC0415
    from world.magic.services.targeting import protective_flavor  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot interpose: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot interpose: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot interpose: character is dead."
        raise ValueError(msg)

    if ally is not None:
        if ally.pk == participant.pk:
            msg = "Cannot interpose yourself."
            raise ValueError(msg)
        if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
            msg = "Interpose target must be an active participant in this encounter."
            raise ValueError(msg)

    if technique is not None:
        knows_technique = CharacterTechnique.objects.filter(
            character=participant.character_sheet,
            technique=technique,
        ).exists()
        if not knows_technique:
            msg = "Cannot interpose: character does not know that technique."
            raise ValueError(msg)
        flavor = protective_flavor(technique)
        if flavor is None:
            msg = "Cannot interpose: that technique cannot guard yet."
            raise ValueError(msg)

    _validate_redirect_declaration(encounter, redirect_opponent_target, redirect_object_target)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": technique,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.INTERPOSE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "redirect_opponent_target": redirect_opponent_target,
            "redirect_object_target": redirect_object_target,
            "confirm_soulfray_risk": confirm_soulfray_risk,
        },
    )
    return action


def declare_mark(
    participant: CombatParticipant,
    opponent: CombatOpponent,
    *,
    technique: Technique | None = None,
) -> CombatMark:
    """Declare a mark — a directed, round-scoped combatant reference (#2664).

    A participant declares a target opponent for covenant-mates to focus.
    The mark persists for the round; old marks are ignored (query-scoped by
    ``round_number``). Generic combat primitive — vow content (perks, rungs)
    reads the mark via the ``TARGET_IS_MARKED_BY_ALLY`` situation evaluator.

    Validations mirror ``declare_interpose``: encounter must be in DECLARING
    status, participant must be ACTIVE, opponent must be ACTIVE and in the
    same encounter. Idempotent per round: re-declaring updates the same row.
    """
    from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
    from world.combat.models import CombatMark  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot mark: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot mark: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot mark: character is dead."
        raise ValueError(msg)

    if opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot mark a defeated or fled opponent."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk:
        msg = "Cannot mark: opponent is not in this encounter."
        raise ValueError(msg)

    mark, _ = CombatMark.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "encounter": encounter,
            "opponent": opponent,
            "source_technique": technique,
        },
    )
    return mark


def declare_succor(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a sheltering maneuver for a specific ally — passives-only, auto-ready.

    Unlike Interpose (which can guard "any ally" against whichever attack lands),
    Succor always names a specific ally: environmental shelter is "I'm sheltering
    THIS person," not "I'll block whichever hazard lands on someone." Resolution
    happens later, at round-tick DoT application (#1744).
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot succor: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot succor: participant is no longer active in this encounter."
        raise ValueError(msg)
    if is_dead(participant.character_sheet):
        msg = "Cannot succor: character is dead."
        raise ValueError(msg)
    if ally.pk == participant.pk:
        msg = "Cannot succor yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Succor target must be an active participant in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.VERY_LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.SUCCOR,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
            "succor_resolution": None,
        },
    )
    return action


def declare_rally(
    participant: CombatParticipant,
    ally: CombatParticipant,
) -> CombatRoundAction:
    """Declare a rallying maneuver — inspire an ally, auto-ready (#2015).

    RALLY rolls a presence/Performance check at round-tick; on success it applies
    a short-lived ``Inspired`` condition to the ally (a damage-multiplier buff) and,
    on a great success, restores morale to ally-side summon opponents. This
    function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot rally: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot rally: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot rally: character is dead."
        raise ValueError(msg)

    if ally.pk == participant.pk:
        msg = "Cannot rally yourself."
        raise ValueError(msg)
    if ally.encounter_id != encounter.pk or ally.status != ParticipantStatus.ACTIVE:
        msg = "Rally target must be an active participant in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": None,
            "focused_ally_target": ally,
            "maneuver": CombatManeuver.RALLY,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_demoralize(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a demoralizing maneuver — break an opponent's nerve, auto-ready (#2015).

    DEMORALIZE rolls a presence/Persuasion(Intimidation) check at round-tick against
    the target's Composure; on success it depletes the target's morale. Mindless
    opponents resist (not immune). This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot demoralize: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot demoralize: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot demoralize: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Demoralize target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.DEMORALIZE,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action


def declare_taunt(
    participant: CombatParticipant,
    opponent: CombatOpponent,
) -> CombatRoundAction:
    """Declare a taunting maneuver — draw an NPC's aggro, auto-ready (#2015).

    TAUNT rolls a wits/Persuasion(Intimidation) check at round-tick against the
    target's Composure; on success it accumulates threat on the existing
    ``ThreatRecord`` seam, biasing the NPC's target selection toward the taunter.
    This function only records the declaration.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot taunt: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)

    if participant.status != ParticipantStatus.ACTIVE:
        msg = "Cannot taunt: participant is no longer active in this encounter."
        raise ValueError(msg)

    if is_dead(participant.character_sheet):
        msg = "Cannot taunt: character is dead."
        raise ValueError(msg)

    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Taunt target must be an active opponent in this encounter."
        raise ValueError(msg)

    action, _ = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": None,
            "effort_level": EffortLevel.LOW,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.TAUNT,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": True,
        },
    )
    return action
