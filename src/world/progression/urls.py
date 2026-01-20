"""
URL configuration for progression API endpoints.
"""

from django.urls import path

from world.progression.views import AccountProgressionView

urlpatterns = [
    path("account/", AccountProgressionView.as_view(), name="account-progression"),
]
