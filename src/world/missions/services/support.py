"""Support-moves service — the fan and declare pipeline (#2046).

A support move is a non-routing sibling surface fanned from a helper's own
gifts (capabilities via the ownership oracle, plus predicate-tree legs
for distinction/trait combos). Patterns auto-match the node's live CHECK
options; authored gems add to or suppress patterns. A declaration takes
the place of the helper's pick/vote in the group flow.

The fan reuses the capability oracle (``get_effective_capability_value``)
exactly as ``challenge_options_for_character`` does, and the sanctioned
predicate evaluator (``evaluate`` + ``CharacterPredicateContext``) exactly
as ``MissionOption.visibility_rule`` does — no new qualification logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from world.checks.consequence_resolution import apply_resolution
from world.checks.services import perform_check
from world.checks.types import ResolutionContext
from world.conditions.services import get_effective_capability_value
from world.missions.types import SupportMove
from world.predicates.predicates import CharacterPredicateContext, evaluate

_ERR_NOT_PARTICIPANT = "You are not part of that mission."
_ERR_NODE_RESOLVED = "That beat has already resolved."
_ERR_ALREADY_DECLARED = "You have already declared support at this beat."
_ERR_CAP_REACHED = "The party has reached the support declaration cap for this beat."
_ERR_NO_SNAPSHOT = "No active snapshot found for this participant at this node."
_ERR_UNKNOWN_SOURCE = "Unknown support source kind: {kind}"

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.covenants.perks.context import SituationContext
    from world.missions.models import (
        MissionAssistPattern,
        MissionInstance,
        MissionNode,
        MissionNodeSnapshot,
        MissionNodeSupportOption,
        MissionParticipant,
        MissionSupportDeclaration,
    )


def _qualifier_passes(
    capability_id: int | None,
    qualifier_rule: dict,
    character: ObjectDB,
) -> bool:
    """Check whether a support move's qualifier passes for ``character``.

    Capability leg: the character must hold the capability (>0 effective value
    via ``get_effective_capability_value``). Predicate leg: the sanctioned
    predicate tree evaluated via ``CharacterPredicateContext``. A move must
    have at least one leg (DB CHECK constraint enforces this at write time).
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415

    cap_ok = True
    if capability_id is not None:
        cap = CapabilityType.objects.get(pk=capability_id)
        cap_ok = get_effective_capability_value(character.sheet_data, cap) > 0

    pred_ok = (
        evaluate(qualifier_rule, CharacterPredicateContext(character)) if qualifier_rule else True
    )
    return cap_ok and pred_ok


def _node_check_type_ids(node: MissionNode) -> set[int]:
    """The set of CheckType pks the node's CHECK options reference.

    AUTHORED CHECK options use ``authored_check_type``; CHALLENGE options
    use their approaches' ``check_type``. This is the context-match axis
    for patterns.
    """
    check_type_ids: set[int] = set()
    for option in node.options.all():
        if option.authored_check_type_id is not None:
            check_type_ids.add(option.authored_check_type_id)
        if option.challenge_id is not None:
            for approach in option.challenge.approaches.all():
                if approach.check_type_id is not None:
                    check_type_ids.add(approach.check_type_id)
    return check_type_ids


def _node_challenge_category_ids(node: MissionNode) -> set[int]:
    """The set of ChallengeCategory pks the node's CHALLENGE options reference."""
    cat_ids: set[int] = set()
    for option in node.options.filter(challenge__isnull=False).select_related("challenge"):
        if option.challenge.category_id is not None:
            cat_ids.add(option.challenge.category_id)
    return cat_ids


def support_moves_for(
    instance: MissionInstance,  # noqa: ARG001
    node: MissionNode,
    character: ObjectDB,
) -> list[SupportMove]:
    """Surface the support moves available to ``character`` at ``node``.

    Gems whose qualifier passes are offered first. Unless a gem with
    ``suppress_patterns`` exists, active patterns whose context matches
    the node's live CHECK options (check_types and/or challenge_categories)
    and whose qualifier passes are also offered. Rumored-but-unqualified
    moves return as tease-only entries.

    The list is per-viewer: each participant sees only their own qualifying
    moves (plus rumored teases), mirroring how option lists work today.
    """
    from world.missions.models import MissionAssistPattern  # noqa: PLC0415

    moves: list[SupportMove] = []

    # --- Authored gems ---
    gems = list(node.support_options.all())
    suppress = any(gem.suppress_patterns for gem in gems)

    for gem in gems:
        qualifies = _qualifier_passes(gem.capability_id, gem.qualifier_rule, character)
        is_rumored = bool(gem.rumor_text)
        if not qualifies and not is_rumored:
            continue
        moves.append(
            SupportMove(
                source_id=gem.pk,
                source_kind="gem",
                label=gem.flavor_template or "Support",
                capability_name=gem.capability.name if gem.capability_id else None,
                check_type_name=gem.support_check_type.name,
                difficulty=gem.difficulty,
                easing=gem.easing,
                flavor=gem.flavor_template,
                rumored=is_rumored and not qualifies,
                rumor_text=gem.rumor_text,
            )
        )

    # --- Pattern catalog (unless suppressed) ---
    if not suppress:
        node_ct_ids = _node_check_type_ids(node)
        node_cat_ids = _node_challenge_category_ids(node)

        patterns = (
            MissionAssistPattern.objects.filter(is_active=True)
            .prefetch_related("check_types")  # noqa: PREFETCH_STRING
            .prefetch_related("challenge_categories")  # noqa: PREFETCH_STRING
        )
        for pattern in patterns:
            # Context match: at least one check_type or challenge_category
            # axis matches. A pattern with neither axis matches nowhere
            # (explicit, no globals).
            pattern_ct_ids = {ct.pk for ct in pattern.check_types.all()}
            pattern_cat_ids = {cc.pk for cc in pattern.challenge_categories.all()}
            if not pattern_ct_ids and not pattern_cat_ids:
                continue
            ct_match = bool(pattern_ct_ids & node_ct_ids)
            cat_match = bool(pattern_cat_ids & node_cat_ids)
            if not (ct_match or cat_match):
                continue

            qualifies = _qualifier_passes(pattern.capability_id, pattern.qualifier_rule, character)
            is_rumored = bool(pattern.rumor_text)
            if not qualifies and not is_rumored:
                continue
            moves.append(
                SupportMove(
                    source_id=pattern.pk,
                    source_kind="pattern",
                    label=pattern.name,
                    capability_name=(pattern.capability.name if pattern.capability_id else None),
                    check_type_name=pattern.support_check_type.name,
                    difficulty=pattern.difficulty,
                    easing=pattern.easing,
                    flavor=pattern.flavor_template,
                    rumored=is_rumored and not qualifies,
                    rumor_text=pattern.rumor_text,
                )
            )

    return moves


def _mission_situation_ctx(
    character: ObjectDB, instance: MissionInstance
) -> SituationContext | None:
    """The ``SituationContext`` for a mission check by ``character`` in ``instance``
    (#2536 slice 3 Court wiring). ``None`` when the character has no
    ``CharacterSheet`` — mirrors the guard ``_situational_perk_check_bonus`` applies
    itself, so a checker without a sheet is byte-identical to the pre-#2536 default.
    """
    from world.covenants.perks.context import SituationContext  # noqa: PLC0415

    try:
        sheet = character.sheet_data
    except (ObjectDoesNotExist, AttributeError):
        return None
    return SituationContext(
        holder=sheet, subject=sheet, target=None, resolution=None, mission=instance
    )


def _participant_or_raise(instance: MissionInstance, character: ObjectDB) -> MissionParticipant:
    """Return the participant row or raise BeatActionError."""
    from world.missions.services.play import BeatActionError  # noqa: PLC0415

    participant = instance.participants.filter(character=character).first()
    if participant is None:
        raise BeatActionError(_ERR_NOT_PARTICIPANT)
    return participant


def _resolve_move_source(
    source_kind: str,
    source_id: int,
) -> MissionAssistPattern | MissionNodeSupportOption:
    """Look up the support move source by kind and id."""
    from world.missions.services.play import BeatActionError  # noqa: PLC0415

    if source_kind == "pattern":  # noqa: STRING_LITERAL
        from world.missions.models import MissionAssistPattern  # noqa: PLC0415

        return MissionAssistPattern.objects.get(pk=source_id)
    if source_kind == "gem":  # noqa: STRING_LITERAL
        from world.missions.models import MissionNodeSupportOption  # noqa: PLC0415

        return MissionNodeSupportOption.objects.get(pk=source_id)
    raise BeatActionError(_ERR_UNKNOWN_SOURCE.format(kind=source_kind))


def _roll_and_bank(  # noqa: PLR0913
    instance: MissionInstance,
    node: MissionNode,
    character: ObjectDB,
    participant: MissionParticipant,
    snapshot: MissionNodeSnapshot,
    move: MissionAssistPattern | MissionNodeSupportOption,
    source_kind: str,
) -> MissionSupportDeclaration:
    """Guard, roll, bank easing, fire complication, mint deed + declaration."""
    from world.checks.consequence_resolution import (  # noqa: PLC0415
        PendingResolution,
    )
    from world.missions.models import (  # noqa: PLC0415
        MissionDeedRecord,
        MissionSupportDeclaration,
    )
    from world.missions.services.play import BeatActionError  # noqa: PLC0415

    with transaction.atomic():
        if MissionSupportDeclaration.objects.filter(snapshot=snapshot).exists():
            raise BeatActionError(_ERR_ALREADY_DECLARED)
        existing_count = MissionSupportDeclaration.objects.filter(
            instance=instance, snapshot__node=node
        ).count()
        if existing_count >= node.max_support:
            raise BeatActionError(_ERR_CAP_REACHED)

        result = perform_check(
            character,
            move.support_check_type,
            target_difficulty=move.difficulty,
            situation_ctx=_mission_situation_ctx(character, instance),
        )
        is_success = result.success_level >= 1
        easing_banked = move.easing if is_success else 0

        if not is_success and move.complication_consequence_id is not None:
            context = ResolutionContext(
                character=character,
                mission_instance=instance,
            )
            apply_resolution(
                PendingResolution(result, move.complication_consequence),
                context,
            )

        first_option = node.options.first()
        MissionDeedRecord.objects.create(
            instance=instance,
            actor=character,
            node=node,
            option=first_option,
            outcome=result.outcome,
        )

        decl_kwargs: dict[str, object] = {
            "instance": instance,
            "snapshot": snapshot,
            "participant": participant,
            "outcome": result.outcome,
            "easing_banked": easing_banked,
        }
        if source_kind == "pattern":  # noqa: STRING_LITERAL
            decl_kwargs["pattern"] = move
        else:
            decl_kwargs["support_option"] = move
        return MissionSupportDeclaration.objects.create(**decl_kwargs)


def declare_support(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    source_kind: str,
    source_id: int,
) -> MissionSupportDeclaration:
    """Declare a support move, roll the check, and bank easing or fire complication.

    Guards (participant, node unresolved, no existing declaration, cap)
    inside ``transaction.atomic``. Rolls ``perform_check`` at the move's
    difficulty. On success banks easing; on failure fires the complication
    consequence (if any) on the helper via the existing consequence pipeline.
    Mints the helper's ``MissionDeedRecord`` and emits per-actor STORY prose
    + room ambient stir.

    A declaration takes the place of the helper's pick/vote in the group
    flow.
    """
    from world.missions.models import MissionNodeSnapshot  # noqa: PLC0415
    from world.missions.services.play import BeatActionError  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import (  # noqa: PLC0415
        emit_ambient_room_stir,
        send_narrative_message,
    )

    participant = _participant_or_raise(instance, character)
    node = instance.current_node
    if node is None or instance.status != "active":  # noqa: STRING_LITERAL
        raise BeatActionError(_ERR_NODE_RESOLVED)

    move = _resolve_move_source(source_kind, source_id)

    snapshot = (
        MissionNodeSnapshot.objects.filter(instance=instance, node=node, participant=participant)
        .order_by("-taken_at")
        .first()
    )
    if snapshot is None:
        raise BeatActionError(_ERR_NO_SNAPSHOT)

    declaration = _roll_and_bank(
        instance, node, character, participant, snapshot, move, source_kind
    )

    # Emit per-actor STORY + room ambient stir (outside atomic, like group
    # resolution so narrative side-effects don't roll back with a retry).
    from world.missions.models import MissionAssistPattern  # noqa: PLC0415

    move_label = (
        (move.name if isinstance(move, MissionAssistPattern) else "")
        or move.flavor_template
        or "Support"
    )
    story_text = move.flavor_template or f"Support declared: {move_label}"
    try:
        sheet = character.sheet_data
    except AttributeError:
        sheet = None
    if sheet is not None:
        send_narrative_message(
            recipients=[sheet],
            body=story_text,
            category=NarrativeCategory.STORY,
            ooc_note=f"Mission support declared (instance #{instance.pk}).",
        )
    anchor_room = instance.anchor_room
    if anchor_room is not None:
        emit_ambient_room_stir(anchor_room)

    return declaration
