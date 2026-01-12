"""
Serializers for traits system.
"""

from rest_framework import serializers

from world.traits.models import Trait


class TraitSerializer(serializers.ModelSerializer):
    """Serializer for trait definitions."""

    class Meta:
        model = Trait
        fields = ["id", "name", "trait_type", "category", "description"]
        read_only_fields = fields
