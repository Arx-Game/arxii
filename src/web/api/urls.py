from django.urls import include, path

from web.api.views import (
    CurrentUserAPIView,
    HomePageAPIView,
    LogoutAPIView,
    RegisterAvailabilityAPIView,
    ServerStatusAPIView,
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
    # Django-allauth headless API endpoints
    path("auth/", include("allauth.headless.urls")),
]
