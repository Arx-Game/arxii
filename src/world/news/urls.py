"""URL configuration for the public-reaction news feed API (#1450)."""

from django.urls import path

from world.news.views import PublicFeedView

urlpatterns = [
    path("feed/", PublicFeedView.as_view(), name="public-feed"),
]
