"""Staff-only invite management URLs — mounted at ``/api/staff/`` (#3054)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.registration.views import AccountInviteViewSet, VerificationLinkView

router = DefaultRouter()
router.register("invites", AccountInviteViewSet, basename="account-invite")

urlpatterns = [
    path("verification-link/", VerificationLinkView.as_view(), name="staff-verification-link"),
    *router.urls,
]
