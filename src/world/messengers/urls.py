"""URL configuration for the missives API (#3289), mounted at ``api/missives/``."""

from rest_framework.routers import SimpleRouter

from world.messengers.views import MissiveViewSet

app_name = "messengers"

router = SimpleRouter()
router.register("", MissiveViewSet, basename="missive")

urlpatterns = router.urls
