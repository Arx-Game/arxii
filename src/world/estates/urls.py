from rest_framework.routers import DefaultRouter

from world.estates.views import (
    BequestViewSet,
    EstateClaimViewSet,
    EstateSettlementViewSet,
    WillExecutorViewSet,
    WillViewSet,
)

router = DefaultRouter()
router.register("wills", WillViewSet, basename="will")
router.register("bequests", BequestViewSet, basename="bequest")
router.register("executors", WillExecutorViewSet, basename="will-executor")
router.register("settlements", EstateSettlementViewSet, basename="estate-settlement")
router.register("claims", EstateClaimViewSet, basename="estate-claim")

app_name = "estates"
urlpatterns = router.urls
