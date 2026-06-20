"""URL patterns for the consent API."""

from rest_framework.routers import DefaultRouter

from world.consent.views import (
    SocialConsentCategoryRuleViewSet,
    SocialConsentCategoryViewSet,
    SocialConsentPreferenceViewSet,
    SocialConsentWhitelistViewSet,
)

router = DefaultRouter()
router.register("categories", SocialConsentCategoryViewSet, basename="categories")
router.register("preferences", SocialConsentPreferenceViewSet, basename="preferences")
router.register("category-rules", SocialConsentCategoryRuleViewSet, basename="category-rules")
router.register("whitelist", SocialConsentWhitelistViewSet, basename="whitelist")

urlpatterns = router.urls
