from django.urls import path

from web.api.views import HomePageAPIView, LoginAPIView

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
]
