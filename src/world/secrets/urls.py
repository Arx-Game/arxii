"""URL configuration for the secrets API (#1334)."""

from rest_framework.routers import DefaultRouter

from world.secrets.views import KnownSecretViewSet

router = DefaultRouter()
router.register("known", KnownSecretViewSet, basename="known-secret")

urlpatterns = router.urls
