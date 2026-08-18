"""URL configuration for the secrets API (#1334, #1429, #3266)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.secrets.views import (
    AuthoredSecretViewSet,
    GossipActionView,
    GossipListView,
    GrievanceOptionListView,
    KnownSecretViewSet,
    SecretGrievanceView,
)

app_name = "secrets"

router = DefaultRouter()
router.register("known", KnownSecretViewSet, basename="known-secret")
router.register("authored", AuthoredSecretViewSet, basename="authored")

urlpatterns = [
    # #1429 — the secret-victim grievance flow (mirrors the telnet +grievance command).
    path("grievance-options/", GrievanceOptionListView.as_view(), name="grievance-options"),
    path("grievance/", SecretGrievanceView.as_view(), name="secret-grievance"),
    # #1572 — the gossip web surface (mirrors the telnet `gossip` command).
    path("gossip/", GossipListView.as_view(), name="gossip-list"),
    path("gossip/action/", GossipActionView.as_view(), name="gossip-action"),
    *router.urls,
]
