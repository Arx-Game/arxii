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

from actions.constants import ActionBackend, TargetKind
from actions.errors import ActionDispatchError
from actions.registry import get_action
from actions.round_context import get_active_round_context
from actions.types import (
    ActionRef,
    DispatchResult,
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

    from actions.models import ActionTemplate
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterAnima
    from world.mechanics.types import AvailableAction
    from world.scenes.action_availability import AvailableEnhancement


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

    actions.extend(_challenge_actions(character))
    actions.extend(_combat_actions(character))
    actions.extend(_clash_contribution_actions(character))
    actions.extend(_scene_actions(character))
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

    Raises:
        ActionDispatchError: With ``UNKNOWN_ACTION_REF`` if ``technique_id`` is
            missing from ``kwargs``, ``ctx`` is not a ``CombatRoundContext``, or
            either the ``Clash`` or ``Technique`` pk does not exist.
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
# Scene-action adapter (social ActionTemplates with technique enhancements)
# ---------------------------------------------------------------------------


_SOCIAL_CATEGORY = "social"  # noqa: STRING_LITERAL — mirrors ActionTemplate.category column, no TextChoices for it yet


def _scene_actions(character: ObjectDB) -> list[PlayerAction]:
    """Surface social ``ActionTemplate`` rows as ``PlayerAction``s.

    These are the data-driven social actions (Intimidate, Persuade, Flirt, …)
    that previously lived behind ``world.scenes.action_availability.
    get_available_scene_actions``. For v1 they emit as REGISTRY-backend
    descriptors keyed by the lowercased template name — the legacy scene-action
    endpoint still handles dispatch. A follow-up PR will introduce a dedicated
    backend value for these once the legacy endpoint is removed.

    Enhancements / target_spec / strain are NOT populated here — they are
    attached uniformly by ``_enrich_player_actions`` so every backend's actions
    pass through one batched pass of the same queries.

    Currently ignores *character*; in a follow-up this becomes the place where
    per-character availability filters (e.g. residence-only social actions)
    apply.
    """
    del character  # placeholder for per-character filtering in a follow-up PR
    from actions.models import ActionTemplate  # noqa: PLC0415

    templates = list(ActionTemplate.objects.filter(category=_SOCIAL_CATEGORY))
    result: list[PlayerAction] = []
    for template in templates:
        action_key = template.name.lower()
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
        action.target_spec = _target_spec_for_action(action)
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
    stats lookup that is identical to what ``get_available_scene_actions``
    performs. Identity-map caching keeps the cost low across repeated calls
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
    """Return the action key for *action* used to find ActionEnhancement rows."""
    template = action.action_template
    if template is not None:
        return template.name.lower()
    if action.ref.registry_key:
        return action.ref.registry_key
    return ""


def _target_spec_for_action(action: PlayerAction) -> TargetSpec | None:
    """Synthesize a ``TargetSpec`` for *action* by inspecting available metadata.

    Resolution order:
    1. Hand-coded ``Action`` subclass via the dispatch ref's ``registry_key``;
       read its ``target_kind`` and ``target_filters`` class fields.
    2. Data-driven social ``ActionTemplate`` (category=="social"): synthesize
       a PERSONA + SINGLE + in_same_scene/exclude_self default.
    3. Anything else: ``None`` (self-action or shape we don't know yet).
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
        return TargetSpec(
            kind=TargetKind.PERSONA,
            cardinality=TargetType.SINGLE,
            filters=TargetFilters(in_same_scene=True, exclude_self=True),
        )

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
