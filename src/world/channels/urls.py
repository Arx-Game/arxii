"""URL configuration for the player channels API (#3299)."""

from rest_framework.routers import DefaultRouter

from world.channels.views import (
    ChannelMessageViewSet,
    ChannelSubscriptionViewSet,
    ChannelViewSet,
)

app_name = "channels"

router = DefaultRouter()
router.register("channels", ChannelViewSet, basename="channel")
router.register("subscriptions", ChannelSubscriptionViewSet, basename="channel-subscription")
router.register("messages", ChannelMessageViewSet, basename="channel-message")

urlpatterns = router.urls
