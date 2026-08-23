"""URL routes for the tavern games API (#3292)."""

from rest_framework.routers import DefaultRouter

from world.tavern_games.views import GameSessionViewSet, TavernGameViewSet

router = DefaultRouter()
router.register(r"games", TavernGameViewSet, basename="tavern-game")
router.register(r"sessions", GameSessionViewSet, basename="tavern-game-session")

urlpatterns = router.urls
