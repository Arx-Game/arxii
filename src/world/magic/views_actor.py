"""Shared actor-resolution mixin for magic-app puppet-gated viewsets.

Extracted from ``SanctumViewSet`` (#1497) so any web viewset that dispatches
through ``action.run()`` on behalf of the requesting user's active puppet can
reuse the same resolution logic (#1728).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist


class PuppetActorMixin:
    """Resolve the caller's selected character, verifying sheet ownership."""

    def _resolve_actor(self, request):
        """Return the caller's selected character if they own its sheet.

        Mirrors ``world.relationships.views.RelationshipUpdateViewSet._resolve_actor``.
        Returns the ObjectDB character (puppet) or ``None`` when resolution
        fails — caller should respond with HTTP 400.
        """
        from world.roster.services.selection import character_for_request  # noqa: PLC0415

        actor = character_for_request(request, entry_id=None)
        if actor is None:
            return None
        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None
        if sheet.character.db_account_id != request.user.pk:
            return None
        return actor
