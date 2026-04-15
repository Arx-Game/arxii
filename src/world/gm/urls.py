"""URL configuration for the GM system."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.gm.views import (
    GMApplicationActionView,
    GMApplicationQueueView,
    GMApplicationViewSet,
    GMInviteClaimView,
    GMRosterInviteViewSet,
    GMTableMembershipViewSet,
    GMTableViewSet,
)

app_name = "gm"

router = DefaultRouter()
router.register("applications", GMApplicationViewSet, basename="gm-application")
router.register("tables", GMTableViewSet, basename="gm-table")
router.register("table-memberships", GMTableMembershipViewSet, basename="gm-table-membership")
router.register("invites", GMRosterInviteViewSet, basename="gm-invite")

# Ordering is load-bearing: ``invites/claim/`` MUST be registered before
# ``router.urls``. DRF's default detail regex for the ``invites`` viewset
# (``invites/<pk>/``) would otherwise match ``invites/claim/`` with
# ``pk="claim"`` and route to GMRosterInviteViewSet.retrieve, silently
# breaking the claim endpoint. Don't reorder without keeping this in mind.
urlpatterns = [
    path("invites/claim/", GMInviteClaimView.as_view(), name="gm-invite-claim"),
    path("", include(router.urls)),
    path("queue/", GMApplicationQueueView.as_view(), name="gm-application-queue"),
    path(
        "queue/<int:pk>/<str:action>/",
        GMApplicationActionView.as_view(),
        name="gm-application-action",
    ),
]
