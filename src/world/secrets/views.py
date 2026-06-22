"""Secret-tab API (#1334) — the viewer's known secrets about a character.

Read-only: returns the ``SecretKnowledge`` the viewer's account holds (newest first), filterable
by ``subject`` (a CharacterSheet pk) for one person's tab. Scoped to the account's roster entries
— an OOC "what you've learned about this person" view; knowledge itself stays roster-scoped.
Locked partial-knowledge layers render as "Unknown" in the serializer.
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
        # Subquery (not a list) so the __in stays a single indexed query; the names come from the
        # prefetched character so the serializer never queries per row.
        own_entries = RosterEntry.objects.for_account(self.request.user)
        return (
            SecretKnowledge.objects.filter(roster_entry__in=own_entries)
            .select_related(
                "secret",
                "secret__category",
                "secret__author_persona",
                "secret__subject_sheet__character",
                "secret__second_party_sheet__character",
            )
            .order_by("-found_at")
        )
