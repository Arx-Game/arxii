from django.urls import path

from web.api.views import (
    HomePageAPIView,
    LoginAPIView,
    LogoutAPIView,
    ServerStatusAPIView,
)

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("status/", ServerStatusAPIView.as_view(), name="api-status"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("logout/", LogoutAPIView.as_view(), name="api-logout"),
]
