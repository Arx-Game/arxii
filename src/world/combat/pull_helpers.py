"""Shared helper for committing a thread pull as a ``CombatPull`` row.

This module is intentionally thin — it exists so that both the cast-declaration
path (``CastTechniqueAction._commit_combat_pull``) and the clash-contribution
path (``_dispatch_clash_contribution`` in ``actions.player_interface``) can
commit a pull via the same logic without duplicating the error-mapping.

The function is designed to be called at **declaration time** (before the round
resolves) so that the combat read-path — ``_sum_active_flat_bonuses`` and
``compute_intensity_for_clash`` in ``world.combat.services`` — sees the committed
``CombatPull`` row during resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.magic.types.pull import CastPullDeclaration


def commit_combat_pull(
    cast_pull: CastPullDeclaration,
    participant: CombatParticipant,
    encounter: CombatEncounter,
    technique_id: int,
) -> None:
    """Commit *cast_pull* as a ``CombatPull`` row for the current round.

    Calls ``spend_resonance_for_pull`` with a ``PullActionContext`` so:

    1. A ``CombatPull`` row is persisted (unique per ``(participant, round_number)``).
    2. Resonance and anima are debited atomically.
    3. ``CombatPullResolvedEffect`` snapshots are written for the read-path
       (``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``).

    This helper is shared between the cast-declaration path
    (``CastTechniqueAction``) and the clash-contribution path
    (``_dispatch_clash_contribution``) so the commit logic is not duplicated.

    Args:
        cast_pull: The ``CastPullDeclaration`` carrying resonance, tier, and threads.
        participant: The ``CombatParticipant`` making the pull.
        encounter: The ``CombatEncounter`` the participant belongs to.
        technique_id: PK of the technique involved (used for anchor validation).

    Raises:
        ActionDispatchError(PULL_ALREADY_COMMITTED): When the
            ``(participant, round_number)`` unique constraint fires (duplicate
            pull in the same round).
        ActionDispatchError(PULL_INVALID): When ``spend_resonance_for_pull``
            raises a ``MagicError`` (invalid pull declaration — e.g. thread not
            in action, insufficient resonance balance).
    """
    from django.db import IntegrityError  # noqa: PLC0415

    from actions.errors import ActionDispatchError  # noqa: PLC0415
    from world.magic.exceptions import MagicError  # noqa: PLC0415
    from world.magic.services.resonance import spend_resonance_for_pull  # noqa: PLC0415
    from world.magic.types.pull import PullActionContext  # noqa: PLC0415

    sheet = participant.character_sheet

    action_context = PullActionContext(
        combat_encounter=encounter,
        participant=participant,
        involved_techniques=(technique_id,),
    )

    try:
        spend_resonance_for_pull(
            character_sheet=sheet,
            resonance=cast_pull.resonance,
            tier=cast_pull.tier,
            threads=list(cast_pull.threads),
            action_context=action_context,
        )
    except IntegrityError as exc:
        raise ActionDispatchError(ActionDispatchError.PULL_ALREADY_COMMITTED) from exc
    except MagicError as exc:
        raise ActionDispatchError(ActionDispatchError.PULL_INVALID) from exc
