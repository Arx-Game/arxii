"""Fatigue system URL configuration."""

from django.urls import path

from world.fatigue.views import RestView

app_name = "fatigue"
urlpatterns = [
    path("rest/", RestView.as_view(), name="rest"),
]
