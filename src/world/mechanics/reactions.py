"""Shared capability-reaction dispatch helper (#1273).

A "capability reaction" is the pattern where a character responds to an event
(a falling ally, an incoming blow) by locating an active :class:`ChallengeInstance`
bound to a target object, selecting the right approach from their available
actions, resolving the challenge, and applying an outcome function.

This module extracts that pattern from ``plummet.dispatch_catch`` so both the
catch and interpose resolution paths share one spine.  Converging
``dispatch_catch`` itself onto this helper is deferred to a follow-up task (Task
9) to avoid destabilising the already-merged plummet work.

Public surface:

- :func:`dispatch_capability_reaction` — the shared spine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.types import AvailableAction, ChallengeResolutionResult


def _select_reaction_action(
    actor: ObjectDB,
    actions: list[AvailableAction],
    approach: str | None,
    *,
    select_best_check_rating: bool = False,
) -> AvailableAction:
    """Pick the :class:`~world.mechanics.types.AvailableAction` matching *approach*.

    Iterates *actions* looking for one whose ``capability_source.capability_name``
    equals *approach*.  Falls back to ``actions[0]`` when:

    - *approach* is ``None`` and *select_best_check_rating* is ``False``;
    - no action's capability name matches (e.g. the approach is condition-sourced
      and carries an empty ``capability_name``).

    When *select_best_check_rating* is ``True`` and *approach* is ``None``,
    delegates to :func:`_select_best_rated_action` instead of the naive
    first-match fallback (#2207) — string-matching on ``capability_name`` is
    dead on the condition-sourced path (``capability_name=""``, see
    ``world.mechanics.services._get_condition_sources``), so a caller comparing
    two mechanically-equivalent approaches (e.g. interpose's Reflexes vs.
    Melee-Defense twins) needs a rating-based pick instead. An explicit
    *approach* always wins — this only engages the naive fallback's ``None``
    case.

    Mirrors ``_select_catch_action`` in ``plummet.py`` but is parameterised on the
    approach name rather than hard-coding the catch capability.
    """
    if approach is None and select_best_check_rating:
        return _select_best_rated_action(actor, actions)

    if approach is not None:
        for action in actions:
            source = action.capability_source
            if source is not None and source.capability_name == approach:
                return action
    # No match — fall back to the first available reaction action.
    return actions[0]


def _select_best_rated_action(
    actor: ObjectDB,
    actions: list[AvailableAction],
) -> AvailableAction:
    """Pick the action whose resolved ``check_type`` rates highest for *actor* (#2207).

    Groups *actions* by their resolved approach's ``check_type`` and calls
    :func:`~world.checks.services.compute_check_rating` once per DISTINCT check
    type (never per action — capability-source duplicates of the same check
    type reuse the cached rating), then returns the action backed by the
    higher-rated check type. Deterministic — no dice roll (ADR-0019 keeps the
    one roll inside ``resolve_challenge``/``perform_check``) — and never
    invents an action outside *actions* (ADR-0032): every candidate already
    came from ``get_available_actions``. Ties keep the first action encountered
    (``actions[0]`` order preference).
    """
    from world.checks.services import compute_check_rating  # noqa: PLC0415

    ratings_by_check_type_id: dict[int, int] = {}
    best_action = actions[0]
    best_rating: int | None = None

    for action in actions:
        check_type = action.resolved_check_type
        if check_type is None:
            continue
        if check_type.id not in ratings_by_check_type_id:
            ratings_by_check_type_id[check_type.id] = compute_check_rating(actor, check_type)
        rating = ratings_by_check_type_id[check_type.id]
        if best_rating is None or rating > best_rating:
            best_rating = rating
            best_action = action

    return best_action


def dispatch_capability_reaction(  # noqa: PLR0913
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM
    target_object: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    challenge_name: str,
    approach: str | None,
    error_msg: str,  # noqa: ARG001 — reserved for callers that raise on no-match
    outcome_fn: Callable[[ChallengeResolutionResult], None],
    extra_modifiers: int = 0,
    select_best_check_rating: bool = False,
) -> ChallengeResolutionResult | None:
    """Resolve *actor*'s capability reaction against *target_object* and apply the outcome.

    Shared spine for catch-a-faller and interpose-a-blow (and any future reactive
    capability resolution):

    1. :func:`~world.mechanics.services.get_available_actions` surfaces only the
       reaction approaches *actor*'s capabilities qualify for at their current
       location.
    2. The available actions are filtered to those matching *challenge_name* and
       bound to *target_object* via
       ``resolved_challenge_instance.target_object_id``.
    3. If none match, returns ``None`` (interpose policy: "no challenge — skip").
       Callers that prefer a ``LookupError`` on absence should inspect the result
       and raise themselves.
    4. :func:`_select_reaction_action` picks the action matching *approach*
       (falls back to the first action when *approach* is absent or has no
       exact match) — or, when *select_best_check_rating* is ``True`` and
       *approach* is ``None``, the action whose resolved check type rates
       highest for *actor* (:func:`_select_best_rated_action`, #2207). Opt-in
       and backward compatible: existing callers (Succor, the scene-cover path)
       leave it ``False`` and keep today's first-match behavior.
    5. :func:`~world.mechanics.challenge_resolution.resolve_challenge` resolves
       the chosen approach against the bound instance — the same synchronous
       immediate-challenge path a DANGER round drives.
    6. *outcome_fn* receives the :class:`~world.mechanics.types.ChallengeResolutionResult`
       and applies whatever state change the caller needs.
    7. Returns the result.

    Returns ``None`` when no reaction action is available for this
    *challenge_name* + *target_object* combination.
    """
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415
    from world.mechanics.services import get_available_actions  # noqa: PLC0415

    location = actor.location
    available = get_available_actions(actor, location)

    reaction_actions = [
        action
        for action in available
        if action.challenge_name == challenge_name
        and action.resolved_challenge_instance is not None
        and action.resolved_challenge_instance.target_object_id == target_object.id
    ]

    if not reaction_actions:
        return None

    chosen = _select_reaction_action(
        actor,
        reaction_actions,
        approach,
        select_best_check_rating=select_best_check_rating,
    )

    result = resolve_challenge(
        actor,
        chosen.resolved_challenge_instance,  # type: ignore[arg-type] — filtered non-None above
        chosen.resolved_challenge_approach,  # type: ignore[arg-type] — set whenever instance is
        chosen.capability_source,
        extra_modifiers=extra_modifiers,
    )
    outcome_fn(result)
    return result
