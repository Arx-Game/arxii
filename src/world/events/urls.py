from rest_framework.routers import DefaultRouter

from world.events.views import EventViewSet

router = DefaultRouter()
router.register("", EventViewSet, basename="event")

app_name = "events"
urlpatterns = router.urls
