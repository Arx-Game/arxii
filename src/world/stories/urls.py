from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.stories.views import (
    AggregateBeatContributionViewSet,
    AssistantGMClaimViewSet,
    BeatViewSet,
    ChapterViewSet,
    EpisodeSceneViewSet,
    EpisodeViewSet,
    GlobalStoryProgressViewSet,
    GroupStoryProgressViewSet,
    PlayerTrustViewSet,
    SessionRequestViewSet,
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
# Phase 2 ViewSets
router.register(r"group-story-progress", GroupStoryProgressViewSet)
router.register(r"global-story-progress", GlobalStoryProgressViewSet)
router.register(r"aggregate-beat-contributions", AggregateBeatContributionViewSet)
router.register(r"assistant-gm-claims", AssistantGMClaimViewSet)
router.register(r"session-requests", SessionRequestViewSet)
router.register(r"beats", BeatViewSet)

urlpatterns = [
    path("api/", include(router.urls)),
]
