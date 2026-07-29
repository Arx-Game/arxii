"""URLs for the proclamations API (#2842)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.proclamations.views import (
    DomainEdictViewSet,
    EdictKindViewSet,
    ProclamationViewSet,
    StanceArchetypeViewSet,
)

app_name = "proclamations"

router = DefaultRouter()
router.register(r"stances", StanceArchetypeViewSet, basename="stance-archetype")
router.register(r"proclamations", ProclamationViewSet, basename="proclamation")
router.register(r"edict-kinds", EdictKindViewSet, basename="edict-kind")
router.register(r"edicts", DomainEdictViewSet, basename="domain-edict")

urlpatterns = [
    path("", include(router.urls)),
]
