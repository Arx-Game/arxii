from django.urls import path

from web.api.views import HomePageAPIView, LoginAPIView, LogoutAPIView

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("logout/", LogoutAPIView.as_view(), name="api-logout"),
]
