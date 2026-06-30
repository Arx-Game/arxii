"""Path-crossing magic grant (#1579, ADR-0055).

Crossing into a more-advanced Path grants its authored Gift(s) plus a curated
starter technique set (the ``PathGiftGrant`` rows for that path). This realizes
the (Gift x Path) -> base-technique-set leg of ADR-0055 as an *acquisition* on
crossing; #1578 built the complementary resonance-specialization leg that later
re-skins each granted technique on read.

The grant is idempotent and reuses the existing acquisition primitives:
``CharacterGift`` / ``CharacterTechnique`` rows + ``provision_latent_gift_thread``
(#1578) for the latent GIFT thread. XP/advancement *gates* the crossing
(ADR-0053); this grant is a consequence of path membership (ADR-0050), not an XP
purchase.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.types.path_magic import PathMagicGrantResult

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.classes.models import Path
    from world.magic.models.affinity import Resonance
    from world.magic.models.gifts import Gift


def _grant_resonance_for(gift: Gift, claimed_ids: set[int]) -> Resonance | None:
    """Resonance for a newly-granted gift's latent thread.

    Prefer a resonance the character has already claimed (``claimed_ids``) that the
    gift supports; otherwise the gift's first supported resonance; ``None`` if the
    gift supports none (then the thread is not provisioned, mirroring CG). The
    player commits their true choice later via the Rite of Weaving.
    """
    supported = gift.cached_resonances
    if not supported:
        return None
    return next((r for r in supported if r.pk in claimed_ids), supported[0])


@transaction.atomic
def grant_path_magic(sheet: CharacterSheet, path: Path) -> PathMagicGrantResult:
    """Grant ``path``'s authored gift(s) + curated starter techniques to ``sheet``.

    Idempotent: gifts/techniques the character already owns are skipped and are
    not listed in the returned result. Safe to call for any path (a path with no
    ``PathGiftGrant`` rows is a no-op).
    """
    from world.magic.models import (  # noqa: PLC0415
        CharacterResonance,
        CharacterTechnique,
        PathGiftGrant,
    )
    from world.magic.specialization.services import (  # noqa: PLC0415
        grant_gift_to_character,
    )

    grants = PathGiftGrant.objects.filter(path=path).select_related("gift")
    # The character's claimed resonances, fetched once (not per granted gift).
    claimed_ids = set(
        CharacterResonance.objects.filter(character_sheet=sheet).values_list(
            "resonance_id", flat=True
        )
    )

    granted_gifts: list = []
    granted_techniques: list = []
    for grant in grants:
        gift = grant.gift
        resonance = _grant_resonance_for(gift, claimed_ids)
        _, gift_created = grant_gift_to_character(sheet, gift, resonance=resonance)
        if gift_created:
            granted_gifts.append(gift)
        for technique in grant.starter_techniques.all():
            _, tech_created = CharacterTechnique.objects.get_or_create(
                character=sheet, technique=technique
            )
            if tech_created:
                granted_techniques.append(technique)

    if granted_gifts or granted_techniques:
        from world.achievements.constants import AccessChangeSource  # noqa: PLC0415
        from world.achievements.discovery import announce_access_change  # noqa: PLC0415

        announce_access_change(
            sheet,
            gained=granted_techniques,
            lost=[],
            source=AccessChangeSource.PATH_ADVANCEMENT,
        )

    return PathMagicGrantResult(
        granted_gifts=granted_gifts,
        granted_techniques=granted_techniques,
    )
