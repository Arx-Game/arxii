from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.scenes.interaction_views import InteractionFavoriteViewSet, InteractionViewSet
from world.scenes.views import (
    PersonaViewSet,
    SceneMessageReactionViewSet,
    SceneMessageViewSet,
    SceneViewSet,
)

router = DefaultRouter()
router.register(r"scenes", SceneViewSet)
router.register(r"personas", PersonaViewSet, basename="persona")
router.register(r"messages", SceneMessageViewSet, basename="scenemessage")
router.register(
    r"reactions",
    SceneMessageReactionViewSet,
    basename="scenemessagereaction",
)
router.register(r"interactions", InteractionViewSet, basename="interaction")
router.register(
    r"interaction-favorites",
    InteractionFavoriteViewSet,
    basename="interactionfavorite",
)

urlpatterns = [
    path("api/", include(router.urls)),
]
