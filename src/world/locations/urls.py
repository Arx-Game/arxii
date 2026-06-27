"""URL configuration for the locations API (#1522)."""

from django.urls import path

from world.locations.views import ComfortViewSet

app_name = "locations"

comfort_summary = ComfortViewSet.as_view({"get": "summary"})

urlpatterns = [
    path("comfort/", comfort_summary, name="comfort-summary"),
]
