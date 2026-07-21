"""Kind -> completion-handler registry for TableUpdateRequest (#2607).

Mirrors ``world.npc_services.effects``: a handler runs when a member COMPLETES an
approved request. Kinds register their handler from their owning app's
``AppConfig.ready()`` (the distinction kinds from ``DistinctionsConfig``), so the
``gm`` app never imports the consumer apps.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.gm.models import TableUpdateRequest

RequestHandler = Callable[["TableUpdateRequest"], None]

REQUEST_HANDLERS: dict[str, RequestHandler] = {}


class UnregisteredRequestKindError(LookupError):
    """No completion handler is registered for a request's kind."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"No completion handler registered for table-request kind {kind!r}.")
        self.kind = kind


def register_request_handler(kind: str, handler: RequestHandler) -> None:
    """Register the completion handler for a request kind (call from AppConfig.ready)."""
    REQUEST_HANDLERS[kind] = handler


def run_request_completion(request: TableUpdateRequest) -> None:
    """Dispatch a request to its kind's completion handler."""
    handler = REQUEST_HANDLERS.get(request.kind)
    if handler is None:
        raise UnregisteredRequestKindError(request.kind)
    handler(request)
