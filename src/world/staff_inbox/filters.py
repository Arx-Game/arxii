"""FilterSet for staff inbox query params.

The inbox is not backed by a single model, so we use a regular DRF
serializer for query param validation instead of django-filter.
"""

from __future__ import annotations

from rest_framework import serializers

from world.player_submissions.constants import SubmissionCategory


class StaffInboxFilterSerializer(serializers.Serializer):
    """Validates query params for the staff inbox endpoint."""

    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=SubmissionCategory.choices),
        required=False,
    )
    page = serializers.IntegerField(
        required=False,
        min_value=1,
        default=1,
    )
    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=200,
        default=50,
    )
