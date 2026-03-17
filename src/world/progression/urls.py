"""
URL configuration for progression API endpoints.
"""

from django.urls import path

from world.progression.views import AccountProgressionView, ClaimKudosView

urlpatterns = [
    path("account/", AccountProgressionView.as_view(), name="account-progression"),
    path("claim-kudos/", ClaimKudosView.as_view(), name="claim-kudos"),
]
