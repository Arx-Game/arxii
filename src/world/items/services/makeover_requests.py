"""The makeover ask: offer, answer, lapse (#4187).

A cosmetic item used on another player's character whose makeover consent resolves to
``ConsentOutcome.ASK`` becomes a ``MakeoverConsentRequest`` instead of a restyle:
``offer_makeover`` writes the row and tells the target; ``respond_to_makeover_request``
answers it. A grant runs the ordinary ``UseItemAction`` for the stylist with the
accepted row as its proof of consent, so reach, charges, style knowledge and the
technique-grant preflight are all re-checked at grant time and the messages are the
usual ones; a decline spends nothing.

There is no timer. An ask lapses lazily: whenever the target's asks are listed or one is
answered, an ask whose stylist is no longer in the target's room is marked expired
(``expire_if_lapsed``), so a stale card never shows. The web viewset, the telnet offer
handler and ``UseItemAction`` all go through here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from actions.types import ActionResult
from world.items.constants import MAKEOVER_CONSENT_CATEGORY_KEY, MakeoverRemember
from world.items.exceptions import (
    ItemError,
    MakeoverAlreadyAsked,
    MakeoverRequestLapsed,
    MakeoverRequestResolved,
)
from world.items.makeover_models import MakeoverConsentRequest
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.constants import PersonaType
from world.scenes.services import active_persona_for_sheet

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.scenes.models import Persona


def _persona_for(character: ObjectDB) -> Persona:
    return active_persona_for_sheet(character.character_sheet)


def _character_of(persona: Persona) -> ObjectDB:
    return persona.character_sheet.character


def _style_phrase(request: MakeoverConsentRequest) -> str:
    """ "hair (crimson)" for a chosen style, "" for a fixed-option item."""
    option = request.option
    if option is None:
        return ""
    return f"{option.trait.display_name} ({option.display_name})"


# PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #4187).
def describe_offer(request: MakeoverConsentRequest) -> str:
    """What the target reads: who offers what, with which kit."""
    style = _style_phrase(request)
    item = request.item_instance.display_name
    stylist = request.stylist_persona.name
    if style:
        return f"{stylist} offers to restyle your {style} with {item}."
    return f"{stylist} offers to restyle you with {item}."


# PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #4187).
def offer_line(request: MakeoverConsentRequest) -> str:
    """What the stylist reads once the ask is recorded."""
    style = _style_phrase(request)
    item = request.item_instance.display_name
    target = request.target_persona.name
    if style:
        return f"You offer to restyle {target}'s {style} with {item}."
    return f"You offer to restyle {target} with {item}."


def _pending_between(stylist: Persona, target: Persona) -> MakeoverConsentRequest | None:
    return MakeoverConsentRequest.objects.filter(
        stylist_persona=stylist, target_persona=target, status=ActionRequestStatus.PENDING
    ).first()


def _resolve(request: MakeoverConsentRequest, status: str) -> None:
    request.status = status
    request.responded_at = timezone.now()
    request.save(update_fields=["status", "responded_at"])


def expire_if_lapsed(request: MakeoverConsentRequest) -> bool:
    """Mark a pending ask expired when its stylist is no longer in the target's room.

    Returns True when this call expired it. Judged on the two characters' current
    rooms, nothing else: a stylist who stepped out and came back is still here.
    """
    if request.status != ActionRequestStatus.PENDING:
        return False
    stylist = _character_of(request.stylist_persona)
    target = _character_of(request.target_persona)
    if stylist.location is None or stylist.location != target.location:
        _resolve(request, ActionRequestStatus.EXPIRED)
        return True
    return False


@transaction.atomic
def offer_makeover(  # noqa: PLR0913 - the stylist's choices, one keyword each, as use_item takes them
    *,
    user: ObjectDB,
    target: ObjectDB,
    item_instance: ItemInstance,
    option_id: int | None,
    blend: bool,
    descriptor: str | None,
) -> MakeoverConsentRequest:
    """Record the stylist's offer and tell the target. Spends nothing.

    One open ask per stylist/target pair: a second offer while one is pending (and
    not lapsed) is ``MakeoverAlreadyAsked``.
    """
    stylist = _persona_for(user)
    target_persona = _persona_for(target)
    pending = _pending_between(stylist, target_persona)
    if pending is not None and not expire_if_lapsed(pending):
        raise MakeoverAlreadyAsked
    request = MakeoverConsentRequest.objects.create(
        stylist_persona=stylist,
        target_persona=target_persona,
        item_instance=item_instance,
        option_id=option_id,
        blend=blend,
        descriptor=descriptor or "",
    )
    target.msg(f"{describe_offer(request)} (accept makeover / decline makeover)")
    return request


def pending_makeover_requests_for(sheet: CharacterSheet) -> list[MakeoverConsentRequest]:
    """The live asks addressed to this character, newest first; lapsed ones are expired."""
    rows = MakeoverConsentRequest.objects.filter(
        target_persona__character_sheet=sheet, status=ActionRequestStatus.PENDING
    ).select_related(
        "stylist_persona__character_sheet",
        "target_persona__character_sheet",
        "item_instance",
        "option__trait",
    )
    return [row for row in rows if not expire_if_lapsed(row)]


def _remember(
    request: MakeoverConsentRequest, target: ObjectDB, stylist: ObjectDB, *, remember: str
) -> None:
    """Write the one-motion shortcut: ALWAYS whitelists the stylist, NEVER blacklists.

    The consent lists are keyed by the stylist's real tenure and the Privacy page shows
    that tenure under the real character's name. A stylist asking under a mask was seen
    only as the mask, so writing the row would hand the target the identity behind it;
    for a non-PRIMARY stylist persona the shortcut writes nothing. It stays silent on
    purpose: any signal here would itself say "that face is a mask".
    """
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import (  # noqa: PLC0415
        add_social_consent_blacklist,
        add_social_consent_whitelist,
    )
    from world.items.services.usage import _active_tenure_for_sheet  # noqa: PLC0415

    if request.stylist_persona.persona_type != PersonaType.PRIMARY:
        return
    category = SocialConsentCategory.objects.filter(key=MAKEOVER_CONSENT_CATEGORY_KEY).first()
    owner_tenure = _active_tenure_for_sheet(target.character_sheet)
    stylist_sheet = stylist.character_sheet
    stylist_tenure = _active_tenure_for_sheet(stylist_sheet) if stylist_sheet else None
    if category is None or owner_tenure is None or stylist_tenure is None:
        return
    if remember == MakeoverRemember.ALWAYS:
        add_social_consent_whitelist(owner_tenure, stylist_tenure, category)
    else:
        add_social_consent_blacklist(owner_tenure, stylist_tenure, category)


def respond_to_makeover_request(
    request: MakeoverConsentRequest,
    *,
    accept: bool,
    remember: str | None = None,
) -> ActionResult | None:
    """Answer a pending ask.

    Decline: the row is denied, the stylist is told, nothing is spent. Grant: the row
    is accepted and the stylist's ``UseItemAction`` runs with it as proof of consent;
    if that use fails (stylist gone, kit gone or spent, reach lost) the row is expired
    instead and ``MakeoverRequestLapsed`` is raised. ``remember`` writes the target's
    whitelist (``MakeoverRemember.ALWAYS``) or blacklist (``NEVER``) in the same motion.

    Deliberately not atomic: the lapse must stay recorded when it raises, and the use
    itself (``use_item``) already runs in its own transaction.
    """
    if request.status != ActionRequestStatus.PENDING:
        raise MakeoverRequestResolved
    stylist = _character_of(request.stylist_persona)
    target = _character_of(request.target_persona)
    if expire_if_lapsed(request):
        raise MakeoverRequestLapsed
    if remember is not None:
        _remember(request, target, stylist, remember=remember)
    if not accept:
        _resolve(request, ActionRequestStatus.DENIED)
        # PLACEHOLDER (agent-drafted player-facing copy — Apostate to rewrite, #4187)
        stylist.msg(f"{request.target_persona.name} declined.")
        return None

    from actions.definitions.items import UseItemAction  # noqa: PLC0415

    # Accepted before the use runs: ``use_item`` reads the row's status as the proof.
    _resolve(request, ActionRequestStatus.ACCEPTED)
    try:
        result = UseItemAction().execute(
            stylist,
            target=target,
            item=request.item_instance.game_object,
            option_id=request.option_id,
            descriptor=request.descriptor or None,
            blend=request.blend,
            makeover_consent=request,
        )
    except ItemError:
        result = ActionResult(success=False, message="")
    if not result.success:
        _resolve(request, ActionRequestStatus.EXPIRED)
        raise MakeoverRequestLapsed
    return result
