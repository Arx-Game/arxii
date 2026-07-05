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

import dataclasses
from typing import TYPE_CHECKING, Any, NamedTuple

from actions.constants import ActionBackend, ActionCategory, TargetKind
from actions.errors import ActionDispatchError
from actions.registry import get_action
from actions.round_context import RoundContext, get_active_round_context
from actions.types import (
    ActionRef,
    ActionResult,
    AnchorOption,
    DispatchResult,
    FuryTierOption,
    PlayerAction,
    StrainAvailability,
    TargetFilters,
    TargetSpec,
    TargetType,
)
from world.magic.models import CharacterTechnique
from world.mechanics.services import get_available_actions

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.base import Action
    from actions.models import ActionTemplate
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterAnima
    from world.mechanics.types import AvailableAction
    from world.scenes.action_availability import AvailableEnhancement


# Sentinel for "caller did not supply a round context" — distinguishes from None (no active round).
# Used as the default value for the optional ``ctx`` parameter on _combat_actions and
# _clash_contribution_actions so that passing ``ctx=None`` (no active round, already resolved)
# and passing nothing (not yet resolved) are distinguishable.
_UNSET = object()


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
        return _dispatch_registry(character, ref, kwargs, ctx)

    # SCENE_ADAPTIVE: anti-spam gated, then immediate or declaration-deferred.
    if ref.backend == ActionBackend.SCENE_ADAPTIVE:
        return _dispatch_scene_adaptive(character, ref, kwargs, ctx)

    # Step 2: recover authoritative resolution inputs (validates ref against current availability).
    if ref.backend == ActionBackend.CHALLENGE:
        avail = _find_available_action_for_ref(character, ref)
        player_action = _avail_to_player_action(avail)

    else:
        # COMBAT: only surfaced during a DECLARING round; no round = invalid ref.
        if ctx is None or not ctx.is_declaration_open:
            raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

        player_action = _recover_combat_player_action(character, ref)
        avail = None  # COMBAT doesn't use AvailableAction

        # Clash-contribution path: bypass record_declaration and write directly.
        # ClashContributionDeclaration does not produce a CombatRoundAction row —
        # it is consumed by _resolve_clashes in the post-pass after all round actions
        # are resolved.  technique_id is required: ClashContributionDeclaration.technique
        # is non-nullable (world/combat/models.py, on_delete=PROTECT, no null=True).
        if ref.clash_id is not None:
            return _dispatch_clash_contribution(ctx, ref, kwargs)

    # Step 3: route — declaration-gated or immediate.
    declaration_open = ctx is not None and ctx.is_declaration_open
    if declaration_open:
        # Declaration window is open — defer to round resolution.
        ctx.record_declaration(sheet, player_action, kwargs)  # type: ignore[arg-type] — sheet is non-None: ctx only exists when a sheet resolved
        # Attempt presence-gated resolution: once every present ACTIVE participant has
        # declared, the social round resolves automatically.
        _maybe_resolve_scene_round(ctx)
        return DispatchResult(backend=ref.backend, deferred=True)

    return _dispatch_immediate_challenge(character, avail, ctx)


def _dispatch_registry(
    character: ObjectDB,
    ref: ActionRef,
    kwargs: dict[str, Any],
    ctx: RoundContext | None = None,
) -> DispatchResult:
    """Resolve and run a REGISTRY action immediately (no round gating).

    A turn-costing REGISTRY action (``costs_turn``) still drives an active scene round
    after it runs — a social round resolves if its present set is complete; a danger
    round ticks immediately.
    """
    action_obj = get_action(ref.registry_key or "")
    if action_obj is None:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
    # Merge non-ObjectDB target ids from the ref into kwargs so REGISTRY actions
    # that operate on non-ObjectDB models (e.g. move_to_position, set_the_stage) receive them.
    merged_kwargs = dict(kwargs)
    if ref.position_id is not None:
        merged_kwargs["position_id"] = ref.position_id
    if ref.blueprint_id is not None:
        merged_kwargs["blueprint_id"] = ref.blueprint_id
    result = action_obj.run(actor=character, **merged_kwargs)
    _drive_scene_round_for_turn_cost(action_obj, ctx)
    return DispatchResult(backend=ActionBackend.REGISTRY, deferred=False, detail=result)


def _scene_adaptive_target(kwargs: dict[str, Any]) -> Any:
    """Resolve ``target_persona_id`` from *kwargs* into a ``Persona`` instance, or ``None``."""
    target_persona_id = kwargs.get("target_persona_id")
    if target_persona_id is None:
        return None
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        return Persona.objects.get(pk=target_persona_id)
    except Persona.DoesNotExist:
        return None


def _dispatch_scene_adaptive(
    character: ObjectDB,
    ref: ActionRef,
    kwargs: dict[str, Any],
    ctx: RoundContext | None,
) -> DispatchResult:
    """Resolve and run a SCENE_ADAPTIVE action: anti-spam gated, then immediate or deferred.

    Flow:
    1. Anti-spam check — reject if the sheet acted too recently.
    2. Look up the action in the registry.
    3. If a round context is active:
       a. Ask the action for a round declaration; if one is returned and the window is open,
          record it and return deferred=True.
       b. Otherwise check is_repeat_blocked; raise ROUND_REPEAT_BLOCKED if blocked.
    4. Run immediately, mark acted, feed the pose-order ledger.
    """
    from commands.pending_actions import check_anti_spam, mark_acted  # noqa: PLC0415
    from world.scenes.models import get_scene_round_defaults_config  # noqa: PLC0415

    sheet = _get_character_sheet(character)
    if sheet is not None:
        cooldown = check_anti_spam(sheet.pk, get_scene_round_defaults_config().anti_spam_seconds)
        if cooldown is not None:
            raise ActionDispatchError(ActionDispatchError.ANTI_SPAM_COOLDOWN)

    action_obj = get_action(ref.registry_key or "")
    if action_obj is None:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    target_persona = _scene_adaptive_target(kwargs)
    run_kwargs = dict(kwargs)
    if ref.technique_id is not None:
        run_kwargs.setdefault("technique_id", ref.technique_id)

    if ctx is not None:
        decl = action_obj.round_declaration(ctx, **run_kwargs)
        if isinstance(decl, ActionResult):
            # Soulfray gate (or similar short-circuit): the action registered a pending
            # cast and returned a prompt message.  Do NOT record a declaration or run
            # execute() — return the message as a non-deferred result.
            return DispatchResult(backend=ActionBackend.SCENE_ADAPTIVE, deferred=False, detail=decl)
        if ctx.is_declaration_open and decl is not None:
            player_action, decl_kwargs = decl
            ctx.record_declaration(sheet, player_action, decl_kwargs)  # type: ignore[arg-type]
            return DispatchResult(backend=ActionBackend.SCENE_ADAPTIVE, deferred=True, detail=None)
        if ctx.is_repeat_blocked(sheet, ref, target_persona):
            raise ActionDispatchError(ActionDispatchError.ROUND_REPEAT_BLOCKED)

    result = action_obj.run(actor=character, **run_kwargs)
    if result.success:
        _record_scene_adaptive_acted(sheet, ctx, ref, target_persona, mark_acted)
    return DispatchResult(backend=ActionBackend.SCENE_ADAPTIVE, deferred=False, detail=result)


def _record_scene_adaptive_acted(
    sheet: Any,
    ctx: RoundContext | None,
    ref: ActionRef,
    target_persona: Any,
    mark_acted: Any,
) -> None:
    """Record anti-spam and pose-order side-effects after a successful SCENE_ADAPTIVE action."""
    if sheet is not None:
        mark_acted(sheet.pk)
    if ctx is not None and sheet is not None:
        ctx.record_immediate_action(sheet, ref, target_persona)


def _recover_combat_player_action(character: ObjectDB, ref: ActionRef) -> PlayerAction:
    """Recover the COMBAT ``PlayerAction`` for *ref*, carrying any client slot intent.

    The availability layer rebuilds the ref with technique_id only; carry the
    client's slot intent (focused vs passive-<category>) onto it so the
    declaration routes to the correct CombatRoundAction slot (#874).
    """
    player_action = _find_combat_player_action_for_ref(character, ref)
    if ref.action_slot is not None:
        player_action = dataclasses.replace(
            player_action,
            ref=dataclasses.replace(player_action.ref, action_slot=ref.action_slot),
        )
    return player_action


def _dispatch_immediate_challenge(
    character: ObjectDB,
    avail: AvailableAction | None,
    ctx: RoundContext | None,
) -> DispatchResult:
    """Resolve a CHALLENGE action immediately and tick the scene round if active.

    ``avail`` is guaranteed non-None on the live path: COMBAT without a round
    context raised earlier; CHALLENGE always sets ``avail``; REGISTRY returned early.
    """
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

    # Post-dispatch tick: a CHALLENGE action costs a turn; advance the scene round if active.
    _tick_scene_round_if_active(ctx)

    return DispatchResult(backend=ActionBackend.CHALLENGE, deferred=False, detail=resolution)


def _tick_scene_round_if_active(ctx: RoundContext | None) -> None:
    """Advance the scene round (tick DoTs) if *ctx* is a ``SceneRoundContext``.

    Called after an immediate CHALLENGE resolution. COMBAT cannot occur inside a scene round
    (``get_active_round_context`` returns combat context first), so only CHALLENGE reaches the
    immediate-resolution path while a scene round is active.
    """
    from world.scenes.round_context import SceneRoundContext  # noqa: PLC0415

    if isinstance(ctx, SceneRoundContext):
        from world.scenes.round_services import advance_scene_round_for_action  # noqa: PLC0415

        advance_scene_round_for_action(ctx.scene_round)


def _drive_scene_round_for_turn_cost(action_obj: Action, ctx: RoundContext | None) -> None:
    """Drive an active scene round after a turn-costing REGISTRY action.

    No-op unless *action_obj* is turn-costing and a scene round is active. STRICT
    (declaration-open) rounds — including danger rounds, which are STRICT —
    gather-and-resolve via presence-gated resolution; OPEN/POSE_ORDER rounds tick
    immediately."""
    if not action_obj.costs_turn or ctx is None:
        return
    if ctx.is_declaration_open:
        _maybe_resolve_scene_round(ctx)
    else:
        _tick_scene_round_if_active(ctx)


def _maybe_resolve_scene_round(ctx: RoundContext | None) -> None:
    """Resolve an active scene round if the presence-gated completion rule is met.

    Called after a turn-costing declaration/action. No-op for combat contexts and for
    OPEN/POSE_ORDER rounds (which tick immediately via ``_tick_scene_round_if_active``).
    A danger round is STRICT, so it resolves here — and ``resolve_scene_round`` owns the
    danger auto-end once the peril clears."""
    from world.scenes.round_context import SceneRoundContext  # noqa: PLC0415

    if isinstance(ctx, SceneRoundContext):
        from world.scenes.round_services import maybe_resolve_scene_round  # noqa: PLC0415

        maybe_resolve_scene_round(ctx.scene_round)


def get_player_actions(character: ObjectDB) -> list[PlayerAction]:
    """Return all available ``PlayerAction`` descriptors for *character*.

    Merges the challenge, combat, and registry backends into a single homogeneous
    list.  Recomputed on every call — no caching.

    Each ``PlayerAction`` is enriched with:
    - ``enhancements``: tuple of ``AvailableEnhancement`` (techniques the
      character knows whose ``ActionEnhancement`` rows reference the action's
      key/template).
    - ``target_spec``: ``TargetSpec`` for hand-coded actions that set
      ``target_kind`` / ``target_filters`` on the class; synthesized for
      data-driven social ``ActionTemplate``-backed actions; ``None`` for
      self-actions or unknown shapes.
    - ``strain``: ``StrainAvailability`` carrying the character's anima cap
      when at least one enhancement is reachable AND the character has a
      ``CharacterAnima`` row.

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

    # Resolve the round context once and share it across helpers that need it.
    # _combat_actions and _clash_contribution_actions both require the same lookup;
    # resolving once here halves the SceneRoundParticipant query cost.
    sheet = _get_character_sheet(character)
    ctx = get_active_round_context(sheet) if sheet is not None else None

    actions.extend(_challenge_actions(character))
    actions.extend(_combat_actions(character, ctx=ctx))
    actions.extend(_clash_contribution_actions(character, ctx=ctx))
    actions.extend(_scene_actions(character))
    actions.extend(_positioning_actions(character))
    actions.extend(_set_the_stage_actions(character))
    # Registry backend: all current actions excluded (no ActionTemplate / check_type)
    # — see module docstring.  When registry actions gain ActionTemplate backing,
    # uncomment and implement _registry_actions(character).

    # Single batched pass: attach enhancements/target_spec/strain to each
    # PlayerAction. All queries happen once for the whole character.
    _enrich_player_actions(character, actions)

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


def _combat_actions(
    character: ObjectDB,
    ctx: RoundContext | None = _UNSET,  # type: ignore[assignment]
) -> list[PlayerAction]:
    """Return COMBAT ``PlayerAction``s when the character is in an active declaring round.

    Only produces actions when:
    1. The character has a ``CharacterSheet`` (required to resolve combat participation).
    2. ``get_active_round_context`` returns a ``RoundContext`` with
       ``is_declaration_open == True`` (encounter in DECLARING phase).

    Candidate set: techniques the character knows that are combat-usable
    (``technique.action_template is not None``).  This is the SAME gate
    the dispatch path enforces — availability surfaces candidates only;
    authoritative per-target / passive-slot / status validation happens
    at dispatch time (``CombatRoundContext.record_declaration``).

    Args:
        character: The character's ``ObjectDB`` instance.
        ctx: Pre-resolved ``RoundContext`` (or ``None`` if no active round) from the caller.
            Pass ``_UNSET`` (the default) to let this function resolve it.
            Pass the caller's already-resolved context to avoid a redundant DB lookup.
    """
    # Resolve CharacterSheet from the character ObjectDB
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []

    if ctx is _UNSET:
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

    # Per-technique performability filter: skip techniques the character cannot
    # currently perform (dead, or any unmet capability requirement). Combat
    # techniques per character are bounded (a handful), so a clear per-technique
    # loop is acceptable for v1 — no batching needed.
    # Soulfray + fury declaration context (#1543). One soulfray lookup per
    # character; fury tiers are a small authored catalog; anchors are the
    # caster's consented relationships with a non-zero bond.
    from world.magic.models import FuryTier  # noqa: PLC0415
    from world.magic.services.capability_requirements import (  # noqa: PLC0415
        technique_performable,
    )
    from world.magic.services.fury import provocation_cap  # noqa: PLC0415
    from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415
    from world.relationships.models import CharacterRelationship  # noqa: PLC0415

    grants = list(grants)
    if not grants:
        return []

    fury_tiers = tuple(
        FuryTierOption(
            id=t.pk,
            name=t.name,
            depth=t.depth,
            control_penalty=t.control_penalty,
            intensity_bonus=t.intensity_bonus,
            berserk_severity=t.berserk_severity,
        )
        for t in FuryTier.objects.order_by("depth")
    )
    soulfray_warning = get_soulfray_warning(character)
    anchors: list[AnchorOption] = []
    for rel in CharacterRelationship.objects.filter(
        source=sheet, is_active=True, is_pending=False
    ).select_related("target", "target__character"):
        anchor_sheet = rel.target
        cap = provocation_cap(character, anchor_sheet)
        if cap < 1:
            continue
        anchor_char = anchor_sheet.character
        name = anchor_char.key if anchor_char is not None else str(anchor_sheet)
        anchors.append(AnchorOption(id=anchor_sheet.pk, name=name, provocation_cap=cap))
    eligible_fury_anchors = tuple(anchors)

    result: list[PlayerAction] = []
    for grant in grants:
        technique = grant.technique
        if not technique_performable(character, technique):
            continue
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
                action_category=technique.action_category,
                reach=technique.reach,
                soulfray_warning=soulfray_warning,
                available_fury_tiers=fury_tiers,
                eligible_fury_anchors=eligible_fury_anchors,
            )
        )

    return result


def _clash_contribution_actions(
    character: ObjectDB,
    ctx: RoundContext | None = _UNSET,  # type: ignore[assignment]
) -> list[PlayerAction]:
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

    Args:
        character: The character's ``ObjectDB`` instance.
        ctx: Pre-resolved ``RoundContext`` (or ``None`` if no active round) from the caller.
            Pass ``_UNSET`` (the default) to let this function resolve it.
            Pass the caller's already-resolved context to avoid a redundant DB lookup.
    """
    sheet = _get_character_sheet(character)
    if sheet is None:
        return []

    # Clash contribution declarations are only meaningful during DECLARING phase —
    # same gate as _combat_actions.  Return early if the window is closed.
    if ctx is _UNSET:
        ctx = get_active_round_context(sheet)
    if ctx is None or not ctx.is_declaration_open:
        return []

    # Deferred imports: keep the actions package free of combat models at the top level.
    from world.combat.constants import (  # noqa: PLC0415
        ClashActionSlot,
        ClashStatus,
        ParticipantStatus,
    )
    from world.combat.models import Clash, CombatParticipant  # noqa: PLC0415
    from world.scenes.constants import RoundStatus  # noqa: PLC0415

    # Find an active participant in a non-completed encounter.
    participant = (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
            encounter__status__in={
                RoundStatus.DECLARING,
                RoundStatus.RESOLVING,
                RoundStatus.BETWEEN_ROUNDS,
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

    # FOCUSED-only emission. Per the combat-resolution-loop design spec, a
    # clash is something a PC is bound to by their focused action — there is
    # no separate "passive contribution" concept. The PASSIVE descriptor was
    # emitted in earlier code (and surfaced "Commit / Lend" as a player
    # choice) but the dichotomy is wrong by design. The `ClashActionSlot.PASSIVE`
    # enum value stays in the data model for v1 (no schema churn) but is
    # unreachable from the public surface.
    result: list[PlayerAction] = []
    for clash in active_clashes:
        opponent_name = clash.npc_opponent.name
        flavor_label = clash.get_flavor_display()
        progress_summary = f"Progress: {clash.progress} / {clash.pc_win_threshold} (PC target)"

        display_name = f"Commit to {flavor_label}: {opponent_name}"
        description = (
            f"Use your focused action slot to contribute to this clash. {progress_summary}."
        )

        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=clash.pk,
            clash_action_slot=ClashActionSlot.FOCUSED.value,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.COMBAT,
                display_name=display_name,
                description=description,
                ref=ref,
                # check_type is None: technique chosen at declaration time determines the check.
                check_type=None,
                # v1: every PC in the encounter sees every active clash. The
                # principal-vs-helper-vs-ineligible role distinction is deferred
                # to a follow-up PR; for now every active clash surfaces a
                # commit option to every encounter participant.
                prerequisite_met=True,
                prerequisite_reasons=[],
            )
        )

    return result


def _dispatch_clash_contribution(
    ctx: Any,
    ref: ActionRef,
    kwargs: dict[str, Any],
) -> DispatchResult:
    """Write a ``ClashContributionDeclaration`` for the given clash ref.

    Extracted from ``dispatch_player_action`` to keep its cyclomatic complexity
    within ruff's C901 limit.  Called only when ``ref.clash_id is not None`` and
    ``ctx.is_declaration_open`` is ``True`` (both guaranteed by the caller).

    When ``cast_pull`` is present in *kwargs*, commits the pull immediately via
    ``world.combat.pull_helpers.commit_combat_pull`` so the clash read-path
    (``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``) reflects the
    pull during round resolution.  The one-pull-per-round unique constraint on
    ``CombatPull`` enforces the cap; a duplicate attempt raises
    ``ActionDispatchError(PULL_ALREADY_COMMITTED)``.

    ``cast_pull`` is intentionally NOT forwarded into ``declare_clash_contribution``
    — the bonus comes from the ``CombatPull`` read-path, not from the declaration
    kwargs, to avoid double-charging.

    Raises:
        ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if ``technique_id`` is
            missing from ``kwargs``, ``ctx`` is not a ``CombatRoundContext``, or
            either the ``Clash`` or ``Technique`` pk does not exist.
        ActionDispatchError: With ``PULL_ALREADY_COMMITTED`` when the player has
            already committed a pull this round.
        ActionDispatchError: With ``PULL_INVALID`` when the pull declaration is
            invalid (e.g. thread not anchored to the technique, insufficient balance).
    """
    from world.combat.models import Clash  # noqa: PLC0415
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.combat.services import declare_clash_contribution  # noqa: PLC0415
    from world.magic.models.techniques import Technique  # noqa: PLC0415

    technique_id = kwargs.get("technique_id")
    if technique_id is None:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    # isinstance guard narrows the type for ty so ctx.participant is accessible.
    # ctx is non-None with is_declaration_open=True — guaranteed by the caller.
    if not isinstance(ctx, CombatRoundContext):
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)

    try:
        clash = Clash.objects.get(pk=ref.clash_id)
    except Clash.DoesNotExist as exc:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

    try:
        technique = Technique.objects.get(pk=technique_id)
    except Technique.DoesNotExist as exc:
        raise ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF) from exc

    # Commit an optional thread pull at declaration time.  The pull bonus is
    # sourced from the CombatPull read-path during resolution; do not forward
    # cast_pull into declare_clash_contribution (avoids double-charge).
    # resolve_pull_from_kwargs normalises both the telnet path (pre-built
    # CastPullDeclaration in kwargs["cast_pull"]) and the web path (raw IDs:
    # pull_resonance_id / pull_tier / pull_thread_ids) into one optional declaration.
    from world.combat.pull_helpers import (  # noqa: PLC0415
        commit_combat_pull,
        resolve_pull_from_kwargs,
    )

    sheet = ctx.participant.character_sheet
    cast_pull = resolve_pull_from_kwargs(sheet, kwargs)
    if cast_pull is not None:
        # The clash's target is always its NPC opponent (#1831) — Clash is a
        # PC(s)-vs-one-NPC primitive; there is no ally leg to consider here.
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=ctx.participant,
            encounter=ctx.participant.encounter,
            technique_id=technique_id,
            target=clash.npc_opponent.objectdb,
        )

    declare_clash_contribution(
        participant=ctx.participant,
        clash=clash,
        action_slot=ref.clash_action_slot,
        technique=technique,
        strain_commitment=kwargs.get("strain_commitment", 0),
    )
    return DispatchResult(backend=ActionBackend.COMBAT, deferred=True)


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
    if ref.clash_id is not None:
        # Clash-contribution dispatch: match against the read-path emitter so that
        # only surfaced clashes are dispatchable (same security gate as technique dispatch).
        clash_actions = _clash_contribution_actions(character)
        for action in clash_actions:
            if (
                action.ref.clash_id == ref.clash_id
                and action.ref.clash_action_slot == ref.clash_action_slot
            ):
                return action
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


# ---------------------------------------------------------------------------
# Positioning-action adapter (move_to_position for directly adjacent positions)
# ---------------------------------------------------------------------------


def _positioning_actions(character: ObjectDB) -> list[PlayerAction]:
    """Surface a move_to_position ``PlayerAction`` for each directly adjacent passable position.

    "Directly adjacent" means a single-hop open edge (passable + no active gating
    challenge) from the character's current position.  Multi-hop reachability is
    handled by the service's ``reachable_positions`` function (BFS), but this
    action picker only offers single-hop moves so the player makes one step at a time.

    If the character is not placed in any position (unplaced or no positioning graph
    in the room), returns an empty list — no error is raised.
    """
    from django.db.models import Q  # noqa: PLC0415

    from world.areas.positioning.models import PositionEdge  # noqa: PLC0415
    from world.areas.positioning.services import (  # noqa: PLC0415
        adjacent_open_positions,
        position_of,
    )

    current = position_of(character)
    if current is None:
        return []

    result: list[PlayerAction] = []
    for edge in adjacent_open_positions(current):
        # Determine which side of the edge is the destination (not current).
        neighbor = edge.position_b if edge.position_a_id == current.pk else edge.position_a
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="move_to_position",
            position_id=neighbor.pk,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.REGISTRY,
                display_name=f"Move to {neighbor.name}",
                ref=ref,
                description=neighbor.description,
                action_category=ActionCategory.PHYSICAL,
            )
        )

    # Surface gated (locked) edges as non-actionable entries so the player
    # can see that a path exists but is currently blocked by a challenge.
    gated_edges = PositionEdge.objects.filter(
        Q(position_a=current) | Q(position_b=current),
        is_passable=True,
        gating_challenge__isnull=False,
        gating_challenge__is_active=True,
    ).select_related("position_a", "position_b", "gating_challenge__template")
    for edge in gated_edges:
        neighbor = edge.position_b if edge.position_a_id == current.pk else edge.position_a
        challenge_name = edge.gating_challenge.template.name
        # Point the ref at the gating challenge so the UI can offer the approach.
        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=edge.gating_challenge_id,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.CHALLENGE,
                display_name=f"Move to {neighbor.name} (blocked: {challenge_name})",
                ref=ref,
                description=neighbor.description,
                action_category=ActionCategory.PHYSICAL,
                prerequisite_met=False,
                prerequisite_reasons=[f"Gated by challenge: {challenge_name}"],
            )
        )

    return result


# ---------------------------------------------------------------------------
# Staff-only terrain adapter (set_the_stage quick action)
# ---------------------------------------------------------------------------


def _set_the_stage_actions(character: ObjectDB) -> list[PlayerAction]:
    """Surface a ``set_the_stage`` ``PlayerAction`` for staff when the room has a default blueprint.

    Only emits an action when ALL of the following are true:
    - The actor passes ``is_staff_observer`` (avoids the model query for non-staff).
    - The actor has a current location.
    - The location has a ``RoomProfile`` with ``default_blueprint`` set.

    A single ``PlayerAction`` is offered using the room's ``default_blueprint``.
    Staff who want to apply a different blueprint can pass an arbitrary
    ``blueprint_id`` in the kwargs via the API; this surface only provides the
    one-click default-blueprint quick action.
    """
    from core_management.permissions import is_staff_observer  # noqa: PLC0415

    if not is_staff_observer(character):
        return []

    location = character.location
    if location is None:
        return []

    profile = getattr(location, "room_profile", None)  # noqa: GETATTR_LITERAL
    if profile is None:
        return []

    blueprint = profile.default_blueprint
    if blueprint is None:
        return []

    ref = ActionRef(
        backend=ActionBackend.REGISTRY,
        registry_key="set_the_stage",
        blueprint_id=blueprint.pk,
    )
    return [
        PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name=f"Set the stage: {blueprint.name}",
            ref=ref,
            description=blueprint.description if blueprint.description else "",
            action_category=ActionCategory.PHYSICAL,
        )
    ]


# ---------------------------------------------------------------------------
# Scene-action adapter (social ActionTemplates with technique enhancements)
# ---------------------------------------------------------------------------


_SOCIAL_CATEGORY = "social"  # noqa: STRING_LITERAL


def _scene_actions(character: ObjectDB) -> list[PlayerAction]:
    """Surface social ``ActionTemplate`` rows as ``PlayerAction``s.

    These are the data-driven social actions (Intimidate, Persuade, Flirt, …).
    For v1 they emit as REGISTRY-backend descriptors keyed by the lowercased
    template name. A follow-up PR may introduce a dedicated backend value.

    Enhancements / target_spec / strain are NOT populated here — they are
    attached uniformly by ``_enrich_player_actions`` so every backend's actions
    pass through one batched pass of the same queries.

    Currently ignores *character*; in a follow-up this becomes the place where
    per-character availability filters (e.g. residence-only social actions)
    apply.
    """
    del character  # placeholder for per-character filtering in a follow-up PR
    from actions.models import ActionTemplate  # noqa: PLC0415
    from actions.registry import SOCIAL_ACTIONS_BY_TEMPLATE_NAME  # noqa: PLC0415

    templates = list(ActionTemplate.objects.filter(category=_SOCIAL_CATEGORY))
    result: list[PlayerAction] = []
    for template in templates:
        # Derive the dispatch key from the registry singleton, not name.lower():
        # multi-word templates ("Restore to Sense") have a distinct registry key
        # ("restore_sense") that a slug transform cannot reproduce (#1172).
        social_action = SOCIAL_ACTIONS_BY_TEMPLATE_NAME.get(template.name)
        action_key = social_action.key if social_action is not None else template.name.lower()
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key=action_key,
        )
        result.append(
            PlayerAction(
                backend=ActionBackend.REGISTRY,
                display_name=template.name,
                ref=ref,
                check_type=template.check_type,
                action_template=template,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Enrichment: enhancements + target_spec + strain
# ---------------------------------------------------------------------------


def _enrich_player_actions(
    character: ObjectDB,
    actions: list[PlayerAction],
) -> None:
    """Mutate *actions* in place, attaching enhancements / target_spec / strain.

    Single batched pass:
    - Query the character's known techniques once.
    - Query ActionEnhancement rows joining those techniques once.
    - Bucket enhancements by ``action_template_id`` and ``base_action_key`` so a
      PlayerAction can find its enhancements via either path.
    - Fetch CharacterAnima once for the strain cap snapshot.

    Self-actions / unknown target shapes leave ``target_spec=None``.
    """
    sheet = _get_character_sheet(character)
    if sheet is None:
        return

    known_technique_ids = set(
        CharacterTechnique.objects.filter(character=sheet).values_list("technique_id", flat=True)
    )

    anima = _get_character_anima(character)

    enhancements_by_action_key = _build_enhancement_index(
        character=character,
        known_technique_ids=known_technique_ids,
        anima=anima,
    )

    strain_cap = anima.current if anima is not None else None

    for action in actions:
        enhancements = _enhancements_for_action(
            action=action,
            enhancements_by_action_key=enhancements_by_action_key,
        )
        action.enhancements = enhancements
        action.target_spec = _target_spec_for_action(action, character=character)
        action.action_category = _action_category_for_action(action)
        if enhancements and strain_cap is not None:
            action.strain = StrainAvailability(cap=strain_cap)


def _build_enhancement_index(
    *,
    character: ObjectDB,
    known_technique_ids: set[int],
    anima: CharacterAnima | None,
) -> dict[str, list[AvailableEnhancement]]:
    """Return an index of available enhancements keyed by ``base_action_key``.

    Pure: one query for ActionEnhancement rows, plus a per-technique runtime
    stats lookup. Identity-map caching keeps the cost low across repeated calls
    in the same request.

    Receives ``anima`` from the caller so we don't issue a duplicate
    CharacterAnima lookup just to compute effective costs.
    """
    from actions.models import ActionEnhancement  # noqa: PLC0415
    from world.magic.services import (  # noqa: PLC0415
        calculate_effective_anima_cost,
        get_runtime_technique_stats,
        get_soulfray_warning,
    )
    from world.scenes.action_availability import AvailableEnhancement  # noqa: PLC0415

    by_action_key: dict[str, list[AvailableEnhancement]] = {}

    if not known_technique_ids:
        return by_action_key

    rows = list(
        ActionEnhancement.objects.filter(
            source_type="technique",
            technique_id__in=known_technique_ids,
        ).select_related("technique")
    )
    if not rows:
        return by_action_key

    soulfray_warning = get_soulfray_warning(character) if rows else None
    stats_cache: dict[int, tuple[int, int]] = {}

    for row in rows:
        technique = row.technique
        if technique is None:
            continue
        if technique.pk not in stats_cache:
            stats = get_runtime_technique_stats(technique, character)
            stats_cache[technique.pk] = (stats.intensity, stats.control)
        intensity, control = stats_cache[technique.pk]

        if anima is not None:
            cost = calculate_effective_anima_cost(
                base_cost=technique.anima_cost,
                runtime_intensity=intensity,
                runtime_control=control,
                current_anima=anima.current,
            )
            effective_cost = cost.effective_cost
        else:
            effective_cost = 0

        warning = soulfray_warning if effective_cost > 0 else None
        available = AvailableEnhancement(
            enhancement=row,
            technique=technique,
            effective_cost=effective_cost,
            soulfray_warning=warning,
        )

        if row.base_action_key:
            by_action_key.setdefault(row.base_action_key, []).append(available)

    return by_action_key


def _enhancements_for_action(
    *,
    action: PlayerAction,
    enhancements_by_action_key: dict[str, list[AvailableEnhancement]],
) -> tuple[AvailableEnhancement, ...]:
    """Return enhancements for *action* via ``base_action_key`` indexing."""
    action_key = _resolve_action_key(action)
    if action_key and action_key in enhancements_by_action_key:
        return tuple(enhancements_by_action_key[action_key])

    return ()


def _resolve_action_key(action: PlayerAction) -> str:
    """Return the action key for *action* used to find ActionEnhancement rows.

    Prefer the dispatch ref's ``registry_key``: for social actions it is the
    canonical registry key (e.g. ``restore_sense``), whereas ``template.name.lower()``
    would yield ``restore to sense`` and miss the ``base_action_key`` index (#1172).
    """
    if action.ref.registry_key:
        return action.ref.registry_key
    template = action.action_template
    if template is not None:
        return template.name.lower()
    return ""


def _tenure_persona_ids(tenure: object) -> set[int]:
    """Return persona PKs attached to *tenure*'s roster entry's character sheet.

    Returns an empty set if the relationship chain is broken.
    """
    try:
        sheet = tenure.roster_entry.character_sheet  # type: ignore[union-attr]
        return set(sheet.personas.values_list("pk", flat=True))
    except Exception:  # noqa: BLE001
        return set()


def _tenure_blocks_actor(
    tenure: object, actor_tenure: object | None, category: object | None
) -> bool:
    """True if *tenure*'s consent excludes *actor_tenure* for *category*.

    Thin wrapper over :func:`world.consent.services.consent_blocks_targeting` — the
    single-tenure gate decision now lives there (#1909) so later gates (e.g. the steal
    gate) can call it directly without reaching into the dispatch layer. This name
    stays so existing callers (duels, tests) are untouched. The scene-wide picker
    sweep batches the same decision in :func:`_consent_excluded_persona_ids`.
    """
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415

    return consent_blocks_targeting(
        owner_tenure=tenure, category=category, actor_tenure=actor_tenure
    )


class _CategoryConsentData(NamedTuple):
    """Batched per-category consent lookups for a participant sweep (owner-tenure id sets)."""

    rule_modes: dict[int, str]
    whitelisted_owner_ids: set[int]
    blacklisted_owner_ids: set[int]
    friend_owner_ids: set[int]


def _load_category_consent_data(
    prefs_by_tenure: dict[int, object],
    tenure_ids: list[int],
    category: object | None,
    actor_tenure: object | None,
) -> _CategoryConsentData:
    """Batch-load the per-category consent data for a participant sweep.

    Returns a :class:`_CategoryConsentData` whose ``rule_modes`` maps a preference id to
    its category rule mode, and whose three owner-id sets record which owner tenures have
    (respectively) whitelisted, blacklisted, or friended *actor_tenure*. Everything is
    empty when *category* is ``None`` (uncategorized → master switch only). At most four
    queries (rules, whitelist, blacklist, friendships), each independent of participant
    count. Friendship is not category-scoped — an OOC friend passes every category.
    """
    from world.consent.models import (  # noqa: PLC0415
        SocialConsentBlacklist,
        SocialConsentCategoryRule,
        SocialConsentWhitelist,
    )
    from world.scenes.models import Friendship  # noqa: PLC0415

    rule_modes: dict[int, str] = {}
    whitelisted_owner_ids: set[int] = set()
    blacklisted_owner_ids: set[int] = set()
    friend_owner_ids: set[int] = set()
    if category is None:
        return _CategoryConsentData(
            rule_modes, whitelisted_owner_ids, blacklisted_owner_ids, friend_owner_ids
        )

    pref_ids = [pref.pk for pref in prefs_by_tenure.values()]
    if pref_ids:
        # One query: this category's rules across all of those preferences.
        rule_modes = {
            rule.preference_id: rule.mode
            for rule in SocialConsentCategoryRule.objects.filter(
                preference_id__in=pref_ids, category=category
            )
        }
    if actor_tenure is not None:
        # One query each: whitelist / blacklist entries naming the actor for this category,
        # plus friendships the owner tenures extended to the actor (category-independent).
        whitelisted_owner_ids = set(
            SocialConsentWhitelist.objects.filter(
                owner_tenure_id__in=tenure_ids,
                allowed_tenure=actor_tenure,
                category=category,
            ).values_list("owner_tenure_id", flat=True)
        )
        blacklisted_owner_ids = set(
            SocialConsentBlacklist.objects.filter(
                owner_tenure_id__in=tenure_ids,
                blocked_tenure=actor_tenure,
                category=category,
            ).values_list("owner_tenure_id", flat=True)
        )
        friend_owner_ids = set(
            Friendship.objects.filter(
                friender_tenure_id__in=tenure_ids,
                friend_tenure=actor_tenure,
            ).values_list("friender_tenure_id", flat=True)
        )
    return _CategoryConsentData(
        rule_modes, whitelisted_owner_ids, blacklisted_owner_ids, friend_owner_ids
    )


def _consent_excluded_persona_ids(
    tenures: list,
    tenure_ids: list[int],
    category: object | None,
    actor_tenure: object | None,
) -> set[int]:
    """Persona ids of *tenures* whose consent blocks the actor, decided from batched data.

    Mirrors the per-tenure decision in :func:`_tenure_blocks_actor` but loads the
    preference / category-rule / whitelist / blacklist / friendship data once for the
    whole set (one preference query plus the loads in :func:`_load_category_consent_data`).
    """
    from world.consent.models import SocialConsentPreference  # noqa: PLC0415
    from world.consent.services import _decide_consent_block  # noqa: PLC0415

    # One query: preferences for those tenures, keyed by tenure id (missing → default allow).
    prefs_by_tenure: dict[int, object] = {
        pref.tenure_id: pref
        for pref in SocialConsentPreference.objects.filter(tenure_id__in=tenure_ids)
    }
    data = _load_category_consent_data(prefs_by_tenure, tenure_ids, category, actor_tenure)

    actor_present = actor_tenure is not None
    excluded: set[int] = set()
    for tenure in tenures:
        pref = prefs_by_tenure.get(tenure.pk)
        if pref is None:
            continue  # no preference row → default allow
        if not pref.allow_social_actions:
            excluded.update(_tenure_persona_ids(tenure))
            continue
        if category is None:
            continue  # uncategorized → master switch only
        if _decide_consent_block(
            data.rule_modes.get(pref.pk),
            actor_present=actor_present,
            whitelisted=tenure.pk in data.whitelisted_owner_ids,
            blacklisted=tenure.pk in data.blacklisted_owner_ids,
            is_friend=tenure.pk in data.friend_owner_ids,
        ):
            excluded.update(_tenure_persona_ids(tenure))
    return excluded


def _block_excludes(
    block: object,
    actor_player_id: int,
    actor_persona_id: int | None,
    persona_ids: set[int],
) -> set[int]:
    """Persona ids a single block removes from the actor's target picker (#1278).

    Either direction. A persona-scoped block applies only while the actor presents the relevant
    face; ``account_level`` covers all of the blocker's faces. Only the exact blocked/blocker
    faces are excluded — never the rest of the player's roster (anti-derivation).
    """
    if block.owner_id == actor_player_id:  # actor is the blocker
        if not block.account_level and block.blocker_persona_id not in (None, actor_persona_id):
            return set()
        if block.blocked_persona_id is None:
            return set(persona_ids)
        return {block.blocked_persona_id} if block.blocked_persona_id in persona_ids else set()
    # actor is the blocked
    if block.account_level:
        return set(persona_ids)
    if block.blocker_persona_id in persona_ids and block.blocked_persona_id in (
        None,
        actor_persona_id,
    ):
        return {block.blocker_persona_id}
    return set()


def _block_excluded_persona_ids(
    actor_tenure: object | None,
    actor_persona_id: int | None,
    tenures: list,
) -> set[int]:
    """Persona ids in the scene the actor cannot target due to an active block (#1278).

    Loads the actor's active blocks once, then matches each participant tenure's personas in
    Python — no per-candidate query. Mutual; the per-block decision is ``_block_excludes``.
    """
    if actor_tenure is None:
        return set()
    from django.db.models import Q  # noqa: PLC0415
    from django.utils import timezone  # noqa: PLC0415

    from world.scenes.models import Block  # noqa: PLC0415

    actor_player_id = actor_tenure.player_data_id
    blocks = list(
        Block.objects.filter(
            Q(pending_removal_at__isnull=True) | Q(pending_removal_at__gt=timezone.now())
        ).filter(Q(owner_id=actor_player_id) | Q(blocked_player_id=actor_player_id))
    )
    if not blocks:
        return set()

    excluded: set[int] = set()
    for tenure in tenures:
        other_player_id = tenure.player_data_id
        if other_player_id == actor_player_id:
            continue
        persona_ids = _tenure_persona_ids(tenure)
        for block in blocks:
            if {block.owner_id, block.blocked_player_id} == {actor_player_id, other_player_id}:
                excluded |= _block_excludes(block, actor_player_id, actor_persona_id, persona_ids)
    return excluded


def _social_consent_exclusions(character: ObjectDB, category: object | None) -> frozenset[int]:
    """Return persona IDs of characters that don't consent to social actions from *character*.

    Checks SocialConsentPreference for all tenures participating in the character's
    current scene. Returns a frozenset of Persona PKs to exclude from the target picker.
    *category* gates per-category enforcement (mirrors :func:`_tenure_blocks_actor`).

    The preference / category-rule / whitelist lookups are **batched** across the whole
    participant set: a bounded number of queries per sweep (one tenure load, one
    preference load, and — when *category* is set — one category-rule load plus, when the
    actor has a tenure, one whitelist load), rather than the per-tenure fan-out that would
    scale with scene size (#1248).
    """
    from world.roster.models import RosterTenure  # noqa: PLC0415
    from world.scenes.models import Scene, SceneParticipation  # noqa: PLC0415

    location = character.db_location
    if location is None:
        return frozenset()

    scene = (
        Scene.objects.filter(location=location, is_active=True).order_by("-date_started").first()
    )
    if scene is None:
        return frozenset()

    actor_sheet = _get_character_sheet(character)
    actor_tenure: RosterTenure | None = None
    if actor_sheet is not None:
        actor_tenure = RosterTenure.objects.filter(
            roster_entry__character_sheet=actor_sheet,
            end_date__isnull=True,
        ).first()

    participations = list(SceneParticipation.objects.filter(scene=scene).select_related("account"))
    account_ids = {p.account_id for p in participations if p.account_id is not None}
    if not account_ids:
        return frozenset()

    # One query: every active tenure for the participating accounts.
    tenures = list(
        RosterTenure.objects.filter(
            player_data__account_id__in=account_ids,
            end_date__isnull=True,
        )
    )
    if not tenures:
        return frozenset()
    tenure_ids = [tenure.pk for tenure in tenures]

    consent_excluded = _consent_excluded_persona_ids(tenures, tenure_ids, category, actor_tenure)

    # #1278 — a coded block also removes the blocked persona from the actor's target picker.
    actor_persona_id: int | None = None
    if actor_sheet is not None:
        from world.scenes.constants import PersonaType  # noqa: PLC0415

        active_id = actor_sheet.active_persona_id
        if active_id is not None:
            actor_persona_id = active_id
        else:
            primary = actor_sheet.personas.filter(persona_type=PersonaType.PRIMARY).first()
            actor_persona_id = primary.pk if primary is not None else None
    block_excluded = _block_excluded_persona_ids(actor_tenure, actor_persona_id, tenures)

    return frozenset(consent_excluded | block_excluded)


def _target_spec_for_action(
    action: PlayerAction, character: ObjectDB | None = None
) -> TargetSpec | None:
    """Synthesize a ``TargetSpec`` for *action* by inspecting available metadata.

    Resolution order:
    1. Hand-coded ``Action`` subclass via the dispatch ref's ``registry_key``;
       read its ``target_kind`` and ``target_filters`` class fields.
    2. Data-driven social ``ActionTemplate`` (category=="social"): synthesize
       a PERSONA + SINGLE + in_same_scene/exclude_self + consent exclusions.
    3. COMBAT technique action (``ref.technique_id`` set): synthesize from
       the technique's ``target_type`` and derived relationship. Returns ``None``
       for SELF-targeting techniques (no frontend picker needed).
    4. Anything else: ``None`` (self-action or shape we don't know yet).
    """
    if action.ref.registry_key:
        registry_action = get_action(action.ref.registry_key)
        if registry_action is not None and registry_action.target_kind is not None:
            return TargetSpec(
                kind=registry_action.target_kind,
                cardinality=registry_action.target_type,
                filters=registry_action.target_filters or TargetFilters(),
            )

    template = action.action_template
    if template is not None and _template_is_social(template):
        excluded = (
            _social_consent_exclusions(character, template.consent_category)
            if character is not None
            else frozenset()
        )
        return TargetSpec(
            kind=TargetKind.PERSONA,
            cardinality=TargetType.SINGLE,
            filters=TargetFilters(
                in_same_scene=True,
                exclude_self=True,
                excluded_persona_ids=excluded,
            ),
        )

    if action.backend == ActionBackend.COMBAT and action.ref.technique_id is not None:
        return _target_spec_for_technique_action(action.ref.technique_id)

    return None


def _target_spec_for_technique_action(technique_id: int) -> TargetSpec | None:
    """Build a ``TargetSpec`` for a COMBAT technique action.

    Returns ``None`` for SELF-targeting techniques (no picker needed).
    For all other cardinalities, returns a PERSONA spec with ``in_same_scene=True``
    and ``exclude_self=True`` when the derived relationship is ENEMY or ALLY.
    """
    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.models.techniques import ConditionTargetKind, Technique  # noqa: PLC0415
    from world.magic.services.targeting import derive_target_relationship  # noqa: PLC0415

    try:
        technique = Technique.objects.get(pk=technique_id)
    except Technique.DoesNotExist:
        return None

    if technique.target_type == ActionTargetType.SELF:
        return None

    relationship = derive_target_relationship(technique)
    exclude_self = relationship in {ConditionTargetKind.ENEMY, ConditionTargetKind.ALLY}
    return TargetSpec(
        kind=TargetKind.PERSONA,
        cardinality=TargetType(technique.target_type),
        filters=TargetFilters(
            in_same_scene=True,
            exclude_self=exclude_self,
        ),
    )


def _action_category_for_action(action: PlayerAction) -> ActionCategory | None:
    """Return the ActionCategory for *action*, preferring the already-set value.

    For COMBAT actions the category is set from the technique at build time.
    For registry actions backed by a code Action singleton, propagate from
    that singleton's ``action_category`` field.
    """
    if action.action_category is not None:
        return action.action_category
    if action.ref.registry_key:
        registry_action = get_action(action.ref.registry_key)
        if registry_action is not None and registry_action.action_category is not None:
            return registry_action.action_category
    return None


def _template_is_social(template: ActionTemplate) -> bool:
    """Return True if *template* is a social-category data-driven action."""
    return template.category == _SOCIAL_CATEGORY


def _get_character_anima(character: ObjectDB) -> CharacterAnima | None:
    """Return the character's CharacterAnima row, or None when unset.

    Shared by ``_build_enhancement_index`` and the strain attachment so the
    identity map serves both reads from a single fetch.
    """
    from world.magic.models import CharacterAnima  # noqa: PLC0415

    try:
        return CharacterAnima.objects.get(character=character)
    except CharacterAnima.DoesNotExist:
        return None
