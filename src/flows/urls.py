"""URL configuration for the flows authoring API (#3417)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from flows.views import (
    DslCatalogViewSet,
    FlowDefinitionViewSet,
    TriggerDefinitionViewSet,
    TriggerViewSet,
)

app_name = "flows"

router = DefaultRouter()
router.register(r"catalog", DslCatalogViewSet, basename="flows-catalog")
router.register(r"flows", FlowDefinitionViewSet, basename="flow-definition")
router.register(r"trigger-definitions", TriggerDefinitionViewSet, basename="trigger-definition")
router.register(r"triggers", TriggerViewSet, basename="trigger")

urlpatterns = [
    path("", include(router.urls)),
]
