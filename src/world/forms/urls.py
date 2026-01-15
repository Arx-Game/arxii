from rest_framework.routers import DefaultRouter

from world.forms.views import CharacterFormViewSet, FormTraitViewSet

router = DefaultRouter()
router.register(r"traits", FormTraitViewSet, basename="formtrait")
router.register(r"character-forms", CharacterFormViewSet, basename="characterform")

urlpatterns = router.urls
