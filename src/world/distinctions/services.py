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

from world.distinctions.exceptions import DistinctionExclusionError
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import (
        CharacterDistinction,
        Distinction,
        DistinctionChangeAuthorization,
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


DISTINCTION_REMOVAL_FRICTION_MULTIPLIER = 1.5


def compute_distinction_change_xp_cost(
    distinction: Distinction,
    rank: int,
    action: str,
) -> int:
    """Compute the XP cost for a distinction change.

    Args:
        distinction: The distinction being added or removed.
        rank: For ADD, the target rank (usually 1). For REMOVE, the
            CharacterDistinction's current rank.
        action: ``DistinctionChangeAction.ADD`` or ``DistinctionChangeAction.REMOVE``.

    Returns:
        The XP cost (always positive).
    """
    from world.distinctions.types import DistinctionChangeAction  # noqa: PLC0415

    base = 2 * abs(distinction.cost_per_rank) * rank
    if action == DistinctionChangeAction.REMOVE and distinction.cost_per_rank < 0:
        return int(base * DISTINCTION_REMOVAL_FRICTION_MULTIPLIER)
    return base


def _check_removal_prerequisites(character_distinction: CharacterDistinction) -> None:
    """Check that no other held distinction depends on the one being removed.

    Stub — DistinctionPrerequisite uses rule_json, no production rows reference
    distinctions as prerequisites yet. TODO: proper rule evaluation.
    """


def remove_distinction(
    character_distinction: CharacterDistinction,
    *,
    authorization: DistinctionChangeAuthorization,
) -> None:
    """Remove a CharacterDistinction, reconciling all dependent systems.

    The inverse of ``grant_distinction``. Requires a valid (non-consumed)
    ``DistinctionChangeAuthorization`` with ``action=REMOVE`` targeting this row.

    Teardown order:
    1. ``delete_distinction_modifiers`` — removes CharacterModifier + ModifierSource rows.
    2. ``clear_distinction_secret`` — deletes the Secret if present (idempotent).
    3. ``CharacterDistinction.delete()`` — CASCADE handles remaining FKs.

    The authorization's ``is_consumed`` / ``consumed_at`` are marked by the
    CALLER (``spend_xp_on_distinction_unlock``), NOT by this function.

    NOT torn down (by design):
    - ``CharacterResonance`` currency (monotonic, no clawback — #2037).
    - ``NPCAsset`` (world entity, nullable FK orphans).
    - CodexEntry grants (knowledge can't be unlearned).
    - ``ActionEnhancement`` (auto-disabled when CharacterDistinction row is gone).

    Args:
        character_distinction: The CharacterDistinction to remove.
        authorization: The DistinctionChangeAuthorization authorizing this removal.

    Raises:
        DistinctionAuthorizationError: If the authorization is already consumed
            or doesn't target this CharacterDistinction.
    """
    from world.distinctions.exceptions import (  # noqa: PLC0415
        DistinctionAuthorizationError,
    )
    from world.distinctions.types import DistinctionChangeAction  # noqa: PLC0415
    from world.mechanics.services import delete_distinction_modifiers  # noqa: PLC0415
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if authorization.is_consumed:
        msg = "This distinction change authorization has already been used."
        raise DistinctionAuthorizationError(msg)
    if (
        authorization.action != DistinctionChangeAction.REMOVE
        or authorization.target_character_distinction_id != character_distinction.pk
    ):
        msg = "This authorization does not target this distinction."
        raise DistinctionAuthorizationError(msg)

    _check_removal_prerequisites(character_distinction)

    with transaction.atomic():
        delete_distinction_modifiers(character_distinction)
        clear_distinction_secret(character_distinction)

        distinction_name = character_distinction.distinction.name
        character_sheet = authorization.character_sheet
        character_distinction.delete()

    send_narrative_message(
        recipients=[character_sheet],
        body=f"You have shed the distinction: {distinction_name}.",
        category=NarrativeCategory.ABILITY,
        sender_account=None,
    )


def spend_xp_on_distinction_unlock(
    character_sheet: CharacterSheet,
    authorization: DistinctionChangeAuthorization,
) -> None:
    """Spend XP to complete a distinction change (add or remove).

    Validates: authorization not consumed, authorization targets this character.
    Locks the authorization row with ``select_for_update`` to prevent
    double-accept. Debits XPTracker, writes XPTransaction, fires
    ``grant_distinction`` (ADD) or ``remove_distinction`` (REMOVE), then marks
    the authorization consumed.

    This service is the SOLE writer of ``is_consumed`` / ``consumed_at``.

    Args:
        character_sheet: The character spending XP.
        authorization: The DistinctionChangeAuthorization to complete.

    Raises:
        DistinctionAuthorizationError: If the authorization is already
            consumed, doesn't target this character, or the character has
            insufficient XP.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.distinctions.exceptions import DistinctionAuthorizationError  # noqa: PLC0415
    from world.distinctions.models import DistinctionChangeAuthorization  # noqa: PLC0415
    from world.distinctions.types import (  # noqa: PLC0415
        DistinctionChangeAction,
        DistinctionOrigin,
    )
    from world.magic.services.alterations import enforce_advancement_gate  # noqa: PLC0415
    from world.progression.models.rewards import XPTransaction  # noqa: PLC0415
    from world.progression.services.awards import get_or_create_xp_tracker  # noqa: PLC0415
    from world.progression.types import ProgressionReason  # noqa: PLC0415

    if authorization.character_sheet_id != character_sheet.pk:
        msg = "This authorization does not target this character."
        raise DistinctionAuthorizationError(msg)

    enforce_advancement_gate(character_sheet)

    account = character_sheet.character.account
    if account is None:
        msg = "This character has no linked account."
        raise DistinctionAuthorizationError(msg)

    xp_tracker = get_or_create_xp_tracker(account)

    with transaction.atomic():
        locked_auth = (
            DistinctionChangeAuthorization.objects.select_for_update()
            .filter(pk=authorization.pk)
            .first()
        )
        if locked_auth is None or locked_auth.is_consumed:
            msg = "This distinction change authorization has already been used."
            raise DistinctionAuthorizationError(msg)

        if not xp_tracker.can_spend(locked_auth.xp_cost):
            msg = f"Need {locked_auth.xp_cost} XP, have {xp_tracker.current_available}."
            raise DistinctionAuthorizationError(msg)

        xp_tracker.spend_xp(locked_auth.xp_cost)

        XPTransaction.objects.create(
            account=account,
            amount=-locked_auth.xp_cost,
            reason=ProgressionReason.XP_PURCHASE,
            description=f"Distinction change: {locked_auth.action}",
            character=character_sheet.character,
            gm=locked_auth.authorized_by,
        )

        if locked_auth.action == DistinctionChangeAction.ADD:
            grant_distinction(
                character_sheet,
                locked_auth.target_distinction,
                origin=DistinctionOrigin.UNLOCK_PURCHASE,
                source_description=locked_auth.reason,
            )
        else:
            remove_distinction(
                locked_auth.target_character_distinction,
                authorization=locked_auth,
            )
            # Refresh from DB — remove_distinction deleted the
            # target_character_distinction, and SET_NULL nulled the FK.
            locked_auth.refresh_from_db()

        locked_auth.is_consumed = True
        locked_auth.consumed_at = timezone.now()
        locked_auth.save(update_fields=["is_consumed", "consumed_at"])
