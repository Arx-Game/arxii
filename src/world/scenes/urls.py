from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.scenes.views import PersonaViewSet, SceneMessageViewSet, SceneViewSet

router = DefaultRouter()
router.register(r"scenes", SceneViewSet)
router.register(r"personas", PersonaViewSet, basename="persona")
router.register(r"messages", SceneMessageViewSet, basename="scenemessage")

urlpatterns = [
    path("api/", include(router.urls)),
]
