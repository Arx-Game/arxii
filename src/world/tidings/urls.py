"""URL configuration for the public-reaction tidings feed API (#1450)."""

from django.urls import path

from world.tidings.views import PublicFeedView

urlpatterns = [
    path("feed/", PublicFeedView.as_view(), name="public-feed"),
]
