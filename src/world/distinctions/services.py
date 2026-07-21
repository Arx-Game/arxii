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

from world.distinctions.exceptions import DistinctionExclusionError, DistinctionRevokeError
from world.distinctions.types import DISTINCTION_CHANGE_XP_PER_CG_POINT
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.distinctions.models import CharacterDistinction, Distinction
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


def change_supported(distinction: Distinction) -> bool:
    """True iff this distinction may be added/removed via a GM table request (#2607).

    Two guards (both must pass): (1) the hard technical guard — it carries none
    of the irreversible grant types (resonance/asset/codex), which have no clean
    unwind (resonance ``lifetime_earned`` is monotonic); (2) the soft denylist —
    it is not flagged ``post_cg_immutable``. The first is derived from grant
    config (no authoring); the second is a reactively-curated opt-out.
    """
    if distinction.post_cg_immutable:
        return False
    return not (
        distinction.resonance_grants.exists()
        or distinction.asset_grants.exists()
        or distinction.codex_grants.exists()
    )


def distinction_change_xp_cost(distinction: Distinction, *, rank: int, removing: bool) -> int:
    """XP charged for a table distinction change (#2607).

    Charged only on the benefit direction — gaining a positive distinction or
    removing a negative one — and free otherwise. ``3 × |cost_per_rank × rank|``.
    This asymmetry kills the points-pump: a distinction taken at CG for a point
    refund costs real XP to shed later.
    """
    cost_per_rank = distinction.cost_per_rank
    benefits = (cost_per_rank < 0 and removing) or (cost_per_rank > 0 and not removing)
    if not benefits:
        return 0
    return DISTINCTION_CHANGE_XP_PER_CG_POINT * abs(cost_per_rank * rank)


@transaction.atomic
def revoke_distinction(character_distinction: CharacterDistinction) -> None:
    """Remove a held distinction and reverse everything the grant built (#2607).

    The removal counterpart to ``grant_distinction`` — promoted from the ad-hoc
    ``.filter(...).delete()`` pattern to a real seam (see this app's CLAUDE.md).
    Valid only for ``change_supported`` distinctions (no resonance/asset/codex
    grants — those have no clean unwind: resonance ``lifetime_earned`` is
    monotonic). Refuses defensively if one reaches here; ``change_supported``
    gates upstream at request submit.

    Order matters: clear any relocated Secret first (else deleting the row
    orphans the ``secrets.Secret``), then delete the modifier sources (cascades
    to ``CharacterModifier``), then the row. ``ActionEnhancement`` gating is
    derived-on-read from the template, so deleting the row removes access
    automatically — nothing to unwind there.
    """
    from world.mechanics.services import delete_distinction_modifiers  # noqa: PLC0415

    distinction = character_distinction.distinction
    if not change_supported(distinction):
        msg = (
            f"{distinction.name} cannot be removed automatically — it carries "
            "resonance/asset/codex grants or is denylisted."
        )
        raise DistinctionRevokeError(msg)

    clear_distinction_secret(character_distinction)
    delete_distinction_modifiers(character_distinction)
    character_distinction.delete()
