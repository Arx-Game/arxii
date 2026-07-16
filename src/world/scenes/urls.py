from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.scenes.action_views import SceneActionRequestViewSet, SceneActionTargetViewSet
from world.scenes.friend_views import FriendshipViewSet, RivalryViewSet
from world.scenes.interaction_views import (
    InteractionFavoriteViewSet,
    InteractionReactionViewSet,
    InteractionViewSet,
    ReactionEmojiViewSet,
)
from world.scenes.place_views import PlaceViewSet
from world.scenes.reaction_views import ReactionWindowViewSet
from world.scenes.social_control_views import BlockViewSet, MuteViewSet
from world.scenes.speaker_queue_views import SpeakerQueueViewSet
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
    r"reaction-emoji",
    ReactionEmojiViewSet,
    basename="reactionemoji",
)
router.register(
    r"summary-revisions",
    SceneSummaryRevisionViewSet,
    basename="scenesummaryrevision",
)
router.register(r"places", PlaceViewSet, basename="place")
router.register(r"speaker-queues", SpeakerQueueViewSet, basename="speakerqueue")
router.register(
    r"action-requests",
    SceneActionRequestViewSet,
    basename="sceneactionrequest",
)
router.register(
    r"action-targets",
    SceneActionTargetViewSet,
    basename="sceneactiontarget",
)
router.register(
    r"reaction-windows",
    ReactionWindowViewSet,
    basename="reactionwindow",
)
router.register(r"blocks", BlockViewSet, basename="block")
router.register(r"mutes", MuteViewSet, basename="mute")
router.register(r"friends", FriendshipViewSet, basename="friend")
router.register(r"rivals", RivalryViewSet, basename="rival")

urlpatterns = [
    path("api/", include(router.urls)),
]
