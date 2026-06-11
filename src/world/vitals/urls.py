"""Vitals system URL configuration."""

from django.urls import path

from world.vitals.views import CharacterVitalsView

app_name = "vitals"
urlpatterns = [
    path("<int:character_id>/", CharacterVitalsView.as_view(), name="character-vitals"),
]
