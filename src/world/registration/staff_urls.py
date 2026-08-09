"""Staff-only invite management URLs — mounted at ``/api/staff/`` (#3054)."""

from rest_framework.routers import DefaultRouter

from world.registration.views import AccountInviteViewSet

router = DefaultRouter()
router.register("invites", AccountInviteViewSet, basename="account-invite")

urlpatterns = router.urls
