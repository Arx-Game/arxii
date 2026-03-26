"""URL configuration for the actions app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from actions.views import ActionTemplateViewSet

router = DefaultRouter()
router.register(r"action-templates", ActionTemplateViewSet, basename="actiontemplate")

urlpatterns = [
    path("", include(router.urls)),
]
