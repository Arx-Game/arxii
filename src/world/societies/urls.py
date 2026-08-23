"""URLs for the societies player API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from world.societies.ranking_views import RankingDisplayViewSet
from world.societies.views import (
    OrganizationMembershipOfferViewSet,
    OrganizationMembershipViewSet,
    OrganizationRankViewSet,
    OrganizationReputationViewSet,
    OrganizationViewSet,
    OrgAppealViewSet,
    ProclamationViewSet,
    StandingDeclarationViewSet,
)

app_name = "societies"

router = DefaultRouter()
router.register(r"rankings", RankingDisplayViewSet, basename="ranking-display")
router.register(r"organizations", OrganizationViewSet, basename="organization")
router.register(r"proclamations", ProclamationViewSet, basename="proclamation")
router.register(r"memberships", OrganizationMembershipViewSet, basename="organization-membership")
router.register(r"ranks", OrganizationRankViewSet, basename="organization-rank")
router.register(
    r"reputations",
    OrganizationReputationViewSet,
    basename="organization-reputation",
)
router.register(
    r"offers",
    OrganizationMembershipOfferViewSet,
    basename="organization-membership-offer",
)
router.register(
    r"standing-declarations",
    StandingDeclarationViewSet,
    basename="standing-declaration",
)
router.register(r"appeals", OrgAppealViewSet, basename="organization-appeal")

urlpatterns = [
    path("", include(router.urls)),
]
