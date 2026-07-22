"""Distinction services (#1334) — relocating a distinction into a Secret.

A sensitive distinction is *relocated* into a :class:`~world.secrets.models.Secret`: the
``CharacterDistinction.secret`` back-reference is the privacy primitive. Minting one drops the
distinction off the public distinctions list (the profile serializer hides it) and makes it
learnable through the clue loop; clearing it makes the distinction public again. The FK's
presence is the secret-state — there is no separate flag to keep in sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.distinctions.exceptions import (
    DistinctionExclusionError,
    SheetUpdateRequestError,
)
from world.distinctions.types import DistinctionOrigin
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import (
        CharacterDistinction,
        Distinction,
        SheetUpdateRequest,
    )
    from world.scenes.models import Persona


def mint_distinction_secret(
    character_distinction: CharacterDistinction,
    *,
    level: int | None = None,
    provenance: str = SecretProvenance.GM_AUTHORED,
    author_persona: Persona | None = None,
    content: str = "",
) -> Secret:
    """Relocate a distinction into a Secret, returning it (#1334).

    Idempotent: if the distinction already has a secret, returns the existing one untouched.
    ``level`` defaults to the distinction kind's ``default_secret_level``; ``content`` defaults
    to the distinction name (a terse, player-editable seed per the legend-deed trust model).
    The default ``GM_AUTHORED`` provenance fits staff-curated ``secret_by_default`` kinds (canon,
    any level); a player self-gating a public distinction passes ``PLAYER_FLAVOR`` + level 1.
    """
    if character_distinction.secret_id is not None:
        return character_distinction.secret
    distinction = character_distinction.distinction
    secret = Secret.objects.create(
        subject_sheet=character_distinction.character,
        level=level if level is not None else distinction.default_secret_level,
        provenance=provenance,
        author_persona=author_persona,
        content=content or distinction.name,
    )
    character_distinction.secret = secret
    character_distinction.save(update_fields=["secret", "updated_at"])
    return secret


def clear_distinction_secret(character_distinction: CharacterDistinction) -> None:
    """Make a relocated distinction public again by deleting its Secret (#1334).

    Deleting the Secret cascades a ``SET_NULL`` onto the back-reference, so the distinction
    returns to the public distinctions list. No-op if it has no secret.
    """
    if character_distinction.secret_id is None:
        return
    secret = character_distinction.secret
    character_distinction.secret = None
    character_distinction.save(update_fields=["secret", "updated_at"])
    secret.delete()


def _check_exclusions(character: CharacterSheet, distinction: Distinction) -> None:
    """Service-layer port of ``DraftDistinctionViewSet._check_mutual_exclusions``/
    ``_check_variant_exclusions`` (#2037 Decision 2).

    The view-layer checks raise DRF ``ValidationError`` inline — the wrong exception
    type for a seam with non-HTTP callers (GM action, achievement engine,
    consequence-effect handler, resonance-threshold check). This is the equivalent
    check against a character's currently-held distinctions, raising
    ``DistinctionExclusionError`` instead.
    """
    from world.distinctions.models import (  # noqa: PLC0415
        CharacterDistinction,
        Distinction as DistinctionModel,
    )

    existing_ids = set(
        CharacterDistinction.objects.filter(character=character)
        .exclude(distinction=distinction)
        .values_list("distinction_id", flat=True)
    )
    if not existing_ids:
        return

    excluded_ids = set(distinction.mutually_exclusive_with.values_list("id", flat=True))
    conflicts = existing_ids & excluded_ids
    if conflicts:
        conflicting = DistinctionModel.objects.filter(id__in=conflicts).first()
        msg = f"Mutually exclusive with {conflicting.name}."
        raise DistinctionExclusionError(msg)

    parent = distinction.parent_distinction
    if parent and parent.variants_are_mutually_exclusive:
        sibling_ids = set(parent.variants.exclude(id=distinction.id).values_list("id", flat=True))
        conflicts = existing_ids & sibling_ids
        if conflicts:
            conflicting = DistinctionModel.objects.filter(id__in=conflicts).first()
            msg = f"Can only select one {parent.name} variant."
            raise DistinctionExclusionError(msg)


def grant_distinction(
    character: CharacterSheet,
    distinction: Distinction,
    *,
    origin: str,
    rank: int | None = None,
    source_description: str = "",
) -> CharacterDistinction:
    """Grant a Distinction, or rank one up, through the single acquisition seam (#2037).

    ``rank=None`` advances one step — 1 for a new grant; ``current.rank + 1`` (clamped to
    ``distinction.max_rank``, no-op returning the row unchanged if already at max) for an
    existing holder. An explicit ``rank`` sets/raises only — never lowers (no-op if
    ``rank <= current.rank``); monotonic, matching the "rank-down never claws back" ethos
    already established by ``reconcile_distinction_resonance_grants``.

    ``origin`` records the distinction's ORIGINAL acquisition provenance and is never
    rewritten by a rank-up — a GM re-award of an endorsement-earned distinction keeps
    ``ENDORSEMENT_THRESHOLD``. Deliberate (#2037 review): provenance is first-acquisition
    history, not latest touch.

    Internally: mutual/variant exclusion check (raises ``DistinctionExclusionError``) ->
    branch on existing ``CharacterDistinction`` -> create
    (``world.mechanics.services.create_distinction_modifiers``) or bump-and-recalculate
    (``update_distinction_rank``) -> narrate via ``send_narrative_message`` -> return the row.

    This is the only writer of ``CharacterDistinction`` outside CG finalization and Django
    admin; every in-play acquisition source (GM award, achievement auto-grant,
    consequence-pool effect, endorsement/resonance threshold) calls this — none re-implements
    the create/rank-up branching.
    """
    from world.distinctions.models import CharacterDistinction  # noqa: PLC0415
    from world.mechanics.services import (  # noqa: PLC0415
        create_distinction_modifiers,
        update_distinction_rank,
    )
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    _check_exclusions(character, distinction)

    existing = CharacterDistinction.objects.filter(
        character=character, distinction=distinction
    ).first()

    with transaction.atomic():
        if existing is None:
            new_rank = rank or 1
            char_distinction = CharacterDistinction.objects.create(
                character=character,
                distinction=distinction,
                rank=new_rank,
                origin=origin,
                source_description=source_description,
            )
            create_distinction_modifiers(char_distinction)
            is_new = True
        else:
            new_rank = min(existing.rank + 1, distinction.max_rank) if rank is None else rank
            if new_rank <= existing.rank:
                # No-op: already at max_rank (rank=None), or an explicit rank that
                # doesn't raise the current rank.
                return existing
            existing.rank = new_rank
            existing.save(update_fields=["rank", "updated_at"])
            update_distinction_rank(existing)
            char_distinction = existing
            is_new = False

    if is_new:
        body = f"You have gained the distinction: {distinction.name}."
    else:
        body = f"Your distinction {distinction.name} has advanced to rank {new_rank}."
    send_narrative_message(
        recipients=[character],
        body=body,
        category=NarrativeCategory.ABILITY,
        sender_account=None,
    )

    return char_distinction


def compute_sheet_update_xp_cost(
    request_type: str,
    distinction: Distinction,
    rank: int,
) -> int:
    """Compute the XP cost for a sheet-update request.

    Sign-based model: pay XP when net-gaining mechanical advantage, free when
    net-losing it. The sign of ``cost_per_rank`` encodes beneficial (positive)
    vs detrimental (negative).

    - ADD a positive distinction (beneficial): costs XP.
    - ADD a negative distinction (detrimental): free.
    - REMOVE a positive distinction (beneficial): free.
    - REMOVE a negative distinction (detrimental): costs XP.

    No friction multiplier, no 2x factor — the points-pump loophole is closed
    because adding a negative (free) and later removing it (costs XP) is never
    profitable.

    Args:
        request_type: ``SheetUpdateRequestType.DISTINCTION_ADD`` or ``DISTINCTION_REMOVE``.
        distinction: The distinction being added or removed.
        rank: For ADD, the target rank. For REMOVE, the CharacterDistinction's current rank.

    Returns:
        The XP cost (always non-negative; 0 for free transactions).
    """
    from world.distinctions.types import SheetUpdateRequestType  # noqa: PLC0415

    if request_type == SheetUpdateRequestType.DISTINCTION_ADD:
        return abs(distinction.cost_per_rank) * rank if distinction.cost_per_rank > 0 else 0
    if request_type == SheetUpdateRequestType.DISTINCTION_REMOVE:
        return abs(distinction.cost_per_rank) * rank if distinction.cost_per_rank < 0 else 0
    return 0


# Backwards-compat alias — old imports still work during migration.
compute_distinction_change_xp_cost = compute_sheet_update_xp_cost


def _check_removal_prerequisites(character_distinction: CharacterDistinction) -> None:
    """Check that no other held distinction depends on the one being removed.

    Stub — DistinctionPrerequisite uses rule_json, no production rows reference
    distinctions as prerequisites yet. TODO: proper rule evaluation.
    """


def remove_distinction(
    character_distinction: CharacterDistinction,
    *,
    sheet_update_request: SheetUpdateRequest,
) -> None:
    """Remove a CharacterDistinction, reconciling all dependent systems.

    The inverse of ``grant_distinction``. Requires a valid (APPROVED)
    ``SheetUpdateRequest`` with ``request_type=DISTINCTION_REMOVE`` targeting this row.

    Teardown order:
    1. ``delete_distinction_modifiers`` — removes CharacterModifier + ModifierSource rows.
    2. ``clear_distinction_secret`` — deletes the Secret if present (idempotent).
    3. ``CharacterDistinction.delete()`` — CASCADE handles remaining FKs.

    The request's ``status`` / ``reviewed_at`` are marked by the CALLER
    (``approve_sheet_update_request``), NOT by this function.

    NOT torn down (by design):
    - ``CharacterResonance`` currency (monotonic, no clawback — #2037).
    - ``NPCAsset`` (world entity, nullable FK orphans).
    - CodexEntry grants (knowledge can't be unlearned).
    - ``ActionEnhancement`` (auto-disabled when CharacterDistinction row is gone).

    Args:
        character_distinction: The CharacterDistinction to remove.
        sheet_update_request: The approved SheetUpdateRequest authorizing this removal.

    Raises:
        SheetUpdateRequestError: If the request is not APPROVED or doesn't target
            this CharacterDistinction.
    """
    from world.distinctions.exceptions import SheetUpdateRequestError  # noqa: PLC0415
    from world.distinctions.types import (  # noqa: PLC0415
        SheetUpdateRequestStatus,
        SheetUpdateRequestType,
    )
    from world.mechanics.services import delete_distinction_modifiers  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if sheet_update_request.status != SheetUpdateRequestStatus.APPROVED:
        msg = "This sheet update request has not been approved."
        raise SheetUpdateRequestError(msg)
    if (
        sheet_update_request.request_type != SheetUpdateRequestType.DISTINCTION_REMOVE
        or sheet_update_request.target_character_distinction_id != character_distinction.pk
    ):
        msg = "This request does not target this distinction."
        raise SheetUpdateRequestError(msg)

    _check_removal_prerequisites(character_distinction)

    with transaction.atomic():
        delete_distinction_modifiers(character_distinction)
        clear_distinction_secret(character_distinction)

        distinction_name = character_distinction.distinction.name
        character_sheet = sheet_update_request.character_sheet
        character_distinction.delete()

    send_narrative_message(
        recipients=[character_sheet],
        body=f"You have shed the distinction: {distinction_name}.",
        category=NarrativeCategory.ABILITY,
        sender_account=None,
    )


def create_sheet_update_request(  # noqa: PLR0913
    character_sheet: CharacterSheet,
    request_type: str,
    *,
    justification: str,
    target_distinction: Distinction | None = None,
    target_character_distinction: CharacterDistinction | None = None,
    submitted_by: object | None = None,
    origin: str = DistinctionOrigin.UNLOCK_PURCHASE,
) -> SheetUpdateRequest:
    """Create a PENDING SheetUpdateRequest.

    Computes ``xp_cost`` at creation time (stamped, not recomputed at
    approval). For DISTINCTION_ADD, a distinction the character already holds
    is allowed — it's a rank-up request. Runs exclusion checks at submission.
    """
    from world.distinctions.models import SheetUpdateRequest  # noqa: PLC0415
    from world.distinctions.types import (  # noqa: PLC0415
        SheetUpdateRequestStatus,
        SheetUpdateRequestType,
    )

    if request_type == SheetUpdateRequestType.DISTINCTION_ADD:
        if target_distinction is None:
            msg = "DISTINCTION_ADD requires target_distinction."
            raise SheetUpdateRequestError(msg)
        _check_exclusions(character_sheet, target_distinction)
        rank = 1
        xp_cost = compute_sheet_update_xp_cost(request_type, target_distinction, rank)
    elif request_type == SheetUpdateRequestType.DISTINCTION_REMOVE:
        if target_character_distinction is None:
            msg = "DISTINCTION_REMOVE requires target_character_distinction."
            raise SheetUpdateRequestError(msg)
        xp_cost = compute_sheet_update_xp_cost(
            request_type,
            target_character_distinction.distinction,
            target_character_distinction.rank,
        )
    else:
        msg = f"Unknown request type: {request_type}"
        raise SheetUpdateRequestError(msg)

    return SheetUpdateRequest.objects.create(
        character_sheet=character_sheet,
        request_type=request_type,
        target_distinction=(
            target_distinction if request_type == SheetUpdateRequestType.DISTINCTION_ADD else None
        ),
        target_character_distinction=(
            target_character_distinction
            if request_type == SheetUpdateRequestType.DISTINCTION_REMOVE
            else None
        ),
        justification=justification,
        status=SheetUpdateRequestStatus.PENDING,
        xp_cost=xp_cost,
        origin=origin,
        submitted_by=submitted_by,
    )


def approve_sheet_update_request(
    request: SheetUpdateRequest,
    gm_account: object,
) -> None:
    """Approve a PENDING SheetUpdateRequest: XP debit + change firing.

    Atomic. Preserves advancement gate + account resolution guards.
    Fails loud if insufficient XP — request stays PENDING.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.distinctions.exceptions import SheetUpdateRequestError  # noqa: PLC0415
    from world.distinctions.models import SheetUpdateRequest  # noqa: PLC0415
    from world.distinctions.types import (  # noqa: PLC0415
        SheetUpdateRequestStatus,
        SheetUpdateRequestType,
    )
    from world.magic.services.alterations import enforce_advancement_gate  # noqa: PLC0415
    from world.progression.models.rewards import XPTransaction  # noqa: PLC0415
    from world.progression.services.awards import get_or_create_xp_tracker  # noqa: PLC0415
    from world.progression.types import ProgressionReason  # noqa: PLC0415

    character_sheet = request.character_sheet

    enforce_advancement_gate(character_sheet)

    account = character_sheet.character.account
    if account is None:
        msg = "This character has no linked account."
        raise SheetUpdateRequestError(msg)

    xp_tracker = get_or_create_xp_tracker(account)

    with transaction.atomic():
        locked_req = SheetUpdateRequest.objects.select_for_update().filter(pk=request.pk).first()
        if locked_req is None or locked_req.status != SheetUpdateRequestStatus.PENDING:
            msg = "This sheet update request has already been processed."
            raise SheetUpdateRequestError(msg)

        if locked_req.xp_cost > 0:
            if not xp_tracker.can_spend(locked_req.xp_cost):
                msg = f"Need {locked_req.xp_cost} XP, have {xp_tracker.current_available}."
                raise SheetUpdateRequestError(msg)
            xp_tracker.spend_xp(locked_req.xp_cost)

            XPTransaction.objects.create(
                account=account,
                amount=-locked_req.xp_cost,
                reason=ProgressionReason.XP_PURCHASE,
                description=f"Distinction change: {locked_req.get_request_type_display()}",
                character=character_sheet.character,
                gm=gm_account,
            )

        # Mark APPROVED before firing the change — remove_distinction checks
        # that the request is APPROVED before deleting the CharacterDistinction.
        locked_req.status = SheetUpdateRequestStatus.APPROVED
        locked_req.reviewed_by = gm_account
        locked_req.reviewed_at = timezone.now()
        locked_req.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        if locked_req.request_type == SheetUpdateRequestType.DISTINCTION_ADD:
            grant_distinction(
                character_sheet,
                locked_req.target_distinction,
                origin=locked_req.origin,
                source_description=locked_req.justification,
            )
        else:
            remove_distinction(
                locked_req.target_character_distinction,
                sheet_update_request=locked_req,
            )
            locked_req.refresh_from_db()


def deny_sheet_update_request(
    request: SheetUpdateRequest,
    gm_account: object,
) -> None:
    """Deny a PENDING SheetUpdateRequest. No XP debit, no change."""
    from django.utils import timezone  # noqa: PLC0415

    from world.distinctions.exceptions import SheetUpdateRequestError  # noqa: PLC0415
    from world.distinctions.types import SheetUpdateRequestStatus  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if request.status != SheetUpdateRequestStatus.PENDING:
        msg = "This sheet update request has already been processed."
        raise SheetUpdateRequestError(msg)

    request.status = SheetUpdateRequestStatus.DENIED
    request.reviewed_by = gm_account
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at"])

    send_narrative_message(
        recipients=[request.character_sheet],
        body=f"Your sheet update request was denied: {request.get_request_type_display()}.",
        category=NarrativeCategory.ABILITY,
        sender_account=gm_account,
    )


def cancel_sheet_update_request(
    request: SheetUpdateRequest,
    account: object,
) -> None:
    """Player-initiated cancellation of their own pending request.

    Hard-deletes the row — a PENDING request has had no mechanical effect.
    """
    from world.distinctions.exceptions import SheetUpdateRequestError  # noqa: PLC0415
    from world.distinctions.types import SheetUpdateRequestStatus  # noqa: PLC0415

    if request.status != SheetUpdateRequestStatus.PENDING:
        msg = "Cannot cancel a request that has already been processed."
        raise SheetUpdateRequestError(msg)

    char_account = request.character_sheet.character.account
    if char_account is None or char_account.pk != account.pk:
        msg = "You can only cancel your own requests."
        raise SheetUpdateRequestError(msg)

    request.delete()
