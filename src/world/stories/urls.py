from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.stories.views import (
    ChapterViewSet,
    EpisodeSceneViewSet,
    EpisodeViewSet,
    PlayerTrustViewSet,
    StoryFeedbackViewSet,
    StoryParticipationViewSet,
    StoryViewSet,
)

router = DefaultRouter()
router.register(r"stories", StoryViewSet)
router.register(r"chapters", ChapterViewSet)
router.register(r"episodes", EpisodeViewSet)
router.register(r"episode-scenes", EpisodeSceneViewSet)
router.register(r"story-participations", StoryParticipationViewSet)
router.register(r"player-trust", PlayerTrustViewSet)
router.register(r"story-feedback", StoryFeedbackViewSet)

urlpatterns = [
    path("api/", include(router.urls)),
]
