"""Unified player action availability and dispatch — merges challenge, combat, and registry.

``get_player_actions`` is the single read path for the action picker UI.  It is
recomputed on every call (no caching) so that GM-spawned challenges and encounter
state changes appear immediately on the next request.

``dispatch_player_action`` is the single write path.  It validates the incoming
``ActionRef`` against the character's *current* availability (security + stale-ref
recovery), then either:
- defers the action as a round declaration (when a DECLARING round is active), or
- dispatches immediately to the appropriate backend resolver.

Backend resolution:
- CHALLENGE  -- delegates to ``world.mechanics.services.get_available_actions``; adapts
  each ``AvailableAction`` (which already carries resolved ``resolved_check_type`` and
  ``resolved_action_template`` instances populated by the prefetch chain) into a
  ``PlayerAction``.
- COMBAT      -- only when ``get_active_round_context`` returns a ``RoundContext``
  whose ``is_declaration_open`` is ``True``; enumerates the character's known
  techniques that have an ``action_template`` (= combat-usable techniques) and
  emits one ``PlayerAction`` per technique.  Also emits clash-contribution
  ``PlayerAction``s for each ``ACTIVE`` clash in the participant's encounter: one
  ``FOCUSED`` slot and one ``PASSIVE`` slot per clash, per the design spec (§4 —
  every PC in the encounter sees every active clash; POV-filter is post-positioning).
- REGISTRY    -- ``get_actions_for_target_type`` returns registry ``Action`` singletons;
  these have no ``ActionTemplate`` / ``check_type`` so ALL current registry actions are
  excluded from ``get_player_actions``.  ``dispatch_player_action`` still handles REGISTRY
  refs for immediate execution (no declaration gating needed for utility actions).

Registry exclusion note:
  Every registry ``Action`` in ``actions.registry`` is a pure Python singleton with no
  database model and no associated ``ActionTemplate``.  The ``PlayerAction`` descriptor
  requires a resolved ``CheckType`` instance (the unifying resolution anchor), which
  cannot be provided for registry actions until they are backed by ``ActionTemplate``
  rows.  They are excluded rather than emitted with a placeholder to avoid confusing the
  dispatch layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.registry import get_action
from actions.round_context import get_active_round_context
from actions.types import ActionRef, DispatchResult, PlayerAction
from world.magic.models import CharacterTechnique
from world.mechanics.services import get_available_actions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.mechanics.types import AvailableAction


def dispatch_player_action(
    character: ObjectDB,
    ref: ActionRef,
    kwargs: dict[str, Any],
) -> DispatchResult:
    """Route a chosen action to the correct backend, declaration-gated when a round is active.

    Validates the incoming ``ref`` against the character's *current* availability —
    not trusting client-supplied ids directly.  This is both the stale/forged-ref
    safety property and the mechanism for recovering the resolved model instances
    needed by each backend.

    Args:
        character: The character's ``ObjectDB`` instance performing the action.
        ref: The typed dispatch reference echoed from the client.
        kwargs: Backend-specific dispatch parameters (e.g. ``effort_level`` for COMBAT).

    Returns:
        A ``DispatchResult`` indicating whether the action was deferred (round
        declaration) or executed immediately, plus any immediate result detail.

    Raises:
        ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if the ref does not match
            any currently-available action for this character.
        ActionDispatchError: With ``ROUND_DECLARATION_CLOSED`` if a round is active
            but the declaration window has already closed (propagated from
            ``record_declaration``).
    """
    sheet = _get_character_sheet(character)

    # Step 1: get the active round context (None if not in an active round).
    # We pass the sheet; fall back gracefully if no sheet (REGISTRY still works).
    ctx = get_active_round_context(sheet) if sheet is not None else None

    # REGISTRY: validate the key exists; no round gating — always immediate.
    if ref.backend == ActionBackend.REGISTRY:
        action_obj = get_action(ref.registry_key or "")
        if action_obj is None:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        result = action_obj.run(actor=character, **kwargs)
        return DispatchResult(backend=ActionBackend.REGISTRY, deferred=False, detail=result)

    # Step 2: recover authoritative resolution inputs (validates ref against current availability).
    if ref.backend == ActionBackend.CHALLENGE:
        avail = _find_available_action_for_ref(character, ref)
        player_action = _avail_to_player_action(avail)

    else:
        # COMBAT: only surfaced during a DECLARING round; no round = invalid ref.
        if ctx is None or not ctx.is_declaration_open:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        player_action = _find_combat_player_action_for_ref(character, ref)
        avail = None  # COMBAT doesn't use AvailableAction

    # Step 3: route — declaration-gated or immediate.
    declaration_open = ctx is not None and ctx.is_declaration_open
    if declaration_open:
        # Declaration window is open — defer to round resolution.
        ctx.record_declaration(sheet, player_action, kwargs)  # type: ignore[arg-type] — sheet is non-None: ctx only exists when a sheet resolved
        return DispatchResult(backend=ref.backend, deferred=True)

    # Immediate CHALLENGE resolution.
    # avail is guaranteed non-None here: COMBAT without a round context raised above;
    # CHALLENGE always sets avail; REGISTRY returned early.
    if avail is None:  # defensive: should be unreachable
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    # Deferred import: challenge_resolution imports actions.services; top-level would cycle.
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415

    resolution = resolve_challenge(
        character,
        avail.resolved_challenge_instance,  # type: ignore[arg-type]
        avail.resolved_challenge_approach,  # type: ignore[arg-type]
        avail.capability_source,
    )
    return DispatchResult(backend=ActionBackend.CHALLENGE, deferred=False, detail=resolution)


def get_player_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return all available ``PlayerAction`` descriptors for *character*.

    Merges the challenge, combat, and registry backends into a single homogeneous
    list.  Recomputed on every call — no caching.

    Args:
        character: The character's ``ObjectDB`` instance (the game object, not
            ``CharacterSheet``).  The character's ``db_location`` is used to look
            up active challenges.

    Returns:
        A list of ``PlayerAction`` instances sorted by backend then by their
        natural order within each backend.  Never ``None``; empty list if no
        actions are available.
    """
    actions: list[PlayerAction] = []

    actions.extend(_challenge_actions(character))
    actions.extend(_combat_actions(character))
    actions.extend(_clash_contribution_actions(character))
    # Registry backend: all current actions excluded (no ActionTemplate / check_type)
    # — see module docstring.  When registry actions gain ActionTemplate backing,
    # uncomment and implement _registry_actions(character).

    return actions


# ---------------------------------------------------------------------------
# Private backend adapters
# ---------------------------------------------------------------------------


def _challenge_actions(character: ObjectDB) -> list[PlayerAction]:
    """Adapt ``AvailableAction`` list from the mechanics service into ``PlayerAction``s."""
    location = character.db_location  # ObjectDB.db_location (FK)
    if location is None:
        return []

    available = get_available_actions(character, location)
    result: list[PlayerAction] = []

    for avail in available:
        if avail.resolved_check_type is None:
            # Defensive: should not happen because _match_approaches always populates
            # resolved_check_type, but skip gracefully if it ever does.
            continue
        result.append(_avail_to_player_action(avail))

    return result


def _combat_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return COMBAT ``PlayerAction``s when the character is in an active declaring round.

    Only produces actions when:
    1. The character has a ``CharacterSheet`` (required to resolve combat participation).
    2. ``get_active_round_context`` returns a ``RoundContext`` with
       ``is_declaration_open == True`` (encounter in DECLARING phase).

    Candidate set: techniques the character knows that are combat-usable
    (``technique.action_template is not None``).  This is the SAME gate
    ``DeclareActionSerializer.validate`` enforces — availability surfaces
    candidates only; authoritative per-target / passive-slot / status
    validation happens at declare/dispatch time (``DeclareActionSerializer.validate``
    / ``CombatRoundContext.record_declaration``).
    """
    # Resolve CharacterSheet from the character ObjectDB
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []

    ctx = get_active_round_context(sheet)
    if ctx is None or not ctx.is_declaration_open:
        return []

    # Enumerate techniques the character knows that have an action_template.
    # select_related ensures no per-technique queries for action_template + check_type.
    grants = CharacterTechnique.objects.filter(
        character=sheet,
        technique__action_template__isnull=False,
    ).select_related(
        "technique",
        "technique__action_template",
        "technique__action_template__check_type",
    )

    result: list[PlayerAction] = []
    for grant in grants:
        technique = grant.technique
        template = technique.action_template  # guaranteed non-None: queryset filters isnull=False
        check_type = template.check_type
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.COMBAT,
                check_type=check_type,
                display_name=technique.name,
                ref=ref,
                action_template=template,
            )
        )

    return result


def _clash_contribution_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return COMBAT ``PlayerAction``s for each active clash in the character's encounter.

    For each ``ACTIVE`` clash the character's encounter contains, emits TWO descriptors:
    one ``FOCUSED`` slot and one ``PASSIVE`` slot.  The PC picks which to commit at
    declaration time (via ``declare_clash_contribution``); surfacing both lets the UI
    present the choice.

    If the PC has already submitted a ``ClashContributionDeclaration`` for a given
    clash this round, we still emit both slot descriptors (v1: no suppression).
    The frontend can highlight which slot is already declared and allow re-declaration
    until the round resolves.

    POV note (spec §4): every PC in the encounter sees every active clash.
    v1 has no positioning, so this is intentional — all PCs are potential contributors.

    ``check_type`` is ``None`` on these descriptors: the check type is determined by
    whichever technique the PC selects at declaration time, not at opportunity-surfacing
    time.  Clash contributions surface the *opportunity*, not the *mechanism*.

    ActionRef encoding
    ------------------
    Each descriptor carries an ``ActionRef`` with ``backend=COMBAT``,
    ``clash_id=<Clash.pk>``, and ``clash_action_slot=<ClashActionSlot value>``.
    A future dispatcher reads these fields to route to ``declare_clash_contribution``.
    """
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []

    # Clash contribution declarations are only meaningful during DECLARING phase —
    # same gate as _combat_actions.  Return early if the window is closed.
    ctx = get_active_round_context(sheet)
    if ctx is None or not ctx.is_declaration_open:
        return []

    # Deferred imports: keep the actions package free of combat models at the top level.
    from world.combat.constants import (  # noqa: PLC0415
        ClashActionSlot,
        ClashStatus,
        EncounterStatus,
        ParticipantStatus,
    )
    from world.combat.models import Clash, CombatParticipant  # noqa: PLC0415

    # Find an active participant in a non-completed encounter.
    participant = (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__status__in={
                EncounterStatus.DECLARING,
                EncounterStatus.RESOLVING,
                EncounterStatus.BETWEEN_ROUNDS,
            },
        )
        .select_related("encounter")
        .order_by("-encounter__created_at")
        .first()
    )
    if participant is None:
        return []

    encounter = participant.encounter

    active_clashes = list(
        Clash.objects.filter(
            encounter=encounter,
            status=ClashStatus.ACTIVE,
        ).select_related("npc_opponent")
    )
    if not active_clashes:
        return []

    result: list[PlayerAction] = []
    for clash in active_clashes:
        opponent_name = clash.npc_opponent.name
        flavor_label = clash.get_flavor_display()
        progress_summary = f"Progress: {clash.progress} / {clash.pc_win_threshold} (PC target)"

        for slot in (ClashActionSlot.FOCUSED, ClashActionSlot.PASSIVE):
            if slot == ClashActionSlot.FOCUSED:
                display_name = f"Commit to {flavor_label}: {opponent_name}"
                description = (
                    f"Use your focused action slot to contribute to this clash. {progress_summary}."
                )
            else:
                display_name = f"Lend strength to {flavor_label}: {opponent_name}"
                description = (
                    f"Use your passive action slot to support this clash. {progress_summary}."
                )

            ref = ActionRef(
                backend=ActionBackend.COMBAT,
                clash_id=clash.pk,
                clash_action_slot=slot.value,
            )
            result.append(
                PlayerAction(
                    backend=ActionBackend.COMBAT,
                    display_name=display_name,
                    description=description,
                    ref=ref,
                    # check_type is None: technique chosen at declaration time determines the check.
                    check_type=None,
                    # v1: every PC in the encounter sees every active clash (POV-filter is
                    # post-positioning; see spec §4).
                    prerequisite_met=True,
                    prerequisite_reasons=[],
                )
            )

    return result


def _find_available_action_for_ref(character: ObjectDB, ref: ActionRef) -> AvailableAction:
    """Find the ``AvailableAction`` matching *ref* from the character's current availability.

    Calls ``get_available_actions`` (the canonical challenge-availability computation)
    and matches by ``(challenge_instance_id, approach_id)``.  Raises
    ``ActionDispatchError(UNKNOWN_ACTION_REF)`` if no match — this is the stale/forged-ref
    safety property: a player can only dispatch an action currently available to them.

    Carries resolved model instances on the returned ``AvailableAction`` — no additional
    queries needed to recover ``resolve_challenge`` inputs.

    Args:
        character: The character's ``ObjectDB`` instance.
        ref: The incoming CHALLENGE ``ActionRef`` carrying the ids to match.

    Returns:
        The matching ``AvailableAction`` with ``resolved_challenge_instance`` and
        ``resolved_challenge_approach`` populated.

    Raises:
        ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if no match found.
    """
    location = character.db_location
    if location is None:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    available = get_available_actions(character, location)
    for avail in available:
        if (
            avail.challenge_instance_id == ref.challenge_instance_id
            and avail.approach_id == ref.approach_id
        ):
            return avail

    raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)


def _avail_to_player_action(avail: AvailableAction) -> PlayerAction:
    """Build a ``PlayerAction`` from an ``AvailableAction`` (DRY with ``_challenge_actions``).

    Shared adapter used by both ``_challenge_actions`` (for the availability read path)
    and ``dispatch_player_action`` (for the deferred declaration path).  Raises
    ``ActionDispatchError(UNKNOWN_ACTION_REF)`` if ``resolved_check_type`` is missing
    (defensive; should not happen for a validly-matched ``AvailableAction``).

    Args:
        avail: A matched ``AvailableAction`` from ``get_available_actions``.

    Returns:
        A ``PlayerAction`` suitable for passing to ``record_declaration``.
    """
    check_type = avail.resolved_check_type
    if check_type is None:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    ref = ActionRef(
        backend=ActionBackend.CHALLENGE,
        challenge_instance_id=avail.challenge_instance_id,
        approach_id=avail.approach_id,
    )
    return PlayerAction(
        backend=ActionBackend.CHALLENGE,
        check_type=check_type,
        display_name=avail.display_name,
        ref=ref,
        action_template=avail.resolved_action_template,
        description=avail.custom_description,
        difficulty=avail.difficulty_indicator,
        prerequisite_met=avail.prerequisite_met,
        prerequisite_reasons=avail.prerequisite_reasons,
    )


def _find_combat_player_action_for_ref(character: ObjectDB, ref: ActionRef) -> PlayerAction:
    """Find the COMBAT ``PlayerAction`` matching *ref* from the character's current availability.

    Calls ``get_player_actions(character)`` and matches by ``ref.technique_id``.  This
    reuses the same availability gate as the read path — only surfaced techniques are
    dispatchable.  Raises ``ActionDispatchError(UNKNOWN_ACTION_REF)`` if not matched.

    Args:
        character: The character's ``ObjectDB`` instance.
        ref: The incoming COMBAT ``ActionRef`` carrying the technique id to match.

    Returns:
        The matching ``PlayerAction``.

    Raises:
        ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if no matching COMBAT action found.
    """
    # Clash-contribution dispatch is deferred: the read path emits clash PlayerActions
    # (via _clash_contribution_actions), but the write/dispatch path hasn't been wired
    # yet — that is Task 7.x / Phase 8 work.  Guard here rather than falling through to
    # the technique_id comparison, which would silently misfire when technique_id is None
    # (all clash-contribution refs omit technique_id).
    if ref.clash_id is not None:
        # Clash contribution dispatch is intentionally unimplemented — see comment above.
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    # Calls get_player_actions (which also computes challenge actions via _challenge_actions).
    # The redundant challenge computation on this dispatch path is acceptable; flag if it
    # becomes a measurable bottleneck.
    all_actions = get_player_actions(character)
    for action in all_actions:
        if action.backend == ActionBackend.COMBAT and action.ref.technique_id == ref.technique_id:
            return action
    raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)


def _get_character_sheet(character: ObjectDB) -> CharacterSheet | None:
    """Return the ``CharacterSheet`` for *character*, or ``None`` if unavailable.

    Uses the reverse OneToOne relation ``sheet_data`` that ``CharacterSheet``
    attaches to ``ObjectDB`` via ``CharacterSheet.character`` (related_name="sheet_data").
    """
    try:
        return character.sheet_data  # type: ignore[attr-defined]
    except AttributeError:
        # RelatedObjectDoesNotExist (raised when CharacterSheet doesn't exist) is a
        # subclass of AttributeError, so this catches both "no sheet" and "no relation".
        # Bare `except Exception` was wrong: it masked DB errors (OperationalError etc.)
        # as "no sheet → empty list".
        return None
