from django.urls import path

from world.narrative.views import (
    MarkNarrativeMessageAcknowledgedView,
    MyNarrativeMessagesView,
)

urlpatterns = [
    path("my-messages/", MyNarrativeMessagesView.as_view(), name="narrative-my-messages"),
    path(
        "deliveries/<int:pk>/acknowledge/",
        MarkNarrativeMessageAcknowledgedView.as_view(),
        name="narrative-delivery-acknowledge",
    ),
]
