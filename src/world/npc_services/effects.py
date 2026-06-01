"""Per-kind effect handler registry for `NPCServiceOffer`.

When a player completes an interaction by selecting an offer's final action,
the offer's `kind` selects a handler from this registry. The handler is
responsible for producing the downstream object — issuing the permit item,
instantiating the mission, creating the loan obligation, etc.

Plan 2 ships only the `PERMIT` handler stub. Plan 3 (#668) fills in the real
`BuildingPermit` `ItemInstance` + `BuildingPermitDetails` row creation.
Future kinds (`MISSION`, `LOAN`, `TRAINING`, ...) register their own
handlers as they land. Mission migration onto this registry is tracked in
#686.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.npc_services.constants import OfferKind

if TYPE_CHECKING:
    from world.npc_services.models import NPCServiceOffer
    from world.scenes.models import Persona


@dataclass(frozen=True)
class EffectResult:
    """Structured result returned by an offer effect handler.

    Carries enough information for the interaction state machine to render
    a closing message to the player and (optionally) for the caller to
    reach the downstream object. ``kind`` echoes the offer kind so
    consumers don't have to redispatch; ``object_pk`` and ``object_label``
    identify the produced object when one is created (None when the
    effect is a one-shot side effect with no persistent object).
    """

    kind: str  # OfferKind value
    object_pk: int | None = None
    object_label: str = ""
    message: str = ""
    payload: dict = field(default_factory=dict)


# Effect handler signature:
#   handler(offer: NPCServiceOffer, persona: Persona) -> EffectResult
#
# The interaction state machine resolves the persona (PC's presented persona
# at the moment of grant) and passes both the offer row and the persona to
# the handler. Handlers are pure-Python service functions — no implicit
# globals; the offer + persona are everything the handler needs to produce
# its downstream object.
EffectHandler = Callable[["NPCServiceOffer", "Persona"], EffectResult]


def _stub_issue_permit(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """Plan 2 placeholder for permit issuance.

    Returns a structured result so the interaction state machine + tests
    can exercise the dispatch end-to-end without depending on Plan 3's
    `BuildingPermit` ItemTemplate + `BuildingPermitDetails` model. Plan 3
    (#668) replaces this body with real `ItemInstance` + details-row
    creation keyed on ``persona`` (the IC holder).
    """
    message = f"Permit '{offer.label}' would be issued to {persona} (Plan 3 wires real creation)."
    return EffectResult(
        kind=OfferKind.PERMIT,
        object_pk=None,
        object_label=offer.label,
        message=message,
        payload={"holder_persona_pk": persona.pk, "offer_pk": offer.pk},
    )


OFFER_EFFECT_HANDLERS: dict[str, EffectHandler] = {
    OfferKind.PERMIT.value: _stub_issue_permit,
}


class UnregisteredOfferKindError(LookupError):
    """Raised when an offer is granted but its kind has no registered handler.

    Authoring error: every value in ``OfferKind`` should have a handler
    registered before any offer of that kind is saved. We fail loudly
    rather than silently no-op the grant.
    """

    def __init__(self, kind: str) -> None:
        super().__init__(f"No effect handler registered for OfferKind={kind!r}")
        self.kind = kind


def dispatch_offer_effect(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """Look up the registered handler for ``offer.kind`` and invoke it.

    Raises ``UnregisteredOfferKindError`` if the kind has no handler —
    authoring should ensure every OfferKind value is wired before any
    offer of that kind ships.
    """
    handler = OFFER_EFFECT_HANDLERS.get(offer.kind)
    if handler is None:
        raise UnregisteredOfferKindError(offer.kind)
    return handler(offer, persona)
