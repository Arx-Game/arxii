from django.urls import path

from web.api.views import (
    HomePageAPIView,
    LoginAPIView,
    LogoutAPIView,
    RegisterAPIView,
    RegisterAvailabilityAPIView,
    ServerStatusAPIView,
)

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("status/", ServerStatusAPIView.as_view(), name="api-status"),
    path("register/", RegisterAPIView.as_view(), name="api-register"),
    path(
        "register/availability/",
        RegisterAvailabilityAPIView.as_view(),
        name="api-register-availability",
    ),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("logout/", LogoutAPIView.as_view(), name="api-logout"),
]
