"""URLs for the Almanach de Catenys API (#3983): the house-builder reads
(realm/founder reads open to any authenticated account; houses stay staff-only)."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.societies.houses.almanach_views import (
    AlmanachFamilyKindViewSet,
    AlmanachFamilyViewSet,
    AlmanachFrontView,
    AlmanachHoldingKindViewSet,
    AlmanachHouseViewSet,
    AlmanachPersonViewSet,
    AlmanachRealmViewSet,
    AlmanachSearchView,
    AlmanachTemplateViewSet,
    AlmanachTitleViewSet,
    AlmanachUnionKindViewSet,
    LandShapeViewSet,
)

router = DefaultRouter()
router.register(r"realms", AlmanachRealmViewSet, basename="almanach-realm")
router.register(r"houses", AlmanachHouseViewSet, basename="almanach-house")
router.register(r"land-shapes", LandShapeViewSet, basename="almanach-land-shape")
# #4239: every family, every person.
router.register(r"people", AlmanachPersonViewSet, basename="almanach-person")
router.register(r"titles", AlmanachTitleViewSet, basename="almanach-title")
router.register(r"families", AlmanachFamilyViewSet, basename="almanach-family")
router.register(r"kinds", AlmanachFamilyKindViewSet, basename="almanach-kind")
router.register(r"templates", AlmanachTemplateViewSet, basename="almanach-template")
router.register(r"union-kinds", AlmanachUnionKindViewSet, basename="almanach-union-kind")
router.register(r"holding-kinds", AlmanachHoldingKindViewSet, basename="almanach-holding-kind")

app_name = "almanach"
urlpatterns = [
    path("front/", AlmanachFrontView.as_view(), name="almanach-front"),
    path("search/", AlmanachSearchView.as_view(), name="almanach-search"),
    *router.urls,
]
