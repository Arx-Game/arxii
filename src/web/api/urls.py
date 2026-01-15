from django.urls import include, path

from web.api.views.general_views import (
    CurrentUserAPIView,
    EmailVerificationAPIView,
    HomePageAPIView,
    LogoutAPIView,
    RegisterAvailabilityAPIView,
    ResendEmailVerificationAPIView,
    ServerStatusAPIView,
)
from web.api.views.search_views import (
    OnlineCharacterSearchAPIView,
    RoomCharacterSearchAPIView,
)

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("status/", ServerStatusAPIView.as_view(), name="api-status"),
    path("user/", CurrentUserAPIView.as_view(), name="api-current-user"),
    path(
        "register/availability/",
        RegisterAvailabilityAPIView.as_view(),
        name="api-register-availability",
    ),
    # Custom logout endpoint (allauth headless doesn't provide one)
    path("auth/browser/v1/auth/logout", LogoutAPIView.as_view(), name="api-logout"),
    # Custom email verification endpoint (allauth headless API is broken)
    path(
        "auth/browser/v1/auth/email/verify",
        EmailVerificationAPIView.as_view(),
        name="api-email-verify",
    ),
    # Resend email verification for logged-in users
    path(
        "auth/browser/v1/auth/email/request",
        ResendEmailVerificationAPIView.as_view(),
        name="api-resend-email-verification",
    ),
    path(
        "characters/online/",
        OnlineCharacterSearchAPIView.as_view(),
        name="api-online-characters",
    ),
    path(
        "characters/room/",
        RoomCharacterSearchAPIView.as_view(),
        name="api-room-characters",
    ),
    # Django-allauth headless API endpoints
    path("auth/", include("allauth.headless.urls")),
    # Forms API
    path("forms/", include("world.forms.urls")),
]
