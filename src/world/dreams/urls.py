"""Dreams system URL configuration."""

from django.urls import path

from world.dreams.views import CharacterDreamStateView

app_name = "dreams"
urlpatterns = [
    path("<int:character_id>/", CharacterDreamStateView.as_view(), name="character-dream-state"),
]
