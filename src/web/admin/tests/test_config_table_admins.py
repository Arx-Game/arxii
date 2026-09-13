"""Admin-page render smoke test for the #3831 config-table admin registrations.

Staff cannot configure a table that has no Django admin page (#3831). Registering
`@admin.register(Model)` is necessary but not sufficient - a `list_display`/
`search_fields` entry that names a field the model doesn't actually have only fails
at RENDER time (Django admin doesn't validate those against the model at import
time the way `ModelAdmin.check()` catches some other mistakes). So this test
doesn't just assert the model is registered - it loads both the changelist and the
add form for every model in `CONFIG_TABLE_MODELS`, which is the only way to catch a
typo'd field name before a staff member does.

`CONFIG_TABLE_MODELS` is a running ledger across #3831's batches - later batches
append their own model names to it rather than writing a parallel test.
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

# Model names registered against #3831 ("config tables the game reads have no
# admin page"). Each entry is a bare model class name; the admin app label for
# every one of these is "arxii" (world/models.py's aggregator, ADR-0195), so the
# changelist/add URLs are always `admin:arxii_<name.lower()>_changelist`/`_add`.
CONFIG_TABLE_MODELS = (
    # world/societies/houses/models.py
    "Title",
    "EdictKind",
    "DomainCrisisType",
    "DomainCrisisTypeOption",
    "StatureBand",
    "PrestigeRankBand",
    "PactKind",
    "NobiliaryParticle",
    "HouseRecognitionRule",
    # world/societies/models.py
    "RenownMagnitudeAward",
    "LegendSettlementConfig",
    "PhilosophicalArchetype",
    "StanceArchetype",
    "PropagandaCampaignTier",
    "RankingDisplay",
    # world/scenes/models.py
    "SceneRoundDefaultsConfig",
    # world/weather/models.py
    "WeatherTransition",
    "WeatherTypeShelter",
    # world/npc_services/models.py
    "NPCRole",
    "NPCServiceOffer",
    "MissionOfferDetails",
    "PermitOfferDetails",
    "LoanOfferDetails",
    "TrainOfferDetails",
    "CourtGrantOfferDetails",
    "StylingOfferDetails",
    "ProfileRecordingOfferDetails",
    "NameCulture",
    "NameCultureEntry",
    "PersonalityTrait",
    "StaffingProfile",
    "StaffingProfileLine",
    "NPCReactionLine",
    "DistinctionRegardSeed",
    "RegardEventConfig",
    # world/predators/models.py
    "PredatorKind",
    # world/progression/models/unlocks.py + models/advancement.py
    "LegendRequirement",
    "DuranceTrainingSite",
    # world/roster/models/families.py
    "UnionKind",
    "Soul",
    "SoulIncarnation",
    # world/magic/models/fury.py
    "FuryTier",
    "FuryConfig",
    # world/magic/models/aura.py
    "AuraAffinityThreshold",
    # world/magic/models/technique_builder.py
    "TechniqueBudgetConfig",
    "TechniqueTierBudget",
    # world/magic/audere_majora.py
    "AudereMajoraThreshold",
    # world/magic/models/anima.py
    "AnimaConfig",
    # world/magic/models/corruption_config.py
    "CorruptionConfig",
    # world/magic/models/affinity.py
    "ResonanceTier",
    # world/magic/models/resonance_environment.py
    "ResonanceAlignmentBoonTier",
    # world/magic/models/grants.py
    "BeginningsRitualGrant",
    "PathRitualGrant",
    "DistinctionRitualGrant",
    "TraditionRitualGrant",
    "CodexEntryRitualGrant",
    "DistinctionResonanceGrant",
    # world/magic/models/liturgy.py
    "RitualLiturgy",
    # world/magic/models/portals.py
    "PortalAnchorKind",
    # world/magic/models/techniques.py
    "TechniqueCapabilityRequirement",
    # world/magic/specialization/models.py
    "TechniqueVariant",
    "TechniqueVariantCapabilityGrant",
    "TechniqueVariantDamageProfile",
    "TechniqueVariantAppliedCondition",
    # world/mechanics/models.py
    "AestheticAxisConfig",
    # world/missions/models.py
    "MissionCategory",
    "MissionAssistPattern",
    "MissionNodeSupportOption",
    "MissionOptionRouteCandidate",
    "MissionTemplate",
    "MissionNode",
    "MissionOption",
    "MissionOptionRoute",
    "MissionOptionOpponentLine",
    "MissionOptionRouteReward",
    "MissionRenownAward",
    "MissionGiver",
)


class ConfigTableAdminPagesTests(TestCase):
    """Every #3831 config table's changelist and add page must render 200."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser(
            "rootadmin3831", "root3831@example.com", "pw-123456"
        )

    def test_changelist_and_add_pages_render(self) -> None:
        self.client.force_login(self.super)
        for name in CONFIG_TABLE_MODELS:
            label = name.lower()
            with self.subTest(model=name):
                changelist_resp = self.client.get(reverse(f"admin:arxii_{label}_changelist"))
                self.assertEqual(
                    changelist_resp.status_code,
                    200,
                    f"{name} changelist did not render: {changelist_resp.status_code}",
                )
                add_resp = self.client.get(reverse(f"admin:arxii_{label}_add"))
                self.assertEqual(
                    add_resp.status_code,
                    200,
                    f"{name} add page did not render: {add_resp.status_code}",
                )
