from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.narrative.views import (
    GemitViewSet,
    MarkNarrativeMessageAcknowledgedView,
    MyNarrativeMessagesView,
    UserCategoryMuteViewSet,
    UserStoryMuteViewSet,
)

router = DefaultRouter()
router.register(r"gemits", GemitViewSet, basename="gemit")
router.register(r"story-mutes", UserStoryMuteViewSet, basename="storymute")
router.register(r"category-mutes", UserCategoryMuteViewSet, basename="categorymute")

urlpatterns = [
    path("my-messages/", MyNarrativeMessagesView.as_view(), name="narrative-my-messages"),
    path(
        "deliveries/<int:pk>/acknowledge/",
        MarkNarrativeMessageAcknowledgedView.as_view(),
        name="narrative-delivery-acknowledge",
    ),
    path("", include(router.urls)),
]
