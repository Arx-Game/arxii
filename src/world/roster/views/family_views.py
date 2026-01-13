"""
Family tree API views.

ViewSets for managing family trees and members.
"""

from http import HTTPMethod

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.roster.models import Family
from world.roster.models.families import FamilyMember
from world.roster.serializers import (
    FamilyMemberSerializer,
    FamilySerializer,
    FamilyTreeSerializer,
)


class FamilyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing families.

    Filter by area_id to get families available for a starting area's realm.
    Filter by has_open_positions=true to show families with placeholder members.
    """

    queryset = Family.objects.filter(is_playable=True)
    serializer_class = FamilySerializer
    permission_classes = [IsAuthenticated]
    # Custom filtering in get_queryset instead of using DjangoFilterBackend

    def get_queryset(self):
        """Return families with optional filtering for open positions."""
        queryset = super().get_queryset()

        # Filter by has_open_positions
        has_open = self.request.query_params.get("has_open_positions")
        if has_open and has_open.lower() == "true":
            queryset = queryset.filter(
                tree_members__member_type=FamilyMember.MemberType.PLACEHOLDER
            ).distinct()

        # Apply ordering in viewset (not model) per project guidelines
        return queryset.order_by("family_type", "name")

    @action(detail=True, methods=[HTTPMethod.GET])
    def tree(self, request, pk=None):
        """
        Get complete family tree with members.

        Returns:
            Family data with members included. Relationships are derived
            from mother/father FKs on FamilyMember.
        """
        family = self.get_object()
        serializer = FamilyTreeSerializer(family, context={"request": request})
        return Response(serializer.data)


class FamilyMemberViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing family members.

    Allows creating placeholders, NPCs, and linking characters to family positions.
    Relationships are derived from mother/father FKs, not stored separately.
    """

    queryset = FamilyMember.objects.all()
    serializer_class = FamilyMemberSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["family", "member_type"]

    def get_queryset(self):
        """Return family members with related data."""
        return (
            super()
            .get_queryset()
            .select_related("family", "character", "mother", "father", "created_by")
            .order_by("family__name", "name")
        )

    def perform_create(self, serializer):
        """Set created_by to current user."""
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """Only allow updates by staff or creator."""
        instance = self.get_object()
        if not (self.request.user.is_staff or self.request.user == instance.created_by):
            msg = "You can only edit family members you created."
            raise PermissionDenied(msg)
        serializer.save()

    def perform_destroy(self, instance):
        """Only allow deletion by staff or creator."""
        if not (self.request.user.is_staff or self.request.user == instance.created_by):
            msg = "You can only delete family members you created."
            raise PermissionDenied(msg)
        instance.delete()
