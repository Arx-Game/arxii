"""URL configuration for actions API."""

from django.urls import path

from actions.views import AvailableActionsView, DispatchActionView, PersonaMenuView

app_name = "actions"

urlpatterns = [
    path(
        "characters/<int:character_id>/available/",
        AvailableActionsView.as_view(),
        name="available-actions",
    ),
    path(
        "characters/<int:character_id>/dispatch/",
        DispatchActionView.as_view(),
        name="dispatch-action",
    ),
    path(
        "characters/<int:character_id>/personas/<int:persona_id>/menu/",
        PersonaMenuView.as_view(),
        name="persona-menu",
    ),
]
