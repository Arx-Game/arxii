from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.scenes.action_views import SceneActionRequestViewSet
from world.scenes.interaction_views import (
    InteractionFavoriteViewSet,
    InteractionReactionViewSet,
    InteractionViewSet,
)
from world.scenes.place_views import PlaceViewSet
from world.scenes.views import (
    PersonaViewSet,
    SceneSummaryRevisionViewSet,
    SceneViewSet,
)

router = DefaultRouter()
router.register(r"scenes", SceneViewSet)
router.register(r"personas", PersonaViewSet, basename="persona")
router.register(r"interactions", InteractionViewSet, basename="interaction")
router.register(
    r"interaction-favorites",
    InteractionFavoriteViewSet,
    basename="interactionfavorite",
)
router.register(
    r"interaction-reactions",
    InteractionReactionViewSet,
    basename="interactionreaction",
)
router.register(
    r"summary-revisions",
    SceneSummaryRevisionViewSet,
    basename="scenesummaryrevision",
)
router.register(r"places", PlaceViewSet, basename="place")
router.register(
    r"action-requests",
    SceneActionRequestViewSet,
    basename="sceneactionrequest",
)

urlpatterns = [
    path("api/", include(router.urls)),
]
