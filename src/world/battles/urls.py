"""URL configuration for the battles read API (#2009, #2010)."""

from rest_framework.routers import DefaultRouter

from world.battles.views import BattleMapBlueprintViewSet, BattleUnitTemplateViewSet, BattleViewSet

router = DefaultRouter()
# Catalog viewsets registered BEFORE BattleViewSet's empty "" prefix
# deliberately: BattleViewSet's detail route matches any single path segment
# as a pk (r"^(?P<pk>[^/.]+)/$"), so if it were registered first its pattern
# would shadow "map-blueprints/"/"unit-templates/" (Django/DRF try
# urlpatterns in registration order and stop at the first match).
router.register("map-blueprints", BattleMapBlueprintViewSet, basename="battle-map-blueprints")
router.register("unit-templates", BattleUnitTemplateViewSet, basename="battle-unit-templates")
router.register("", BattleViewSet, basename="battles")

app_name = "battles"
urlpatterns = router.urls
