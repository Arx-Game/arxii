"""URL routes for the tasking board API."""

from rest_framework.routers import DefaultRouter

from world.tasking.views import (
    OrgRosterViewSet,
    OrgTaskViewSet,
    TaskOutcomeRouteViewSet,
    TaskTemplateViewSet,
)

router = DefaultRouter()
router.register(r"templates", TaskTemplateViewSet, basename="task-template")
router.register(r"routes", TaskOutcomeRouteViewSet, basename="task-outcome-route")
router.register(r"tasks", OrgTaskViewSet, basename="org-task")
router.register(r"roster", OrgRosterViewSet, basename="org-roster")

urlpatterns = router.urls
