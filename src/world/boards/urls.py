"""URL configuration for the boards API (#3286)."""

from rest_framework.routers import DefaultRouter

from world.boards.views import BoardPostViewSet, BoardViewSet

app_name = "boards"

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("posts", BoardPostViewSet, basename="board-post")

urlpatterns = router.urls
