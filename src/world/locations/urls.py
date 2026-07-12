"""URL configuration for the locations API (#1522, #2222)."""

from django.urls import path

from world.locations.views import ComfortViewSet, PortalDestinationsViewSet

app_name = "locations"

comfort_summary = ComfortViewSet.as_view({"get": "summary"})
portal_destinations = PortalDestinationsViewSet.as_view({"get": "list"})

urlpatterns = [
    path("comfort/", comfort_summary, name="comfort-summary"),
    path("portal-destinations/", portal_destinations, name="portal-destinations"),
]
