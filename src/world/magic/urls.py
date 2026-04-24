"""
URL configuration for magic system API.

Note: Affinity and Resonance routes have been removed.
These are now served from the mechanics app as ModifierTarget entries
filtered by category. Use /api/mechanics/modifier-types/?category=affinity
or /api/mechanics/modifier-types/?category=resonance instead.
"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from world.magic.views import (
    CharacterAnimaRitualViewSet,
    CharacterAnimaViewSet,
    CharacterAuraViewSet,
    CharacterFacetViewSet,
    CharacterGiftViewSet,
    CharacterResonanceViewSet,
    EffectTypeViewSet,
    FacetViewSet,
    GiftViewSet,
    PendingAlterationViewSet,
    PoseEndorsementViewSet,
    RestrictionViewSet,
    RitualPerformView,
    SceneEntryEndorsementViewSet,
    TechniqueStyleViewSet,
    TechniqueViewSet,
    ThreadPullPreviewView,
    ThreadViewSet,
    ThreadWeavingTeachingOfferViewSet,
)

app_name = "magic"

router = DefaultRouter()

# Lookup tables (read-only)
# Note: affinities and resonances are now in mechanics app as ModifierTarget.
router.register("styles", TechniqueStyleViewSet, basename="technique-style")
router.register("effect-types", EffectTypeViewSet, basename="effect-type")
router.register("restrictions", RestrictionViewSet, basename="restriction")
router.register("facets", FacetViewSet, basename="facet")

# CG CRUD endpoints
router.register("gifts", GiftViewSet, basename="gift")
router.register("techniques", TechniqueViewSet, basename="technique")

# Character magic data
router.register("character-auras", CharacterAuraViewSet, basename="character-aura")
router.register("character-resonances", CharacterResonanceViewSet, basename="character-resonance")
router.register("character-gifts", CharacterGiftViewSet, basename="character-gift")
router.register("character-anima", CharacterAnimaViewSet, basename="character-anima")
router.register(
    "character-anima-rituals", CharacterAnimaRitualViewSet, basename="character-anima-ritual"
)
router.register("character-facets", CharacterFacetViewSet, basename="character-facet")

# Alterations
router.register(
    "pending-alterations",
    PendingAlterationViewSet,
    basename="pending-alteration",
)

# Resonance Pivot Spec A §4.5 — Thread / Ritual / Teaching offer surface
router.register("threads", ThreadViewSet, basename="thread")
router.register(
    "teaching-offers",
    ThreadWeavingTeachingOfferViewSet,
    basename="thread-weaving-teaching-offer",
)

# Resonance Pivot Spec C — Gain surfaces
router.register(
    "pose-endorsements",
    PoseEndorsementViewSet,
    basename="pose-endorsement",
)
router.register(
    "scene-entry-endorsements",
    SceneEntryEndorsementViewSet,
    basename="scene-entry-endorsement",
)

urlpatterns = [
    *router.urls,
    path(
        "thread-pull-preview/",
        ThreadPullPreviewView.as_view(),
        name="thread-pull-preview",
    ),
    path(
        "rituals/perform/",
        RitualPerformView.as_view(),
        name="ritual-perform",
    ),
]
