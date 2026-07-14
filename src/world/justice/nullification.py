"""Nullification (#1825) — the counter-investigation's payoff against a false accusation.

Fired by the RESEARCH project's completion handler when the researched clue targets an
ACCUSATION secret. The accusation Secret stays (the claim was really made; falsity stays
emergent — resolved fork #1); nullification compensates its damage and makes the
falseness a new discoverable fact about the FRAMER. All magnitudes PLACEHOLDER.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.justice.models import AccusationCrimeClaim, AccusationNullification

if TYPE_CHECKING:
    from world.secrets.models import Secret

# PLACEHOLDER magnitudes: the author-unmask trail is deliberately harder than the
# original disprove trail — base + per-level scale both above the smear seeds.
UNMASK_CLUE_BASE_DIFFICULTY = 15
UNMASK_CLUE_DIFFICULTY_PER_LEVEL = 10

# Authored-by-agent prose — PLACEHOLDER for Apostate's rewrite.
_AUTHORSHIP_CONTENT = (
    "PLACEHOLDER The scandal was manufactured — stitched together and fed to the "
    "rumor mill by {framer}."
)


def nullify_accusation(secret: Secret) -> AccusationNullification:
    """Prove an accusation fabricated: compensate, quiet, retract, and expose the trail.

    Idempotent (one nullification per accusation). Steps:

    1. **Reputation** — full compensating reversal of the exposure's damage.
    2. **Gossip** — every regional heat row zeroed (the rumor is dead).
    3. **Claim** — the criminal claim is retracted; no further heat accrues
       (already-minted heat decays out on its own — the mud takes time to dry).
    4. **The falseness becomes a fact** — when the accusation has an author, mint an
       ACTION_ANCHORED authorship secret *about the framer* (granted to NO ONE) and
       plant its own, harder counter-clue in the hubs where the rumor circulated —
       the author-unmask trail that arms the consent-gated denounce/backfire.
    """
    from world.secrets.models import SecretGossip  # noqa: PLC0415
    from world.secrets.services import reverse_secret_exposure  # noqa: PLC0415

    existing = AccusationNullification.objects.filter(secret=secret).first()
    if existing is not None:
        return existing

    reverse_secret_exposure(secret)

    gossip_rows = list(SecretGossip.objects.filter(secret=secret))
    for row in gossip_rows:
        if row.heat:
            row.heat = 0
            row.save(update_fields=["heat", "updated_date"])

    claim = AccusationCrimeClaim.objects.filter(secret=secret).first()
    if claim is not None and claim.retracted_at is None:
        claim.retracted_at = timezone.now()
        claim.save(update_fields=["retracted_at"])

    authorship_secret = _mint_authorship_secret(secret, [row.region for row in gossip_rows])
    return AccusationNullification.objects.create(
        secret=secret, authorship_secret=authorship_secret
    )


def _mint_authorship_secret(secret: Secret, regions: list) -> Secret | None:
    """The falseness made discoverable — a secret about the framer, granted to no one."""
    from world.clues.services import create_accusation_counter_clue  # noqa: PLC0415
    from world.secrets.constants import SecretLevel, SecretProvenance  # noqa: PLC0415
    from world.secrets.services import author_secret  # noqa: PLC0415

    if secret.author_persona is None:
        return None
    framer_sheet = secret.author_persona.character_sheet
    authorship = author_secret(
        subject_sheet=framer_sheet,
        provenance=SecretProvenance.ACTION_ANCHORED,
        level=SecretLevel.WHISPERS,
        content=_AUTHORSHIP_CONTENT.format(framer=secret.author_persona),
    )
    difficulty = UNMASK_CLUE_BASE_DIFFICULTY + secret.level * UNMASK_CLUE_DIFFICULTY_PER_LEVEL
    for region in regions:
        create_accusation_counter_clue(authorship, region=region, difficulty=difficulty)
    return authorship
