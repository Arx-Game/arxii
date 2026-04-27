"""Atomic transition save service — creates a Transition + its
TransitionRequiredOutcome rows in a single transaction.

Public API:
    save_transition_with_outcomes(transition_data, outcomes, existing_transition)
        — atomically create or update a Transition and replace its routing predicates.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from world.stories.constants import BeatOutcome
from world.stories.models import Transition, TransitionRequiredOutcome


@dataclass
class OutcomeInput:
    """Validated routing predicate row passed to the service."""

    beat_id: int
    required_outcome: BeatOutcome


def save_transition_with_outcomes(
    *,
    transition_data: dict[str, object],
    outcomes: list[OutcomeInput],
    existing_transition: Transition | None = None,
) -> Transition:
    """Atomically create or update a Transition and its TransitionRequiredOutcome rows.

    On create:
        - Creates a new Transition from ``transition_data``.
        - Creates one TransitionRequiredOutcome per entry in ``outcomes``.

    On update (``existing_transition`` provided):
        - Applies ``transition_data`` fields to the existing Transition and saves.
        - Deletes all existing TransitionRequiredOutcome rows on that transition.
        - Creates fresh rows from ``outcomes``.

    If any step raises, the transaction rolls back — no partial state persists.

    Service receives pre-validated inputs; permission gating and field
    validation happen at the view/serializer layer.  The only defensive
    checks here guard against programmer errors (wrong FK, etc.).

    Args:
        transition_data: Serializer-validated fields for the Transition model.
        outcomes: List of OutcomeInput dataclasses (beat_id + required_outcome).
        existing_transition: If updating, the Transition to modify.  None for create.

    Returns:
        The saved (or newly created) Transition instance.
    """
    with transaction.atomic():
        if existing_transition is not None:
            # Apply all validated field values in-place.
            for k, v in transition_data.items():
                setattr(existing_transition, k, v)
            existing_transition.save()
            transition = existing_transition
            # Replace routing predicates with the new set.
            transition.required_outcomes.all().delete()
        else:
            transition = Transition.objects.create(**transition_data)

        for outcome in outcomes:
            if outcome.beat_id <= 0:
                msg = (
                    f"OutcomeInput.beat_id must be a positive integer; "
                    f"got {outcome.beat_id!r}. Serializer should have rejected this."
                )
                raise ValueError(msg)
            TransitionRequiredOutcome.objects.create(
                transition=transition,
                beat_id=outcome.beat_id,
                required_outcome=outcome.required_outcome,
            )

    return transition
