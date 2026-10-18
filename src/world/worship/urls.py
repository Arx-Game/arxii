"""URL routing for the worship API (#2355)."""

from rest_framework.routers import DefaultRouter

from world.worship.live_views import LivePromptViewSet
from world.worship.staff_views import StaffBeingViewSet
from world.worship.steward_views import (
    StewardAnswerViewSet,
    StewardedBeingViewSet,
    StewardPledgeViewSet,
    StewardPromptViewSet,
    StewardSacrificeLineViewSet,
)
from world.worship.views import (
    MiracleViewSet,
    PledgeCardViewSet,
    PledgeViewSet,
    PrayerViewSet,
    VisionViewSet,
    WorshippedBeingViewSet,
    WorshipRiteViewSet,
)

router = DefaultRouter()
router.register("beings", WorshippedBeingViewSet, basename="worshipped-being")
router.register("miracles", MiracleViewSet, basename="miracle")
router.register("rites", WorshipRiteViewSet, basename="worship-rite")
router.register("prayers", PrayerViewSet, basename="prayer")
router.register("pledges", PledgeViewSet, basename="pledge")
router.register("pledge-cards", PledgeCardViewSet, basename="pledge-card")
router.register("visions", VisionViewSet, basename="vision")
router.register("admin/beings", StaffBeingViewSet, basename="staff-being")
# #4333 slice 4: the table page's Beings section, for a stewarded being's table GM.
router.register("stewarded-beings", StewardedBeingViewSet, basename="stewarded-being")
router.register("steward-pledges", StewardPledgeViewSet, basename="steward-pledge")
router.register("steward-answers", StewardAnswerViewSet, basename="steward-answer")
router.register(
    "steward-sacrifice-lines", StewardSacrificeLineViewSet, basename="steward-sacrifice-line"
)
router.register("steward-prompts", StewardPromptViewSet, basename="steward-prompt")
# #4333 slice 5: a scene GM answers a rite performed in their scene.
router.register("live-answers", LivePromptViewSet, basename="live-answer")

app_name = "worship"
urlpatterns = router.urls
