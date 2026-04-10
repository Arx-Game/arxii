"""FilterSet for staff inbox query params.

The inbox is not backed by a single model, so we use a regular DRF
serializer for query param validation instead of django-filter.
"""

from __future__ import annotations

from rest_framework import serializers


class StaffInboxFilterSerializer(serializers.Serializer):
    """Validates query params for the staff inbox endpoint."""

    categories = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
