"""
URL configuration for codex API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.codex.views import (
    CodexCategoryViewSet,
    CodexEntryViewSet,
    CodexSubjectViewSet,
)

app_name = "codex"

router = DefaultRouter()
router.register(r"categories", CodexCategoryViewSet, basename="category")
router.register(r"subjects", CodexSubjectViewSet, basename="subject")
router.register(r"entries", CodexEntryViewSet, basename="entry")

urlpatterns = [
    path("", include(router.urls)),
]
