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
    from world.character_sheets.models import CharacterSheet
    from world.combat.models import CombatEncounter, CombatParticipant
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
