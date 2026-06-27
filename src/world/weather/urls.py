"""URL configuration for the weather API (#1522)."""

from django.urls import path

from world.weather.views import WeatherViewSet

app_name = "weather"

weather_conditions = WeatherViewSet.as_view({"get": "conditions"})

urlpatterns = [
    path("conditions/", weather_conditions, name="weather-conditions"),
]
