"""URL configuration for the clue read API (#1575)."""

from django.urls import path

from world.clues.views import ClueSearchView, MyHeldCluesView

app_name = "clues"

urlpatterns = [
    path("search/", ClueSearchView.as_view(), name="clue-search"),
    path("held/", MyHeldCluesView.as_view(), name="held-clues"),
]
