# src/world/distinctions/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from django.db import models

if TYPE_CHECKING:
    from world.character_creation.models import DistinctionOffer
    from world.distinctions.models import Distinction


@dataclass
class ValidatedDistinction:
    """Validated distinction data for adding to a draft.

    ``offer`` is the ``DistinctionOffer`` row the pick was validated against
    (#3675), every CG add goes through an offer now, so it is required.
    """

    distinction: Distinction
    rank: int
    notes: str
    offer: DistinctionOffer


class DraftDistinctionEntry(TypedDict):
    """Type for a distinction entry stored in draft_data.

    ``offer_ids`` mixes ``int`` (a real ``DistinctionOffer`` row) and ``str``
    (a tradition-state-carried drawback has no offer row, so its source key is
    the synthetic string ``"state:<TraditionState value>"`` built by
    ``world.character_creation.offers.reconcile_offer_picks`` (#3675).
    """

    distinction_id: int
    distinction_name: str
    distinction_slug: str
    category_slug: str
    rank: int
    cost: int
    notes: str
    # Offer provenance (#3675): one entry per distinction, every contributing offer.
    offer_ids: list[int | str]
    sources: list[str]
    arrivals: list[str]
    # The feature this entry is aimed at (#3739), for a ``taken_per_feature``
    # distinction only: ``feature_trait`` is a ``FormTrait.name`` and
    # ``feature_marking`` a ``DraftMarking`` pk, and at most one is ever set.
    # A distinction held per feature appears once per feature, so the entry list
    # is keyed by ``feature_key`` rather than by ``distinction_id`` alone.
    feature_trait: str
    feature_marking: int


#: The key that identifies one draft entry. Everything that used to key the
#: entry list by ``distinction_id`` keys it by this instead (#3739): "Alluring"
#: on a scar and "Alluring" on your eyes are two entries of one distinction,
#: and both are paid for.
type FeatureKey = tuple[int, str, int]


def feature_key(entry: DraftDistinctionEntry) -> FeatureKey:
    """The identity of one draft entry: its distinction plus the feature it names.

    Called anywhere the entry list is indexed (``offers.offers_for``,
    ``reconcile_offer_picks``, the sync view's merge, ``_create_distinctions``).
    A distinction that is not ``taken_per_feature`` carries no feature, so its
    key degenerates to ``(distinction_id, "", 0)`` and behaves exactly as the
    pre-#3739 ``distinction_id`` key did.
    """
    trait, marking = feature_of(entry)
    return (entry["distinction_id"], trait, marking)


def feature_of(entry: DraftDistinctionEntry) -> tuple[str, int]:
    """Just the feature half of ``feature_key``: ``("", 0)`` when there is none.

    Kept separate because most callers compare features, not whole keys: "is this
    entry on the feature I am rendering", "which features has the draft opened".
    """
    return (entry.get("feature_trait") or "", entry.get("feature_marking") or 0)


def build_distinction_entry(  # noqa: PLR0913 - one builder for every draft entry shape
    distinction: Distinction,
    rank: int = 1,
    notes: str = "",
    *,
    offer: DistinctionOffer | None = None,
    source: str = "",
    feature_trait: str = "",
    feature_marking: int = 0,
) -> DraftDistinctionEntry:
    """Build the dictionary entry for a distinction on a draft.

    Called by the distinctions viewset for a plain player pick (no ``offer``)
    and by ``world.character_creation.offers`` when a ``DistinctionOffer`` is
    the source (#3675): the cost is ``0`` when the offer arrives ``bundled`` or
    ``carried``, since that pick isn't paid for out of CG points.

    ``feature_trait``/``feature_marking`` (#3739) name the one feature a
    ``taken_per_feature`` distinction is aimed at; the sync view resolves them
    and passes at most one. Everything else leaves both at their empty defaults.

    ``offer_ids``/``sources``/``arrivals`` are kept in lockstep by ``offer``
    alone (never by whether ``source`` happens to be a non-empty string): an
    APPEARANCE/ACTORS_SHEET CHOICE offer has no opener, so ``source`` is
    routinely ``""``, and a length mismatch between the three lists would blow
    up the ``zip(..., strict=True)`` in ``offers._drop_vanished_sources``.
    """
    has_offer = offer is not None
    arrival = offer.arrives_as if has_offer else ""
    free = arrival in ("bundled", "carried")
    return DraftDistinctionEntry(
        distinction_id=distinction.id,
        distinction_name=distinction.name,
        distinction_slug=distinction.slug,
        category_slug=distinction.category.slug,
        rank=rank,
        cost=0 if free else distinction.calculate_total_cost(rank),
        notes=notes,
        offer_ids=[offer.id] if has_offer else [],
        sources=[source] if has_offer else [],
        arrivals=[arrival] if has_offer else [],
        feature_trait=feature_trait,
        feature_marking=feature_marking,
    )


class DistinctionOrigin(models.TextChoices):
    """How a character acquired a distinction.

    ``GAMEPLAY`` was vestigial from #2037 through #2441 — kept for schema
    stability, no production writer assigned it. #2441 Task 8 became its first
    production writer: ``world.magic.services.tradition_membership.
    leave_tradition`` stamps it when re-applying the Unbound drawback, an
    automatic system consequence of the player's own leave-tradition action that
    doesn't fit any of the other four sources (no GM, achievement, consequence
    pool, or endorsement threshold involved). Every in-play grant goes through
    ``world.distinctions.services.grant_distinction`` and stamps one of these
    six values.

    ``SPECIES`` (#2472) is a finalize-time origin alongside ``CHARACTER_CREATION``:
    it marks a distinction forced onto the sheet by the character's species
    (e.g. a minor gift auto-granted to fill an empty gift slot) rather than one
    the player spent points on during the draft.
    """

    CHARACTER_CREATION = "character_creation", "Character Creation"
    GAMEPLAY = "gameplay", "Gameplay"
    GM_AWARD = "gm_award", "GM Award"
    ACHIEVEMENT_AUTO_GRANT = "achievement_auto_grant", "Achievement"
    CONSEQUENCE_POOL = "consequence_pool", "Consequence"
    ENDORSEMENT_THRESHOLD = "endorsement_threshold", "Endorsement Threshold"
    SPECIES = "species", "Species"
    UNLOCK_PURCHASE = "unlock_purchase", "Unlock Purchase"


class OtherStatus(models.TextChoices):
    """Status of a freeform 'Other' distinction entry."""

    PENDING_REVIEW = "pending_review", "Pending Review"
    APPROVED = "approved", "Approved"
    MAPPED = "mapped", "Mapped to Distinction"


class SheetUpdateRequestType(models.TextChoices):
    """Which kind of sheet-update this request represents.

    Only DISTINCTION_ADD / DISTINCTION_REMOVE are wired in #2628;
    future kinds (BACKGROUND_EDIT, etc.) will extend this enum.
    """

    DISTINCTION_ADD = "distinction_add", "Add Distinction"
    DISTINCTION_REMOVE = "distinction_remove", "Remove Distinction"


class SheetUpdateRequestStatus(models.TextChoices):
    """Lifecycle state of a SheetUpdateRequest."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"


# Backwards-compat alias — old imports still work during migration.
DistinctionChangeAction = SheetUpdateRequestType
