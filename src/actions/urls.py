"""URL configuration for actions API."""

from django.urls import path

from actions.views import AvailableActionsView

app_name = "actions"

urlpatterns = [
    path(
        "characters/<int:character_id>/available/",
        AvailableActionsView.as_view(),
        name="available-actions",
    ),
]
