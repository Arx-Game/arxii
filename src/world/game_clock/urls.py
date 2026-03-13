"""URL configuration for the game clock API."""

from django.urls import path

from world.game_clock.views import ClockViewSet

app_name = "game_clock"

clock_state = ClockViewSet.as_view({"get": "list"})
clock_convert = ClockViewSet.as_view({"get": "convert"})
clock_adjust = ClockViewSet.as_view({"post": "adjust"})
clock_ratio = ClockViewSet.as_view({"post": "ratio"})
clock_pause = ClockViewSet.as_view({"post": "pause"})
clock_unpause = ClockViewSet.as_view({"post": "unpause"})

urlpatterns = [
    path("", clock_state, name="clock-state"),
    path("convert/", clock_convert, name="clock-convert"),
    path("adjust/", clock_adjust, name="clock-adjust"),
    path("ratio/", clock_ratio, name="clock-ratio"),
    path("pause/", clock_pause, name="clock-pause"),
    path("unpause/", clock_unpause, name="clock-unpause"),
]
