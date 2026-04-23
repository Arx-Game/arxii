from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.stories.views import (
    AggregateBeatContributionViewSet,
    AssistantGMClaimViewSet,
    BeatViewSet,
    ChapterViewSet,
    EpisodeSceneViewSet,
    EpisodeViewSet,
    ExpireOverdueBeatsView,
    GlobalStoryProgressViewSet,
    GMQueueView,
    GroupStoryProgressViewSet,
    MyActiveStoriesView,
    PlayerTrustViewSet,
    SessionRequestViewSet,
    StaffWorkloadView,
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
    # Wave 10: Dashboard endpoints (APIView — aggregate, not paginated).
    # These MUST be registered before the router include so they take precedence
    # over the router's story-detail route (api/stories/{pk}/).
    path("api/stories/my-active/", MyActiveStoriesView.as_view(), name="stories-my-active"),
    path("api/stories/gm-queue/", GMQueueView.as_view(), name="stories-gm-queue"),
    path(
        "api/stories/staff-workload/",
        StaffWorkloadView.as_view(),
        name="stories-staff-workload",
    ),
    # Wave 11: Staff trigger endpoint.
    path(
        "api/stories/expire-overdue-beats/",
        ExpireOverdueBeatsView.as_view(),
        name="stories-expire-overdue-beats",
    ),
    path("api/", include(router.urls)),
]
