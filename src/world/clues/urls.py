"""URL configuration for the clue read API (#1575)."""

from django.urls import path

from world.clues.views import MyHeldCluesView

app_name = "clues"

urlpatterns = [
    path("held/", MyHeldCluesView.as_view(), name="held-clues"),
]
