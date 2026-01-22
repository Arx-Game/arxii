"""
URL configuration for the distinctions API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.distinctions.views import (
    DistinctionCategoryViewSet,
    DistinctionViewSet,
    DraftDistinctionViewSet,
)

app_name = "distinctions"

router = DefaultRouter()
router.register(r"categories", DistinctionCategoryViewSet, basename="distinction-category")
router.register(r"distinctions", DistinctionViewSet, basename="distinction")

urlpatterns = [
    # Router-based URLs
    path("", include(router.urls)),
    # Draft distinction management (nested under drafts)
    path(
        "drafts/<int:draft_id>/distinctions/",
        DraftDistinctionViewSet.as_view({"get": "list", "post": "create"}),
        name="draft-distinctions-list",
    ),
    path(
        "drafts/<int:draft_id>/distinctions/<int:pk>/",
        DraftDistinctionViewSet.as_view({"delete": "destroy"}),
        name="draft-distinctions-detail",
    ),
    path(
        "drafts/<int:draft_id>/distinctions/swap/",
        DraftDistinctionViewSet.as_view({"post": "swap"}),
        name="draft-distinctions-swap",
    ),
]
