"""
URL configuration for relationships API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.relationships.views import (
    CharacterRelationshipViewSet,
    RelationshipConditionViewSet,
)

app_name = "relationships"

router = DefaultRouter()
router.register(r"conditions", RelationshipConditionViewSet, basename="condition")
router.register(r"relationships", CharacterRelationshipViewSet, basename="relationship")

urlpatterns = [
    path("", include(router.urls)),
]
