"""Serializers for worship surfaces (#2355).

``WorshippedBeingRefSerializer`` is the public reference shape (id, name,
tradition name) — safe anywhere; it never exposes pools or avatar links.
"""

from rest_framework import serializers

from world.worship.models import WorshippedBeing


class WorshippedBeingRefSerializer(serializers.ModelSerializer):
    tradition_name = serializers.CharField(source="tradition.name", read_only=True)

    class Meta:
        model = WorshippedBeing
        fields = ["id", "name", "tradition_name"]
