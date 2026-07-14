"""Denounce the framer (#1825) — the consent-gated backfire.

Framing is a bet with equivalent stakes: once the author-unmask trail yields the
authorship secret, anyone the framer's own ``hostile`` consent category admits may
denounce them at a social hub — exposing the authorship secret to the region's
societies (the normal reputation engine) and landing **false-accusation pursuit heat
scaled by the original accusation's level**. This is the ONE counter-play move that is
consent-gated (the Tom/Bob/Fred rule): defending the accused was open to all; naming
and punishing the accuser lives only with people they've opted into antagonism with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.justice.models import AccusationNullification, DenounceRecord

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.secrets.models import Secret

_NOT_A_FRAME_FACT = "That secret names no proven framer to denounce."
_NOT_KNOWN = "You can only denounce with a truth you've actually come into."
_ALREADY_DENOUNCED = "You have already made this denunciation."
_CONSENT_BLOCKED = (
    "They have not opened themselves to being antagonised. "
    "You can clear the accused's name, but not wield the authorship against them."
)
_NOT_HUB = "A denunciation needs an audience — do it at a social hub."


class DenounceError(Exception):
    """A denunciation could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@dataclass(frozen=True)
class DenounceResult:
    """Outcome of a denunciation — always decisive once the gates pass."""

    success: bool
    framer_sheet_id: int


def denounce_framer(
    character: ObjectDB, authorship_secret: Secret, *, room: ObjectDB
) -> DenounceResult:
    """Expose the unmasked framer — reputation via the normal engine, heat by level.

    Gates: the secret is a nullification's authorship fact; the denouncer holds its
    knowledge; a social hub; the framer's ``hostile`` consent admits the denouncer;
    one denunciation per denouncer. No check — the investigation already did the
    proving; this is pulling the trigger.
    """
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import accrue_heat, area_for_room  # noqa: PLC0415
    from world.secrets.gossip import (  # noqa: PLC0415
        GossipError,
        hub_region_for,
        societies_for_region,
    )
    from world.secrets.services import (  # noqa: PLC0415
        accusation_permitted,
        character_knows_secret,
        expose_secret,
    )

    nullification = (
        AccusationNullification.objects.filter(authorship_secret=authorship_secret)
        .select_related("secret")
        .first()
    )
    if nullification is None:
        raise DenounceError(_NOT_A_FRAME_FACT)
    denouncer_sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    if not character_knows_secret(knower_sheet=denouncer_sheet, secret=authorship_secret):
        raise DenounceError(_NOT_KNOWN)
    try:
        region = hub_region_for(room)
    except GossipError as exc:
        raise DenounceError(_NOT_HUB) from exc
    framer_sheet = authorship_secret.subject_sheet
    if not accusation_permitted(framer_sheet=denouncer_sheet, target_sheet=framer_sheet):
        raise DenounceError(_CONSENT_BLOCKED)
    if DenounceRecord.objects.filter(
        authorship_secret=authorship_secret, denouncer_sheet=denouncer_sheet
    ).exists():
        raise DenounceError(_ALREADY_DENOUNCED)

    DenounceRecord.objects.create(
        authorship_secret=authorship_secret, denouncer_sheet=denouncer_sheet
    )
    societies = societies_for_region(region)
    if societies:
        expose_secret(authorship_secret, societies=societies)
    false_accusation = CrimeKind.objects.filter(slug="false-accusation").first()
    framer_persona = framer_sheet.primary_persona
    if false_accusation is not None and framer_persona is not None:
        accrue_heat(
            persona=framer_persona,
            crime_kind=false_accusation,
            area=area_for_room(room),
            deed=None,
            scale=int(nullification.secret.level),
        )
    return DenounceResult(success=True, framer_sheet_id=framer_sheet.pk)
