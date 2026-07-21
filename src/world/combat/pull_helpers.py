"""Shared helpers for committing a thread pull as a ``CombatPull`` row.

This module is intentionally thin — it exists so that both the cast-declaration
path (``CastTechniqueAction._commit_combat_pull``) and the clash-contribution
path (``_dispatch_clash_contribution`` in ``actions.player_interface``) can
commit a pull via the same logic without duplicating the error-mapping.

The function is designed to be called at **declaration time** (before the round
resolves) so that the combat read-path — ``_sum_active_flat_bonuses`` and
``compute_intensity_for_clash`` in ``world.combat.services`` — sees the committed
``CombatPull`` row during resolution.

``build_cast_pull_declaration`` is the single ID→declaration resolver for the web
path: given the caster's sheet PK plus ``resonance_id`` / ``tier`` / ``thread_ids``
IDs (as sent by the frontend over JSON), it resolves ORM instances and builds a
``CastPullDeclaration``.  Accepting an ``int`` instead of a ``CharacterSheet``
instance avoids a superfluous SELECT when the caller holds only a cached FK id
(e.g. ``persona.character_sheet_id``).  The non-combat cast serializer
(``world.scenes.action_serializers._validate_cast_pull``) delegates its core
resolution to this helper so the logic lives in exactly one place.

``resolve_pull_from_kwargs`` normalises the two entry points — a pre-built
``CastPullDeclaration`` object (telnet) and raw pull IDs (web) — into a single
``CastPullDeclaration | None``.  Both combat seams
(``CastTechniqueAction.round_declaration`` and
``_dispatch_clash_contribution``) call this helper instead of reading
``kwargs["cast_pull"]`` directly so both transports converge transparently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatParticipant
    from world.covenants.perks.context import SituationContext
    from world.magic.types.pull import CastPullDeclaration


def build_cast_pull_declaration(
    owner_sheet_id: int,
    *,
    resonance_id: int,
    tier: int,
    thread_ids: list[int],
) -> CastPullDeclaration:
    """Resolve raw pull IDs into a ``CastPullDeclaration`` scoped to *owner_sheet_id*.

    This is the single ID→declaration resolver shared between the web combat
    dispatch path (which sends JSON IDs) and the non-combat cast serializer
    (``world.scenes.action_serializers._validate_cast_pull``).  Telnet passes
    pre-built ``CastPullDeclaration`` objects and does not use this function.

    Args:
        owner_sheet_id: PK of the caster's ``CharacterSheet``; threads must be owned
            by this sheet.  Accepting an ``int`` instead of the ORM instance avoids an
            extra SELECT when the caller already holds the cached FK id (e.g.
            ``persona.character_sheet_id`` or ``sheet.pk`` on a loaded instance).
        resonance_id: PK of the ``Resonance`` the pull is declared on.
        tier: Pull tier (1–3).
        thread_ids: Ordered list of ``Thread`` PKs to include in the pull.

    Returns:
        A ``CastPullDeclaration`` carrying the resolved ``Resonance`` instance and
        the resolved ``Thread`` queryset (as a tuple).

    Raises:
        ``world.magic.exceptions.InvalidImbueAmount``: When *resonance_id* does not
            exist, or any thread id is unknown, retired, belongs to a different
            sheet, or does not match the given resonance.  A single ``InvalidImbueAmount``
            is raised rather than distinct per-field errors so that callers can catch
            at the ``MagicError`` boundary; the DRF serializer maps it to a
            ``ValidationError`` at the serializer boundary.
    """
    from world.magic.exceptions import InvalidImbueAmount  # noqa: PLC0415
    from world.magic.models import Resonance, Thread  # noqa: PLC0415
    from world.magic.types.pull import CastPullDeclaration as _CastPullDeclaration  # noqa: PLC0415

    try:
        resonance = Resonance.objects.get(pk=resonance_id)
    except Resonance.DoesNotExist:
        msg = "Unknown resonance."
        raise InvalidImbueAmount(msg) from None

    threads = list(
        Thread.objects.filter(
            pk__in=thread_ids,
            owner_id=owner_sheet_id,
            resonance_id=resonance.pk,
            retired_at__isnull=True,
        )
    )
    if len(threads) != len(thread_ids):
        msg = (
            "Each pulled thread must exist, be active, be yours, match the "
            "resonance, and appear only once."
        )
        raise InvalidImbueAmount(msg)

    return _CastPullDeclaration(
        resonance=resonance,
        tier=tier,
        threads=tuple(threads),
    )


def resolve_pull_from_kwargs(
    sheet: CharacterSheet,
    kwargs: dict[str, Any],
) -> CastPullDeclaration | None:
    """Normalise telnet-object and web-ID pull kwargs into a ``CastPullDeclaration``.

    Two transports reach the combat pull seams:

    - **Telnet** passes ``cast_pull`` as a pre-built ``CastPullDeclaration``
      (ORM instances already resolved by the command parser).
    - **Web** passes raw IDs: ``pull_resonance_id`` (int), ``pull_tier`` (int),
      ``pull_thread_ids`` (list[int]).

    This helper normalises both into a single ``CastPullDeclaration | None`` so
    both combat seams (``CastTechniqueAction.round_declaration`` and
    ``_dispatch_clash_contribution``) can call it instead of reading
    ``kwargs["cast_pull"]`` directly.

    Args:
        sheet: The caster's ``CharacterSheet``; used only for the ID path (web).
        kwargs: The raw dispatch kwargs dict.

    Returns:
        - The pre-built ``CastPullDeclaration`` from ``kwargs["cast_pull"]`` when
          present (telnet path — no DB queries needed).
        - A newly-built ``CastPullDeclaration`` from ``pull_resonance_id`` /
          ``pull_tier`` / ``pull_thread_ids`` when those keys are present (web path).
        - ``None`` when neither form is present (no pull declared).

    Raises:
        ``world.magic.exceptions.InvalidImbueAmount``: Propagated from
            ``build_cast_pull_declaration`` when any web-form ID is invalid.
        ``actions.errors.ActionDispatchError``: With ``PULL_INVALID`` wrapping an
            ``InvalidImbueAmount`` at the combat-seam call sites (the helpers above
            this layer map the MagicError; this function does not).
    """
    from world.magic.types.pull import CastPullDeclaration as _CastPullDeclaration  # noqa: PLC0415

    # Telnet path: pre-built CastPullDeclaration object already in kwargs.
    cast_pull = kwargs.get("cast_pull")
    if isinstance(cast_pull, _CastPullDeclaration):
        return cast_pull

    # Web path: raw IDs passed via JSON kwargs.
    resonance_id = kwargs.get("pull_resonance_id")
    tier = kwargs.get("pull_tier")
    thread_ids = kwargs.get("pull_thread_ids")
    if resonance_id is not None and tier is not None and thread_ids is not None:
        return build_cast_pull_declaration(
            sheet.pk,
            resonance_id=int(resonance_id),
            tier=int(tier),
            thread_ids=[int(t) for t in thread_ids],
        )

    return None


def commit_combat_pull(
    cast_pull: CastPullDeclaration,
    participant: CombatParticipant,
    encounter: CombatEncounter,
    technique_id: int,
    target: ObjectDB | None = None,
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

    When ``cast_pull.beseech_bonus > 0``, rolls the shared Court-grant petition
    check (#1718) before committing: success applies the bonus to this pull's
    resolution (via ``resolve_pull_effects``'s per-thread override) and, if the
    bonus exceeds the servant's current ``court_grant_ceiling`` for the thread's
    covenant, calls ``incur_npc_debt`` for the excess; failure commits the pull
    with NO bonus (the base pull still resolves normally). Either way,
    ``record_court_grant_petition_outcome`` fires (recording the streak and,
    on threshold-crossing, the master's escalation ConsequencePool).

    Args:
        cast_pull: The ``CastPullDeclaration`` carrying resonance, tier, and threads.
        participant: The ``CombatParticipant`` making the pull.
        encounter: The ``CombatEncounter`` the participant belongs to.
        technique_id: PK of the technique involved (used for anchor validation).
        target: The live focused target this pull's action is directed at (#1831);
            ``None`` when the action has no resolvable target. Threaded through to
            ``PullActionContext.target``, which feeds ``court_regard_modulation``
            for COVENANT_ROLE pulls via ``resolve_pull_effects``.

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
        target=target,
    )

    beseech_bonus_thread_id = None
    applied_bonus = 0
    if cast_pull.beseech_bonus > 0:
        # #2536 Task 5 review fix: this combat call site has `participant` +
        # `encounter` on hand — the same ingredients every other combat check
        # threads — so hand the petition check a live round context. A future
        # CHECK_BONUS situational perk scoped to the Court petition CheckType
        # (spec §4's named use case) must not silently never fire just because
        # this sibling roll skipped the seam. `target` is None: the petition is
        # a Court-favor roll about the servant↔master bond, not directed at the
        # pull's combat target.
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        situation_ctx = SituationContext(
            holder=sheet,
            subject=sheet,
            target=None,
            resolution=CombatRoundContext(participant),
        )
        beseech_bonus_thread_id, applied_bonus = _resolve_emergency_draw(
            sheet, cast_pull, situation_ctx=situation_ctx
        )

    try:
        spend_resonance_for_pull(
            character_sheet=sheet,
            resonance=cast_pull.resonance,
            tier=cast_pull.tier,
            threads=list(cast_pull.threads),
            action_context=action_context,
            beseech_bonus_thread_id=beseech_bonus_thread_id,
            beseech_bonus=applied_bonus,
        )
    except IntegrityError as exc:
        raise ActionDispatchError(ActionDispatchError.PULL_ALREADY_COMMITTED) from exc
    except MagicError as exc:
        raise ActionDispatchError(ActionDispatchError.PULL_INVALID) from exc


def _resolve_emergency_draw(
    sheet: CharacterSheet,
    cast_pull: CastPullDeclaration,
    *,
    situation_ctx: SituationContext | None = None,
) -> tuple[int | None, int]:
    """Roll the Court-grant petition check for an emergency thread-bond draw (#1718).

    Takes only ``sheet`` + ``cast_pull`` — no ``CombatEncounter``/``CombatParticipant`` —
    so it is combat-agnostic and reused directly by the non-combat cast path
    (``world.magic.services.techniques._charge_cast_pull``) as well as
    ``commit_combat_pull`` below. Do not add a combat-only parameter here.

    ``situation_ctx`` is the ONE exception — and it is not combat-only. It is the
    general per-vow situational-perk seam (#2536): the combat caller
    (``commit_combat_pull``) builds one from its live ``CombatRoundContext`` so a
    ``CHECK_BONUS`` perk scoped to the Court petition CheckType (spec §4) can fire
    on this roll; the non-combat caller (``_charge_cast_pull``) passes ``None``
    because a petition outside combat has no combat positioning to evaluate
    (combat-positioning situations simply never hold — the evaluators return
    ``False`` on a ``None`` resolution). Threaded straight into ``perform_check``.

    Returns ``(thread_id, applied_bonus)`` — ``(None, 0)`` on failure or when the
    pulled thread isn't a COURT-covenant COVENANT_ROLE thread (nothing to
    beseech), or when the covenant has no configured petition check type. On
    success, the requested bonus is clamped so it may exceed the servant's
    current ``court_grant_ceiling`` by at most
    ``CourtGrantConfig.emergency_draw_max_bonus`` (per that field's authored
    meaning — see ``world/covenants/models.py::CourtGrantConfig``); any amount
    past the ceiling incurs debt via ``incur_npc_debt``.
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.covenants.constants import CovenantType  # noqa: PLC0415
    from world.covenants.court_grant import (  # noqa: PLC0415
        completed_court_mission_count,
        court_grant_ceiling,
        court_grant_petition_ease,
        record_court_grant_petition_outcome,
    )
    from world.covenants.models import Covenant  # noqa: PLC0415
    from world.covenants.services import get_court_grant_config  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.npc_services.models import NPCStanding  # noqa: PLC0415
    from world.npc_services.services import incur_npc_debt  # noqa: PLC0415

    court_thread = next(
        (
            t
            for t in cast_pull.threads
            if t.target_kind == TargetKind.COVENANT_ROLE
            and t.target_covenant_role.covenant_type == CovenantType.COURT
        ),
        None,
    )
    if court_thread is None:
        return None, 0

    covenant = Covenant.objects.filter(
        covenant_type=CovenantType.COURT,
        leader__isnull=False,
        memberships__character_sheet=sheet,
        memberships__covenant_role=court_thread.target_covenant_role,
        memberships__left_at__isnull=True,
    ).first()
    if covenant is None or covenant.leader_id is None:
        return None, 0

    config = get_court_grant_config()
    if config.petition_check_type_id is None:
        return None, 0

    master_persona = covenant.leader.primary_persona
    servant_persona = sheet.primary_persona
    standing, _ = NPCStanding.objects.get_or_create(
        persona=servant_persona, npc_persona=master_persona
    )
    ease = court_grant_petition_ease(standing=standing, config=config)
    check_result = perform_check(
        sheet.character,
        config.petition_check_type,
        target_difficulty=config.petition_base_difficulty,
        extra_modifiers=ease,
        situation_ctx=situation_ctx,
    )
    # CheckResult.success_level (world.checks.types) safely returns 0 when
    # outcome is None — no separate None-check needed.
    succeeded = check_result.success_level > 0
    # record_court_grant_petition_outcome (not the bare record_petition_outcome)
    # so this channel fires the master's escalation ConsequencePool on
    # threshold-crossing too (#1718 final-review Finding 2) — previously this
    # channel recorded the streak but never fired escalation, so a servant who
    # only ever used emergency draws could never trigger the master's wrath.
    record_court_grant_petition_outcome(
        standing,
        succeeded=succeeded,
        check_result=check_result,
        character=sheet.character,
        config=config,
    )
    if not succeeded:
        return None, 0

    # emergency_draw_max_bonus bounds how far the draw may exceed the ceiling
    # (its authored meaning), not the raw requested bonus — so clamp against
    # ceiling + max_bonus, not max_bonus alone.
    ceiling = court_grant_ceiling(covenant=covenant, servant_sheet=sheet)
    bonus = min(cast_pull.beseech_bonus, ceiling + config.emergency_draw_max_bonus)
    if bonus > ceiling:
        completed_missions = completed_court_mission_count(character_sheet=sheet, covenant=covenant)
        incur_npc_debt(
            standing,
            bonus - ceiling,
            current_affection=standing.affection,
            current_missions_completed=completed_missions,
        )
    return court_thread.pk, bonus
