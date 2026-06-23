from __future__ import annotations

from typing import Any, Protocol


class OfferHandler(Protocol):
    keyword: str
    label: str

    def pending_for(self, sheet: Any) -> Any | None: ...
    def describe(self, offer: Any) -> str: ...
    def accept(self, offer: Any, caller: Any, args: str) -> str: ...
    def decline(self, offer: Any, caller: Any) -> str: ...


_REGISTRY: list[OfferHandler] = []


def register_offer_handler(handler: OfferHandler) -> None:
    _REGISTRY.append(handler)


def get_all_pending(sheet: Any) -> list[tuple[OfferHandler, Any]]:
    result = []
    for handler in _REGISTRY:
        offer = handler.pending_for(sheet)
        if offer is not None:
            result.append((handler, offer))
    return result


def find_handler(keyword: str) -> OfferHandler | None:
    keyword_lower = keyword.lower()
    for handler in _REGISTRY:
        if handler.keyword.lower() == keyword_lower:
            return handler
    return None


def format_pending_listing(pending: list[tuple[OfferHandler, Any]]) -> str:
    if not pending:
        return "You have no pending offers."
    lines = ["Pending prompts:"]
    lines += [f"  [{h.keyword}] {h.describe(o)}" for h, o in pending]
    return "\n".join(lines)
