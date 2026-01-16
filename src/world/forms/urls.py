from rest_framework.routers import DefaultRouter

from world.forms.views import (
    BuildViewSet,
    CharacterFormViewSet,
    FormTraitViewSet,
    HeightBandViewSet,
)

router = DefaultRouter()
router.register(r"traits", FormTraitViewSet, basename="formtrait")
router.register(r"character-forms", CharacterFormViewSet, basename="characterform")
router.register(r"height-bands", HeightBandViewSet, basename="heightband")
router.register(r"builds", BuildViewSet, basename="build")

urlpatterns = router.urls
