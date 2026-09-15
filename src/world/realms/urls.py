from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.realms.views import RealmViewSet

app_name = "realms"

router = DefaultRouter()
router.register(r"", RealmViewSet, basename="realm")

urlpatterns = [
    path("", include(router.urls)),
]
