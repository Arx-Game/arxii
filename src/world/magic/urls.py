"""
URL configuration for magic system API.

Note: Affinity and Resonance routes have been removed.
These are now served from the mechanics app as ModifierType entries
filtered by category. Use /api/mechanics/modifier-types/?category=affinity
or /api/mechanics/modifier-types/?category=resonance instead.
"""

from rest_framework.routers import DefaultRouter

from world.magic.views import (
    AnimaRitualTypeViewSet,
    CharacterAnimaRitualViewSet,
    CharacterAnimaViewSet,
    CharacterAuraViewSet,
    CharacterGiftViewSet,
    CharacterPowerViewSet,
    CharacterResonanceViewSet,
    GiftViewSet,
    IntensityTierViewSet,
    PowerViewSet,
    ThreadJournalViewSet,
    ThreadResonanceViewSet,
    ThreadTypeViewSet,
    ThreadViewSet,
)

app_name = "magic"

router = DefaultRouter()

# Lookup tables (read-only)
# Note: affinities and resonances are now in mechanics app as ModifierType
router.register("intensity-tiers", IntensityTierViewSet, basename="intensity-tier")
router.register("anima-ritual-types", AnimaRitualTypeViewSet, basename="anima-ritual-type")
router.register("thread-types", ThreadTypeViewSet, basename="thread-type")
router.register("gifts", GiftViewSet, basename="gift")
router.register("powers", PowerViewSet, basename="power")

# Character magic data
router.register("character-auras", CharacterAuraViewSet, basename="character-aura")
router.register("character-resonances", CharacterResonanceViewSet, basename="character-resonance")
router.register("character-gifts", CharacterGiftViewSet, basename="character-gift")
router.register("character-powers", CharacterPowerViewSet, basename="character-power")
router.register("character-anima", CharacterAnimaViewSet, basename="character-anima")
router.register(
    "character-anima-rituals", CharacterAnimaRitualViewSet, basename="character-anima-ritual"
)

# Threads (relationships)
router.register("threads", ThreadViewSet, basename="thread")
router.register("thread-journals", ThreadJournalViewSet, basename="thread-journal")
router.register("thread-resonances", ThreadResonanceViewSet, basename="thread-resonance")

urlpatterns = router.urls
