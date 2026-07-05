"""Action-points URL configuration (#1446)."""

from django.urls import path

from world.action_points.views import ActionPointPoolView

app_name = "action_points"
urlpatterns = [
    path("<int:character_id>/", ActionPointPoolView.as_view(), name="character-action-points"),
]
