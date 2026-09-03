"""Serializers for scheduled-downtime announcements (#3194)."""

from rest_framework import serializers


class PlannedDowntimeSerializer(serializers.Serializer):
    """Read shape for ``PlannedDowntime`` — public, display-safe fields only.

    Read-only: never saved. DRF's own ``create``/``update`` already raise
    ``NotImplementedError``, so this class does not restate them.
    """

    source = serializers.CharField(read_only=True)
    starts_at = serializers.DateTimeField(read_only=True)
    expected_duration_minutes = serializers.IntegerField(read_only=True)
    message = serializers.CharField(read_only=True)
