from django.urls import path
from rest_framework.routers import DefaultRouter

from web.api.views import HomePageAPIView, LoginAPIView, LogoutAPIView
from world.roster.views import RosterEntryViewSet

router = DefaultRouter()
router.register("roster", RosterEntryViewSet, basename="roster")

urlpatterns = [
    path("homepage/", HomePageAPIView.as_view(), name="api-homepage"),
    path("login/", LoginAPIView.as_view(), name="api-login"),
    path("logout/", LogoutAPIView.as_view(), name="api-logout"),
]

urlpatterns += router.urls
