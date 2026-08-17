"""URLs for scheduled-downtime announcements — mounted at ``/api/downtime/`` (#3194)."""

from django.urls import path

from world.downtime.views import NextDowntimeView

urlpatterns = [
    path("next/", NextDowntimeView.as_view(), name="downtime-next"),
]
