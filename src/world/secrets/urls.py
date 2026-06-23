"""URL configuration for the secrets API (#1334, #1429)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.secrets.views import (
    GrievanceOptionListView,
    KnownSecretViewSet,
    SecretGrievanceView,
)

router = DefaultRouter()
router.register("known", KnownSecretViewSet, basename="known-secret")

urlpatterns = [
    # #1429 — the secret-victim grievance flow (mirrors the telnet +grievance command).
    path("grievance-options/", GrievanceOptionListView.as_view(), name="grievance-options"),
    path("grievance/", SecretGrievanceView.as_view(), name="secret-grievance"),
    *router.urls,
]
