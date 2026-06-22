"""Secret-tab API (#1334) — the active character's known secrets about a character.

Read-only: returns the ``SecretKnowledge`` the **active viewing character** holds (newest first),
filterable by ``subject`` (a CharacterSheet pk) for one person's tab. IC knowledge is scoped to
the active character the caller passes (``viewer`` = a RosterEntry pk), **never** the account —
``for_account`` confines it to the caller's own characters so the param can't reach another
account's knowledge. Locked partial-knowledge layers render as "Unknown" in the serializer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.roster.models import RosterEntry
from world.secrets.filters import KnownSecretFilter
from world.secrets.models import SecretKnowledge
from world.secrets.serializers import KnownSecretSerializer
from world.secrets.services import known_secrets_for

if TYPE_CHECKING:
    from django.db.models import QuerySet


class SecretsPagination(PageNumberPagination):
    page_size = 50


class KnownSecretViewSet(ReadOnlyModelViewSet):
    """A viewer's known secrets — the data behind the profile secret tab (#1334)."""

    serializer_class = KnownSecretSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SecretsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = KnownSecretFilter

    def get_queryset(self) -> QuerySet[SecretKnowledge]:
        viewer = self._viewer_entry()
        if viewer is None:
            return SecretKnowledge.objects.none()
        # Shared with the telnet +secrets command; the `subject` FilterSet narrows to one tab.
        return known_secrets_for(viewer)

    def _viewer_entry(self) -> RosterEntry | None:
        """The active (viewing) character, validated as owned by the requester (#1334).

        IC knowledge scopes to the active character, never the account: the caller passes which of
        their characters is viewing (``viewer`` = a RosterEntry pk); ``for_account`` confines the
        lookup to their own, so the param can never reach another account's knowledge. No (or an
        unowned) ``viewer`` → no secrets, rather than an account-wide aggregate.
        """
        raw = self.request.query_params.get("viewer")  # noqa: use_filterset — auth scope, not a filter
        if not raw or not raw.isdigit():
            return None
        return RosterEntry.objects.for_account(self.request.user).filter(pk=int(raw)).first()
