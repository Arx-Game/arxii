"""URL configuration for the GM system."""

from rest_framework.routers import DefaultRouter

from world.gm.views import (
    GMApplicationViewSet,
    GMTableMembershipViewSet,
    GMTableViewSet,
)

app_name = "gm"

router = DefaultRouter()
router.register("applications", GMApplicationViewSet, basename="gm-application")
router.register("tables", GMTableViewSet, basename="gm-table")
router.register("table-memberships", GMTableMembershipViewSet, basename="gm-table-membership")

urlpatterns = router.urls
