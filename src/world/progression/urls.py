"""
URL configuration for progression API endpoints.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.progression.views import AccountProgressionView, ClaimKudosView, VoteViewSet

router = DefaultRouter()
router.register("votes", VoteViewSet, basename="vote")

urlpatterns = [
    path("account/", AccountProgressionView.as_view(), name="account-progression"),
    path("claim-kudos/", ClaimKudosView.as_view(), name="claim-kudos"),
    path("", include(router.urls)),
]
