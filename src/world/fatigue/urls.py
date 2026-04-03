"""Fatigue system URL configuration."""

from django.urls import path

from world.fatigue.views import FatigueStatusView, RestView

app_name = "fatigue"
urlpatterns = [
    path("status/", FatigueStatusView.as_view(), name="fatigue-status"),
    path("rest/", RestView.as_view(), name="rest"),
]
