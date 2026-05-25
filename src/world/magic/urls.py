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
    ApplicablePullsView,
    CharacterAnimaViewSet,
    CharacterAuraViewSet,
    CharacterGiftViewSet,
    CharacterResonanceViewSet,
    EffectTypeViewSet,
    FacetViewSet,
    GiftViewSet,
    PendingAlterationViewSet,
    PendingStageAdvanceOfferViewSet,
    PoseEndorsementViewSet,
    ResonanceGrantViewSet,
    RestrictionViewSet,
    RitualPerformView,
    RitualSessionViewSet,
    RitualViewSet,
    RoomsByPropertyView,
    SceneEntryEndorsementViewSet,
    SineatingPendingOfferViewSet,
    SineatingRequestView,
    SineatingRespondView,
    SoulTetherAcceptView,
    SoulTetherDetailView,
    SoulTetherDissolveView,
    SoulTetherRescueView,
    StageAdvanceRespondView,
    TechniqueStyleViewSet,
    TechniqueViewSet,
    ThreadHubSummaryView,
    ThreadPullCommitView,
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
# Alterations
router.register(
    "pending-alterations",
    PendingAlterationViewSet,
    basename="pending-alteration",
)

# Resonance Pivot Spec A §4.5 — Thread / Ritual / Teaching offer surface
router.register("threads", ThreadViewSet, basename="thread")
router.register("rituals", RitualViewSet, basename="ritual")
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
router.register(
    "resonance-grants",
    ResonanceGrantViewSet,
    basename="resonance-grant",
)


urlpatterns = [
    # Literal paths MUST come before *router.urls so that "rituals/perform/" is
    # matched before the router's "rituals/<pk>/" pattern treats "perform" as a pk.
    path(
        "applicable-pulls/",
        ApplicablePullsView.as_view(),
        name="applicable-pulls",
    ),
    path(
        "rooms-by-property/",
        RoomsByPropertyView.as_view(),
        name="rooms-by-property",
    ),
    path(
        "thread-hub-summary/",
        ThreadHubSummaryView.as_view(),
        name="thread-hub-summary",
    ),
    path(
        "thread-pull-commit/",
        ThreadPullCommitView.as_view(),
        name="thread-pull-commit",
    ),
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
    # Covenants Slice B — Multi-participant ritual sessions.
    # These literal paths MUST come before *router.urls to avoid the router's
    # "rituals/<pk>/" pattern matching "sessions" as a pk.
    path(
        "rituals/sessions/",
        RitualSessionViewSet.as_view({"get": "list", "post": "create"}),
        name="ritual-session-list",
    ),
    path(
        "rituals/sessions/<int:pk>/",
        RitualSessionViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="ritual-session-detail",
    ),
    path(
        "rituals/sessions/<int:pk>/accept/",
        RitualSessionViewSet.as_view({"post": "accept"}),
        name="ritual-session-accept",
    ),
    path(
        "rituals/sessions/<int:pk>/decline/",
        RitualSessionViewSet.as_view({"post": "decline"}),
        name="ritual-session-decline",
    ),
    path(
        "rituals/sessions/<int:pk>/fire/",
        RitualSessionViewSet.as_view({"post": "fire"}),
        name="ritual-session-fire",
    ),
    # Spec B — Soul Tether endpoints (Phase 11)
    path(
        "soul-tether/accept/",
        SoulTetherAcceptView.as_view(),
        name="soul-tether-accept",
    ),
    path(
        "soul-tether/dissolve/",
        SoulTetherDissolveView.as_view(),
        name="soul-tether-dissolve",
    ),
    path(
        "soul-tether/sineating/request/",
        SineatingRequestView.as_view(),
        name="soul-tether-sineating-request",
    ),
    path(
        "soul-tether/sineating/respond/",
        SineatingRespondView.as_view(),
        name="soul-tether-sineating-respond",
    ),
    path(
        "soul-tether/rescue/",
        SoulTetherRescueView.as_view(),
        name="soul-tether-rescue",
    ),
    path(
        "soul-tether/<int:relationship_id>/",
        SoulTetherDetailView.as_view(),
        name="soul-tether-detail",
    ),
    # Task 1.6 — Sineater inbox: pending Sineating offers
    path(
        "soul-tether/sineating/pending/",
        SineatingPendingOfferViewSet.as_view({"get": "list"}),
        name="soul-tether-sineating-pending-list",
    ),
    path(
        "soul-tether/sineating/pending/<int:pk>/",
        SineatingPendingOfferViewSet.as_view({"get": "retrieve"}),
        name="soul-tether-sineating-pending-detail",
    ),
    # Task 1.7 — Sineater inbox: pending stage-advance bonus offers
    path(
        "soul-tether/stage-advance/pending/",
        PendingStageAdvanceOfferViewSet.as_view({"get": "list"}),
        name="soul-tether-stage-advance-pending-list",
    ),
    path(
        "soul-tether/stage-advance/pending/<int:pk>/",
        PendingStageAdvanceOfferViewSet.as_view({"get": "retrieve"}),
        name="soul-tether-stage-advance-pending-detail",
    ),
    path(
        "soul-tether/stage-advance/respond/",
        StageAdvanceRespondView.as_view(),
        name="soul-tether-stage-advance-respond",
    ),
    *router.urls,
]
