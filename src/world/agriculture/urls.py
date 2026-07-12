"""Agriculture URL configuration."""

from django.urls import path

from world.agriculture.views import CollectFoodView

app_name = "agriculture"
urlpatterns = [
    path("collect/", CollectFoodView.as_view(), name="collect"),
]
