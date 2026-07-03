"""Handlers for applying consequence effects from challenge resolution."""

import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.checks.constants import EffectTarget, EffectType
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge
from world.conditions.services import apply_condition, remove_condition
from world.magic.constants import AlterationTier
from world.mechanics.models import ObjectProperty
from world.mechanics.types import AppliedEffect
from world.roster.models import RosterEntry
from world.vitals.services import process_damage_consequences

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.positioning.models import Position
    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence, ConsequenceEffect
    from world.checks.types import ResolutionContext
    from world.magic.models import Affinity, Resonance

logger = logging.getLogger(__name__)

_SKIP_ATTACK = "Attack system not yet implemented."
_NO_SHEET_DESCRIPTION = "Target has no character sheet"
_NO_SHEET_SKIP_REASON = "Target has no CharacterSheet"

# Role constants for _resolve_position — discriminate named-lookup variants.
_ROLE_DESTINATION = "destination"
_ROLE_NAMED = "named"
_ROLE_NAMED_B = "named_b"


def apply_effect(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Dispatch a single ConsequenceEffect and return the result."""
    handler = _HANDLER_REGISTRY.get(effect.effect_type)
    if handler is None:
        return AppliedEffect(
            effect_type=effect.effect_type,
            description="",
            applied=False,
            skip_reason=f"No handler for effect type {effect.effect_type}",
        )
    return handler(effect, context)


def apply_all_effects(
    consequence: "Consequence",
    context: "ResolutionContext",
) -> list[AppliedEffect]:
    """Apply all effects on a consequence. Returns empty list for unsaved consequences."""
    if consequence.pk is None:
        return []
    effects = consequence.effects.all().order_by("execution_order")
    return [apply_effect(e, context) for e in effects]


def _resolve_target(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> "ObjectDB":
    """Resolve the target ObjectDB for an effect based on EffectTarget."""
    if effect.target == EffectTarget.TARGET:
        return context.target if context.target is not None else context.character
    if effect.target == EffectTarget.LOCATION:
        return context.location
    return context.character


# ---------------------------------------------------------------------------
# Individual effect handlers
# ---------------------------------------------------------------------------


def _apply_condition(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply a condition to the resolved target."""
    target = _resolve_target(effect, context)
    severity = effect.condition_severity or 1
    apply_condition(
        target,
        effect.condition_template,
        severity=severity,
        source_character=context.source_character,
    )
    condition_name = effect.condition_template.name
    return AppliedEffect(
        effect_type=EffectType.APPLY_CONDITION,
        description=f"Applied {condition_name} (severity {severity}) to {target.db_key}",
        applied=True,
    )


def _remove_condition(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Remove a condition from the resolved target."""
    target = _resolve_target(effect, context)
    removed = remove_condition(target, effect.condition_template)
    condition_name = effect.condition_template.name
    if removed:
        description = f"Removed {condition_name} from {target.db_key}"
    else:
        description = f"{condition_name} was not present on {target.db_key}"
    return AppliedEffect(
        effect_type=EffectType.REMOVE_CONDITION,
        description=description,
        applied=True,
    )


def _set_relationship_condition(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Set a directed relationship-condition: the TARGET becomes attracted to the actor (#1697).

    The actor (``context.character``) is the one found attractive; the effect's TARGET becomes
    Attracted To them, so the directed relationship is ``source=target, target=actor`` — exactly the
    direction ``relationship_gated_contributions`` reads. A null duration is permanent, a set
    duration is temporary (Very Attracted).
    """
    from world.relationships.services import add_relationship_condition  # noqa: PLC0415

    actor = context.character
    recipient = _resolve_target(effect, context)
    try:
        actor_sheet = actor.sheet_data
        recipient_sheet = recipient.sheet_data
    except ObjectDoesNotExist:
        return AppliedEffect(
            effect_type=EffectType.SET_RELATIONSHIP_CONDITION,
            description="Actor or target has no character sheet; skipped.",
            applied=False,
            skip_reason="missing_sheet",
        )
    if recipient_sheet.pk == actor_sheet.pk:
        return AppliedEffect(
            effect_type=EffectType.SET_RELATIONSHIP_CONDITION,
            description="Actor and target are the same character; skipped.",
            applied=False,
            skip_reason="self_target",
        )
    add_relationship_condition(
        source=recipient_sheet,
        target=actor_sheet,
        condition=effect.relationship_condition,
        duration=effect.relationship_condition_duration,
    )
    condition_name = effect.relationship_condition.name
    return AppliedEffect(
        effect_type=EffectType.SET_RELATIONSHIP_CONDITION,
        description=f"{recipient.db_key} is now '{condition_name}' toward {actor.db_key}",
        applied=True,
    )


def _add_property(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Add or update an ObjectProperty on the resolved target."""
    target = _resolve_target(effect, context)
    value = effect.property_value or 1
    obj_prop, _ = ObjectProperty.objects.update_or_create(
        object=target,
        property=effect.property,
        defaults={"value": value},
    )
    prop_name = effect.property.name
    return AppliedEffect(
        effect_type=EffectType.ADD_PROPERTY,
        description=f"Added property {prop_name} ({value}) to {target.db_key}",
        applied=True,
        created_instance=obj_prop,
    )


def _remove_property(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Remove an ObjectProperty from the resolved target."""
    target = _resolve_target(effect, context)
    deleted_count, _ = ObjectProperty.objects.filter(
        object=target,
        property=effect.property,
    ).delete()
    prop_name = effect.property.name
    if deleted_count:
        description = f"Removed property {prop_name} from {target.db_key}"
    else:
        description = f"Property {prop_name} was not present on {target.db_key}"
    return AppliedEffect(
        effect_type=EffectType.REMOVE_PROPERTY,
        description=description,
        applied=True,
    )


def _deal_damage(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Apply damage to target's health and trigger survivability pipeline."""
    if not effect.damage_amount or effect.damage_amount <= 0:
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="No damage to deal",
            applied=False,
            skip_reason="Damage amount is zero or negative",
        )

    target = _resolve_target(effect, context)
    if target is None:
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="No target to damage",
            applied=False,
            skip_reason="Target not found",
        )

    try:
        vitals = target.sheet_data.vitals
    except (AttributeError, ObjectDoesNotExist):
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="Target has no vitals",
            applied=False,
            skip_reason="Target has no CharacterVitals",
        )

    from world.conditions.services import resolve_damage_type_resistance  # noqa: PLC0415
    from world.magic.services import apply_damage_reduction_from_threads  # noqa: PLC0415

    damage_amount = effect.damage_amount
    if hasattr(target, "threads"):
        damage_amount = apply_damage_reduction_from_threads(target, damage_amount)
    # Damage-type resistance (condition + gift-thread) via the shared seam (#1588).
    # Closes the asymmetry where traps ignored a character's damage-type resistance.
    damage_amount = resolve_damage_type_resistance(target, damage_amount, effect.damage_type)
    if damage_amount <= 0:
        return AppliedEffect(
            effect_type=EffectType.DEAL_DAMAGE,
            description="Damage fully absorbed by thread survivability",
            applied=False,
            skip_reason="Reduced to zero",
        )

    vitals.health -= damage_amount
    vitals.save(update_fields=["health"])

    process_damage_consequences(
        character_sheet=target.sheet_data,
        damage_dealt=damage_amount,
        damage_type=effect.damage_type,
    )

    damage_type_name = effect.damage_type.name if effect.damage_type else "untyped"
    return AppliedEffect(
        effect_type=EffectType.DEAL_DAMAGE,
        description=f"Dealt {damage_amount} {damage_type_name} damage",
        applied=True,
    )


def _launch_attack(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",  # noqa: ARG001
) -> AppliedEffect:
    """Stub handler for attack effects — awaiting combat system."""
    return AppliedEffect(
        effect_type=EffectType.LAUNCH_ATTACK,
        description=f"Would launch attack with {effect.damage_type.name}",
        applied=False,
        skip_reason=_SKIP_ATTACK,
    )


def _launch_flow(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Launch a flow from a consequence effect. Flow engine exists but has no runtime data."""
    flow_name = effect.flow_definition.name if effect.flow_definition else "unknown"
    logger.info(
        "Flow effect triggered: %s for character %s",
        flow_name,
        context.character.db_key,
    )
    return AppliedEffect(
        effect_type=EffectType.LAUNCH_FLOW,
        description=f"Launched flow {flow_name}",
        applied=True,
    )


def _grant_codex(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Grant a codex entry to the character via their RosterEntry."""
    character = context.character
    try:
        roster_entry = character.sheet_data.roster_entry
    except RosterEntry.DoesNotExist:
        return AppliedEffect(
            effect_type=EffectType.GRANT_CODEX,
            description="Character has no roster entry",
            applied=False,
            skip_reason="Character has no roster entry",
        )

    _, created = CharacterCodexKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        entry=effect.codex_entry,
        defaults={"status": CodexKnowledgeStatus.UNCOVERED},
    )
    entry_name = effect.codex_entry.name
    if created:
        description = f"Granted codex entry: {entry_name}"
    else:
        description = f"Codex entry already known: {entry_name}"
    return AppliedEffect(
        effect_type=EffectType.GRANT_CODEX,
        description=description,
        applied=True,
    )


def _tier_multiplier(success_level: int) -> float:
    """Clamped multiplier from a CheckOutcome's success_level.

    1.0 baseline (no bonus for non-positive tiers); +0.2 per point of positive
    success_level, so a max +10 tier is worth 3.0x. Deliberately simple and
    reused nowhere else — tune this curve during implementation review against
    real CheckOutcome rows if the numbers don't feel right in play.
    """
    return 1.0 + max(0, success_level) / 5


def _legend_award(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Award legend to all participants listed in context.

    Reads ``context.participants`` (must be non-empty) and calls
    ``create_legend_event``, which also fans out covenant credits via
    ``credit_engaged_covenants`` (Task 4).

    Magnitude: when both ``context.beat`` and ``context.outcome_tier`` are
    present (the graded beat-completion path), the award scales by risk x
    performance: ``RISK_LEGEND_AWARDS[effective_risk] * tier_multiplier(outcome_tier
    .success_level)``, floored by ``effect.legend_base_value`` (an author's
    explicit override never gets scaled down — see Decision 4, #1716). When
    either is absent (a hand-fired GM deed outside the beat pipeline, or any
    pre-existing caller), the award is the flat ``effect.legend_base_value``,
    unchanged from prior behavior.

    ``effective_risk`` comes from ``effective_risk_for_beat`` (#1770): the beat's
    open ``StakeContractActivation`` when one exists (auto-downgrade for
    over/under-leveled parties + target-level pricing), else ``Beat.risk``
    unchanged. The completion tail resolves the activation only after this
    handler runs, so the open activation's effective risk is still visible here.

    Description fallback chain:
      1. ``effect.legend_description_template`` (if non-blank)
      2. ``context.beat.player_resolution_text`` (if beat present and non-blank)
      3. ``"Legendary deed"`` (generic fallback)
    """
    from world.societies.constants import RISK_LEGEND_AWARDS  # noqa: PLC0415
    from world.societies.exceptions import LegendAwardParticipantMissingError  # noqa: PLC0415
    from world.societies.services import create_legend_event  # noqa: PLC0415

    if not context.participants:
        raise LegendAwardParticipantMissingError

    base_value = effect.legend_base_value
    if context.beat is not None and context.outcome_tier is not None:
        from world.stories.services.stakes import effective_risk_for_beat  # noqa: PLC0415

        risk_award = RISK_LEGEND_AWARDS[effective_risk_for_beat(context.beat)]
        multiplier = _tier_multiplier(context.outcome_tier.success_level)
        base_value = max(base_value, round(risk_award * multiplier))

    fallback_text = (
        context.beat.player_resolution_text
        if context.beat is not None and context.beat.player_resolution_text
        else "Legendary deed"
    )
    description = effect.legend_description_template or fallback_text
    # LegendEvent.title has max_length=200 (AbstractLegendRecord).
    title = description[:200]

    event, entries = create_legend_event(
        title,
        effect.legend_source_type,
        base_value,
        list(context.participants),
        description=description,
        scene=context.scene,
        story=context.story,
    )
    return AppliedEffect(
        effect_type=EffectType.LEGEND_AWARD,
        description=(f"Awarded {base_value} legend to {len(entries)} participant(s)"),
        applied=True,
        created_instance=event,
    )


def _severity_to_tier(severity: int) -> int:
    """Map a condition_severity value to an AlterationTier integer (clamped 1–5)."""
    valid_tiers = {t.value for t in AlterationTier}
    if severity in valid_tiers:
        return severity
    if severity < min(valid_tiers):
        return min(valid_tiers)
    return max(valid_tiers)


def _derive_alteration_origin(
    character: "ObjectDB",
) -> "tuple[Affinity | None, Resonance | None]":
    """Derive origin affinity and resonance from the character's resonances.

    Picks the most recently earned CharacterResonance for the character via the
    ``character.resonances`` handler (Spec A §3.7). Returns (None, None) if the
    character has no sheet or no resonance rows — callers must handle this case
    by skipping pending alteration creation.
    """
    try:
        sheet = character.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None, None
    if sheet is None:
        return None, None
    char_res = character.resonances.most_recently_earned()
    if char_res is None:
        return None, None
    return char_res.resonance.affinity, char_res.resonance


def _apply_magical_scars(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Create a PendingAlteration the player must later resolve.

    Does NOT apply any condition directly. The character's most-recently-earned
    resonance provides the origin affinity and resonance — the scar marks come
    from their magical essence. If the character has no sheet or no resonance
    rows, the handler skips gracefully and returns applied=False.
    """
    from world.magic.services import create_pending_alteration  # noqa: PLC0415

    target = _resolve_target(effect, context)

    try:
        sheet: CharacterSheet = target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return AppliedEffect(
            effect_type=EffectType.MAGICAL_SCARS,
            description=_NO_SHEET_DESCRIPTION,
            applied=False,
            skip_reason=_NO_SHEET_SKIP_REASON,
        )

    affinity, resonance = _derive_alteration_origin(target)
    if affinity is None or resonance is None:
        return AppliedEffect(
            effect_type=EffectType.MAGICAL_SCARS,
            description="Target has no resonance — cannot determine alteration origin",
            applied=False,
            skip_reason="No CharacterResonance found",
        )

    severity = effect.condition_severity or 1
    tier = _severity_to_tier(severity)

    result = create_pending_alteration(
        character=sheet,
        tier=tier,
        origin_affinity=affinity,
        origin_resonance=resonance,
        scene=None,  # Deferred: thread scene through ResolutionContext when available
    )

    verb = "escalated" if not result.created else "acquired"
    return AppliedEffect(
        effect_type=EffectType.MAGICAL_SCARS,
        description=f"Magical alteration {verb}: tier {tier} pending for {target.db_key}",
        applied=True,
    )


def _capture_group_key(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> str | None:
    """Stable key grouping captives of one capture event into a shared cell.

    Keyed on the resolution's scene (the encounter's location handle the
    context reliably carries) plus the captor org, so the same captor taking
    several PCs in one scene shares a cell, while different captors — or no
    scene at all — fall back to separate cells.
    """
    scene = context.scene
    if scene is None:
        return None
    captor_part = effect.capture_captor_organization_id or "none"
    return f"capture:scene:{scene.pk}:{captor_part}"


def _apply_capture(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Take the resolved target into captivity (#931).

    Fires the captivity service from any consequence pool — combat aftermath,
    a mission route, a magical mishap — without that author touching the
    captivity internals. The capture site (``context.location``) becomes the
    cell's return location. Skips gracefully if the target has no sheet or is
    already held, so a capture consequence never crashes a resolution.
    """
    from world.captivity.exceptions import AlreadyCapturedError  # noqa: PLC0415
    from world.captivity.services import capture_character, resolve_capture_setup  # noqa: PLC0415

    target = _resolve_target(effect, context)
    try:
        sheet = target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return AppliedEffect(
            effect_type=EffectType.CAPTURE,
            description=_NO_SHEET_DESCRIPTION,
            applied=False,
            skip_reason=_NO_SHEET_SKIP_REASON,
        )

    # Per-capture override layered over the one CaptivityConfig default — cell flavor,
    # the captive's loop, the rescue mission, and the rescue-clue text (#931 Phase 4).
    setup = resolve_capture_setup(
        captive_template=effect.capture_captive_template,
        rescue_template=effect.capture_rescue_template,
        cell_name=effect.capture_cell_name,
        cell_description=effect.capture_cell_description,
        clue_name=effect.capture_clue_name,
        clue_description=effect.capture_clue_description,
        clue_detect_difficulty=effect.capture_clue_detect_difficulty,
    )

    try:
        captivity = capture_character(
            captive=sheet,
            captor_organization=effect.capture_captor_organization,
            # The captive's own location is the capture site they return to —
            # not context.location (the caster's room), which differs for a
            # TARGET capture. target.location may be None; the service allows it.
            return_location=target.location,
            offscreen_loss_allowed=effect.capture_offscreen_loss_allowed,
            # Empty string → let the spawner fall back to its placeholder flavor.
            cell_name=setup.cell_name or None,
            cell_description=setup.cell_description or None,
            # Captives taken in one encounter (same scene + captor) share a
            # cell — the shared-cell default, honoured on the per-character
            # consequence path. No scene → per-character cells (group_key None).
            group_key=_capture_group_key(effect, context),
        )
    except AlreadyCapturedError:
        return AppliedEffect(
            effect_type=EffectType.CAPTURE,
            description=f"{target.db_key} is already a captive",
            applied=False,
            skip_reason="Target already held",
        )

    # Hand the captive their own loop from inside the cell — the escape +
    # get-word-out options on the resolved (override-then-default) template.
    # No template authored yet → no loop granted; capture still stands.
    if setup.captive_template is not None:
        from world.missions.services.run import grant_captive_mission  # noqa: PLC0415

        grant_captive_mission(setup.captive_template, target)

    # Stamp the rescue mission and plant a discoverable rescue clue at the capture
    # site, so allies who search there are handed the rescue (#931 Phase 4).
    _setup_rescue_discovery(captivity, setup)

    return AppliedEffect(
        effect_type=EffectType.CAPTURE,
        description=f"Captured {target.db_key}",
        applied=True,
    )


def _gating_far_side(
    effect: "ConsequenceEffect",  # noqa: ARG001
    context: "ResolutionContext",
) -> "Position | None":
    """Return the far side of the gating edge the actor is currently crossing.

    Reads context.challenge_instance; finds the edge whose gating_challenge
    is that instance; returns the endpoint that is NOT the actor's current
    position. Returns None if context has no challenge_instance, the actor
    has no position, or no matching edge is found.
    """
    from world.areas.positioning.services import position_of  # noqa: PLC0415

    if context.challenge_instance is None:
        return None
    actor_pos = position_of(context.character)
    if actor_pos is None:
        return None
    edges = context.challenge_instance.gated_position_edges.select_related(
        "position_a", "position_b"
    )
    for edge in edges:
        if edge.position_a_id == actor_pos.pk:
            return edge.position_b
        if edge.position_b_id == actor_pos.pk:
            return edge.position_a
    return None


def _resolve_position(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
    *,
    role: str,
) -> "Position | None":
    """Resolve a Position within the actor's room for a positioning effect.

    role="destination" uses effect.position_destination; role="named" looks up
    effect.position_name by name in the room; role="named_b" uses position_name_b.
    Returns None when unresolved (handler skips).
    """
    from world.areas.positioning.models import Position  # noqa: PLC0415

    room = context.location
    if role == _ROLE_NAMED:
        return Position.objects.filter(room=room, name=effect.position_name).first()
    if role == _ROLE_NAMED_B:
        return Position.objects.filter(room=room, name=effect.position_name_b).first()
    return _resolve_destination(effect, context)


def _resolve_destination(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> "Position | None":
    """Dispatch role="destination" on effect.position_destination."""
    from world.areas.positioning.models import Position  # noqa: PLC0415
    from world.areas.positioning.services import position_of  # noqa: PLC0415
    from world.checks.constants import PositionDestination  # noqa: PLC0415

    room = context.location
    dest = effect.position_destination
    if dest == PositionDestination.ACTOR_POSITION:
        return position_of(context.character)
    if dest == PositionDestination.NAMED:
        return Position.objects.filter(room=room, name=effect.position_name).first()
    if dest == PositionDestination.GATING_FAR_SIDE:
        return _gating_far_side(effect, context)
    if dest == PositionDestination.AWAY_FROM_ACTOR:
        return _resolve_away_from_actor(effect, context)
    return None


def _resolve_away_from_actor(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> "Position | None":
    """Resolve a knockback destination: a Position adjacent to the TARGET that
    is not itself adjacent to the actor (i.e. actually puts distance between
    them). Deterministic tie-break by lowest pk. Returns None if either side
    lacks a Position, the target has no valid neighbor to be pushed into, or
    the target resists via the ``sure_footed`` Capability (#1793) — same
    no-op semantics as every other early return here.
    """
    from world.areas.positioning.services import (  # noqa: PLC0415
        adjacent_open_positions,
        position_of,
    )

    target = _resolve_target(effect, context)
    if target.has_capability("sure_footed"):
        return None
    actor_pos = position_of(context.character)
    target_pos = position_of(target)
    if actor_pos is None or target_pos is None:
        return None

    target_edges = adjacent_open_positions(target_pos)
    neighbors = [
        e.position_b if e.position_a_id == target_pos.pk else e.position_a for e in target_edges
    ]
    if not neighbors:
        return None

    actor_neighbor_ids = {
        e.position_b_id if e.position_a_id == actor_pos.pk else e.position_a_id
        for e in adjacent_open_positions(actor_pos)
    }
    away = [p for p in neighbors if p.pk not in actor_neighbor_ids and p.pk != actor_pos.pk]
    candidates = away or neighbors
    return min(candidates, key=lambda p: p.pk)


def _create_position(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Create a new Position in the actor's room and optionally connect/place occupant."""
    from world.areas.positioning.constants import PositionKind  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        connect_positions,
        create_position,
        force_move_to_position,
        maybe_emit_fall,
        position_of,
    )

    room = context.location
    kind = effect.position_kind or PositionKind.FEATURE
    new_pos = create_position(
        room,
        effect.position_name,
        kind=kind,
        description=effect.position_description,
    )
    actor_pos = position_of(context.character)
    if effect.position_connect_from_actor and actor_pos is not None:
        connect_positions(actor_pos, new_pos)
    if effect.position_place_occupant:
        occupant = _resolve_target(effect, context)
        force_move_to_position(occupant, new_pos)
        maybe_emit_fall(occupant, new_pos)
    return AppliedEffect(
        effect_type=EffectType.CREATE_POSITION,
        description=f"Created position {new_pos.name} in {room.db_key}",
        applied=True,
        created_instance=new_pos,
    )


def _sever_edge(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Remove the edge between two named positions in the actor's room."""
    from world.areas.positioning.services import disconnect_positions, edge_between  # noqa: PLC0415

    a = _resolve_position(effect, context, role=_ROLE_NAMED)
    b = _resolve_position(effect, context, role=_ROLE_NAMED_B)
    if a is None or b is None or edge_between(a, b) is None:
        return AppliedEffect(
            effect_type=EffectType.SEVER_EDGE,
            description="No edge to sever",
            applied=False,
            skip_reason="Endpoints/edge not found",
        )
    disconnect_positions(a, b)
    return AppliedEffect(
        effect_type=EffectType.SEVER_EDGE,
        description=f"Severed edge {a.name}<->{b.name}",
        applied=True,
    )


def _connect_edge(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Create an edge between two named positions in the actor's room (idempotent)."""
    from world.areas.positioning.services import connect_positions, edge_between  # noqa: PLC0415

    a = _resolve_position(effect, context, role=_ROLE_NAMED)
    b = _resolve_position(effect, context, role=_ROLE_NAMED_B)
    if a is None or b is None:
        return AppliedEffect(
            effect_type=EffectType.CONNECT_EDGE,
            description="Endpoints not found",
            applied=False,
            skip_reason="Named endpoints not found",
        )
    if edge_between(a, b) is None:
        connect_positions(a, b)
    return AppliedEffect(
        effect_type=EffectType.CONNECT_EDGE,
        description=f"Connected {a.name}<->{b.name}",
        applied=True,
    )


def _move_to_position(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Move the resolved target to the destination position."""
    from world.areas.positioning.services import (  # noqa: PLC0415
        force_move_to_position,
        maybe_emit_fall,
    )

    target = _resolve_target(effect, context)
    destination = _resolve_position(effect, context, role=_ROLE_DESTINATION)
    if destination is None:
        return AppliedEffect(
            effect_type=EffectType.MOVE_TO_POSITION,
            description="No destination resolved",
            applied=False,
            skip_reason="Destination position could not be resolved",
        )
    force_move_to_position(target, destination)
    maybe_emit_fall(target, destination)
    return AppliedEffect(
        effect_type=EffectType.MOVE_TO_POSITION,
        description=f"Moved {target.db_key} to {destination.name}",
        applied=True,
    )


def _setup_rescue_discovery(captivity: object, setup: object) -> None:
    """Stamp the rescue mission on the captivity and plant its discovery clue (#931).

    Skips when there is no rescue mission (nothing to discover), no authored clue text
    (the GM declined the discoverable clue — the rescue can still be granted by other
    means), or the capture site has no room profile to anchor the clue to.
    """
    if setup.rescue_template is None:
        return
    captivity.rescue_template = setup.rescue_template
    captivity.save(update_fields=["rescue_template"])
    if not setup.clue_name:
        return
    cell = captivity.cell
    return_location = cell.return_location if cell is not None else None
    if return_location is None:
        return

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.clues.services import plant_rescue_clue  # noqa: PLC0415

    try:
        room_profile = return_location.room_profile
    except RoomProfile.DoesNotExist:
        return
    plant_rescue_clue(
        captivity,
        room_profile,
        name=setup.clue_name,
        description=setup.clue_description,
        detect_difficulty=setup.clue_detect_difficulty,
    )


def _apply_escape_captivity(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Free the resolved target from their own captivity (#931 Phase 4).

    The terminal effect of a captive's escape option: a success route attaches
    this, and the captive walks. Skips gracefully if the target has no sheet or
    isn't currently held (a stale or double-fired route), so it never crashes a
    resolution. The ally-side sibling is the rescue route's RESCUE handling.
    """
    from world.captivity.services import escape_captivity  # noqa: PLC0415

    target = _resolve_target(effect, context)
    try:
        sheet = target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return AppliedEffect(
            effect_type=EffectType.ESCAPE_CAPTIVITY,
            description=_NO_SHEET_DESCRIPTION,
            applied=False,
            skip_reason=_NO_SHEET_SKIP_REASON,
        )

    if not escape_captivity(sheet):
        return AppliedEffect(
            effect_type=EffectType.ESCAPE_CAPTIVITY,
            description=f"{target.db_key} is not currently held",
            applied=False,
            skip_reason="Target not held",
        )

    return AppliedEffect(
        effect_type=EffectType.ESCAPE_CAPTIVITY,
        description=f"{target.db_key} escaped captivity",
        applied=True,
    )


def _grant_flight(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Move the resolved target to the aerial layer above their current position."""
    from world.areas.positioning.services import enter_aerial  # noqa: PLC0415

    target = _resolve_target(effect, context)
    enter_aerial(target)
    return AppliedEffect(
        effect_type=EffectType.GRANT_FLIGHT,
        description=f"{target.db_key} took to the air",
        applied=True,
    )


def _remove_flight(
    effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Return the resolved target from the aerial layer back to the ground."""
    from world.areas.positioning.services import leave_aerial  # noqa: PLC0415

    target = _resolve_target(effect, context)
    leave_aerial(target)
    return AppliedEffect(
        effect_type=EffectType.REMOVE_FLIGHT,
        description=f"{target.db_key} returned to the ground",
        applied=True,
    )


def _apply_rescue_captive(
    _effect: "ConsequenceEffect",
    context: "ResolutionContext",
) -> AppliedEffect:
    """Free the run's ``rescue_target`` from captivity (#931 Phase 4 rescue).

    The terminal effect of a rescue run's success route: it reaches the captive
    through the resolving ``MissionInstance.rescue_target`` (carried on the
    context), not the acting character — the rescuer frees someone else. Skips
    gracefully off the mission path, on a non-rescue run, or when the target is
    no longer held (already freed / escaped), so it never crashes a resolution.
    The captive-side sibling is :data:`EffectType.ESCAPE_CAPTIVITY`.
    """
    from world.captivity.services import rescue_captive  # noqa: PLC0415

    instance = context.mission_instance
    captive = instance.rescue_target if instance is not None else None
    if captive is None:
        return AppliedEffect(
            effect_type=EffectType.RESCUE_CAPTIVE,
            description="No rescue target on this resolution",
            applied=False,
            skip_reason="No rescue_target in context",
        )

    if not rescue_captive(captive):
        return AppliedEffect(
            effect_type=EffectType.RESCUE_CAPTIVE,
            description="Rescue target is not currently held",
            applied=False,
            skip_reason="Rescue target not held",
        )

    return AppliedEffect(
        effect_type=EffectType.RESCUE_CAPTIVE,
        description=f"Freed captive {captive.pk}",
        applied=True,
    )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLER_REGISTRY: dict[str, type[None] | object] = {
    EffectType.APPLY_CONDITION: _apply_condition,
    EffectType.REMOVE_CONDITION: _remove_condition,
    EffectType.SET_RELATIONSHIP_CONDITION: _set_relationship_condition,
    EffectType.ADD_PROPERTY: _add_property,
    EffectType.REMOVE_PROPERTY: _remove_property,
    EffectType.DEAL_DAMAGE: _deal_damage,
    EffectType.LAUNCH_ATTACK: _launch_attack,
    EffectType.LAUNCH_FLOW: _launch_flow,
    EffectType.GRANT_CODEX: _grant_codex,
    EffectType.MAGICAL_SCARS: _apply_magical_scars,
    EffectType.LEGEND_AWARD: _legend_award,
    EffectType.CAPTURE: _apply_capture,
    EffectType.ESCAPE_CAPTIVITY: _apply_escape_captivity,
    EffectType.RESCUE_CAPTIVE: _apply_rescue_captive,
    EffectType.CREATE_POSITION: _create_position,
    EffectType.MOVE_TO_POSITION: _move_to_position,
    EffectType.SEVER_EDGE: _sever_edge,
    EffectType.CONNECT_EDGE: _connect_edge,
    EffectType.GRANT_FLIGHT: _grant_flight,
    EffectType.REMOVE_FLIGHT: _remove_flight,
}
