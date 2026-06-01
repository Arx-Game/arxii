"""URL routes for the unified NPC service framework."""

from rest_framework.routers import DefaultRouter

from world.npc_services.views import (
    NPCRoleViewSet,
    NPCServiceOfferViewSet,
    NPCStandingViewSet,
    PermitOfferDetailsViewSet,
)

router = DefaultRouter()
router.register(r"standings", NPCStandingViewSet, basename="npc-standing")
router.register(r"roles", NPCRoleViewSet, basename="npc-role")
router.register(r"offers", NPCServiceOfferViewSet, basename="npc-offer")
router.register(r"permit-details", PermitOfferDetailsViewSet, basename="npc-permit-details")

urlpatterns = router.urls
