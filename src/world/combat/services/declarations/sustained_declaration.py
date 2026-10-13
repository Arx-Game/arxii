"""Declaring sustained rituals and technique sustains."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from world.combat.constants import ParticipantStatus, SustainedKind
from world.combat.models import CombatParticipant, CombatRoundAction, SustainedAction
from world.combat.services.encounter.sustained_absorption import roll_sustained_absorption_budget
from world.combat.services.npc.sustained_narration import _broadcast_sustained_telegraph
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Ritual, Technique


def _sync_sustained_technique_declaration(
    participant: CombatParticipant,
    action: CombatRoundAction,
    technique: Technique | None,
) -> SustainedAction | None:
    """Create (or clear) this round's SustainedAction commitment for *technique* (#2705).

    Called unconditionally from ``declare_action`` (no branch there — keeps its
    cyclomatic complexity down) so re-declaration is always synced: any
    existing TECHNIQUE-kind SustainedAction for ``(participant, declared_round=
    encounter.round_number)`` is deleted first — a player re-declaring the same
    round's action, whether to the same winding-up technique or to something
    else entirely, must never stack a second row — and a new one is created
    only when ``technique`` is set and ``technique.windup_rounds > 0``. Rolls
    Concentration once (via ``roll_sustained_absorption_budget``) each time a
    commitment is (re-)declared.

    Scoped to ``sustained_kind=SustainedKind.TECHNIQUE`` (#2705 adversarial
    review, Fix 2a): a RITUAL row for the same ``(participant, declared_round)``
    is created through a completely different seam
    (``try_declare_sustained_ritual``, called from ``PerformRitualAction`` —
    never from ``declare_action``), and its components were already consumed
    at declaration. An unscoped delete here would silently strand a sustained
    ritual's already-consumed components the moment the player declared
    anything else that same round — no narration, no refund, the commitment
    simply vanishes. ``_validate_no_pending_sustained`` (called earlier in
    ``declare_action``) now blocks that combat declaration outright while a
    RITUAL commitment is pending (Fix 2b), so in practice this delete should
    never even see a RITUAL row for this participant — but scoping it
    correctly here is the actual fix; the validation is defense in depth.
    """
    encounter = participant.encounter
    SustainedAction.objects.filter(
        participant=participant,
        declared_round=encounter.round_number,
        sustained_kind=SustainedKind.TECHNIQUE,
    ).delete()

    if technique is None or technique.windup_rounds <= 0:
        return None

    budget, outcome = roll_sustained_absorption_budget(participant)
    sustained = SustainedAction.objects.create(
        encounter=encounter,
        participant=participant,
        sustained_kind=SustainedKind.TECHNIQUE,
        technique=technique,
        declared_action=action,
        declared_round=encounter.round_number,
        resolves_round=encounter.round_number + technique.windup_rounds,
        absorption_budget=budget,
        outcome_snapshot=outcome,
    )
    _broadcast_sustained_telegraph(sustained)
    return sustained


def try_declare_sustained_ritual(
    *,
    sheet: CharacterSheet,
    ritual: Ritual,
    kwargs: dict[str, Any],
) -> SustainedAction | None:
    """Defer a combat-cast ritual across rounds instead of dispatching now (#2705, Task 5).

    Called by ``PerformRitualAction.execute()`` after components are validated
    and consumed (so a broken commitment is genuinely spent — components are
    never refunded, mirroring ``_mature_one_sustained_action``'s TECHNIQUE
    ruling) and before dispatch. Returns ``None`` — "not sustained, dispatch
    immediately as today" — unless ALL of the following hold:

    - the performer resolves to an ACTIVE ``CombatParticipant`` whose
      encounter is currently DECLARING;
    - ``ritual.check_config_or_none`` is not ``None`` and its
      ``sustained_rounds > 0``;
    - ``kwargs`` is empty (see below);
    - the participant is not already holding an earlier-round commitment —
      mirrors ``_validate_no_pending_sustained``'s D2 guard
      (``declared_round < round_number``, ``resolves_round >= round_number``).
      Unlike that function this does not raise: a ritual invocation is not
      the round-declaration seam, so blocking it outright would strand the
      components already consumed inside the same atomic transaction. Instead
      it falls through to immediate dispatch, same as any other inert case —
      a player cannot stack two parallel sustained commitments, but a ritual
      cast while one is already pending simply isn't deferred.

    **The ADR-0007 kwargs guard.** A ``SustainedAction`` is a DB row with
    fixed columns; persisting an arbitrary per-cast kwargs dict to replay at
    maturation would need a JSON field, which ADR-0007 forbids. A ritual
    invoked with non-empty kwargs (e.g. a ``thread`` target) therefore cannot
    be deferred — it dispatches immediately, exactly as it would outside
    combat. Rituals authored with ``sustained_rounds > 0`` are expected to be
    no-kwargs SERVICE/FLOW calls for this reason.

    When it fires: rolls the absorption budget once
    (``roll_sustained_absorption_budget``, the same helper the TECHNIQUE
    declaration path uses), creates the ``SustainedAction`` (kind RITUAL,
    ``declared_action=None`` — a ritual is declared through
    ``PerformRitualAction``, not the combat round-declaration seam),
    broadcasts the telegraph, and returns the row. Same same-round-
    replacement idempotence as ``_sync_sustained_technique_declaration``: any
    existing ``SustainedAction`` for ``(participant, declared_round=this
    round)`` is replaced, never stacked, so re-performing the ritual the same
    round does not accumulate duplicate commitments.
    """
    if kwargs:
        return None

    check_config = ritual.check_config_or_none
    if check_config is None or check_config.sustained_rounds <= 0:
        return None

    participant = (
        CombatParticipant.objects.filter(
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )
        .select_related("encounter")
        .first()
    )
    if participant is None:
        return None

    encounter = participant.encounter
    if encounter.status != RoundStatus.DECLARING:
        return None

    # ``resolves_round__gte``, not ``__gt``: a commitment maturing THIS round is
    # still being held during DECLARING — ``resolve_round`` has not run yet, so
    # it has not matured. With ``__gt`` a player could stack a second live
    # commitment on their own maturation round, which the "cannot stack two
    # parallel commitments" invariant below forbids. Same off-by-one that made
    # ``_validate_no_pending_sustained`` crash ``resolve_round``.
    already_holding = SustainedAction.objects.filter(
        participant=participant,
        declared_round__lt=encounter.round_number,
        resolves_round__gte=encounter.round_number,
    ).exists()
    if already_holding:
        return None

    SustainedAction.objects.filter(
        participant=participant, declared_round=encounter.round_number
    ).delete()

    budget, outcome = roll_sustained_absorption_budget(participant)
    sustained = SustainedAction.objects.create(
        encounter=encounter,
        participant=participant,
        sustained_kind=SustainedKind.RITUAL,
        ritual=ritual,
        declared_action=None,
        declared_round=encounter.round_number,
        resolves_round=encounter.round_number + check_config.sustained_rounds,
        absorption_budget=budget,
        outcome_snapshot=outcome,
    )
    _broadcast_sustained_telegraph(sustained)
    return sustained
