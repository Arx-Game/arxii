"""Public registration URLs — mounted at ``/api/registration/`` (#3054)."""

from django.urls import path

from world.registration.views import RegistrationStatusView

urlpatterns = [
    path("status/", RegistrationStatusView.as_view(), name="registration-status"),
]
