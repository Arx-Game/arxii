from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

from world.events.views import (
    EventInvitationViewSet,
    EventViewSet,
    OrganizationSearchViewSet,
    SocietySearchViewSet,
)

# SimpleRouter for auxiliary endpoints (no root API view to collide with EventViewSet)
aux_router = SimpleRouter()
aux_router.register("invitations", EventInvitationViewSet, basename="event-invitation")
aux_router.register("organizations", OrganizationSearchViewSet, basename="organization-search")
aux_router.register("societies", SocietySearchViewSet, basename="society-search")

event_router = DefaultRouter()
event_router.register("", EventViewSet, basename="event")

app_name = "events"
urlpatterns = [
    # Auxiliary endpoints first to avoid collision with EventViewSet's <pk> pattern
    path("", include(aux_router.urls)),
    path("", include(event_router.urls)),
]
