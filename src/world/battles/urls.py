"""URL configuration for the battles read API (#2009)."""

from rest_framework.routers import DefaultRouter

from world.battles.views import BattleViewSet

router = DefaultRouter()
router.register("", BattleViewSet, basename="battles")

app_name = "battles"
urlpatterns = router.urls
