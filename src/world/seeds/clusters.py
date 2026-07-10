from __future__ import annotations

from collections.abc import Callable

from django.db.models import Model


def _seed_magic() -> None:
    from world.seeds.game_content.magic import seed_magic_dev  # noqa: PLC0415

    seed_magic_dev()


def _seed_items() -> None:
    from world.seeds.game_content.items import seed_items_dev  # noqa: PLC0415

    seed_items_dev()


def _seed_combat() -> None:
    from world.combat.factories import (  # noqa: PLC0415
        wire_elevation_advantage_modifier_target,
    )
    from world.seeds.game_content.combat import (  # noqa: PLC0415
        seed_dramatic_surge_content,
        seed_encounter_beat_wiring,
        seed_flee_check,
        seed_penetration_contest,
    )

    seed_penetration_contest()
    seed_flee_check()
    seed_encounter_beat_wiring()
    seed_dramatic_surge_content()
    wire_elevation_advantage_modifier_target()


def _seed_battles() -> None:
    from world.seeds.game_content.battles import (  # noqa: PLC0415
        seed_champion_duel_outcome_wiring,
    )

    seed_champion_duel_outcome_wiring()


def _seed_checks() -> None:
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415

    seed_check_resolution_tables()


def _seed_combat_checks() -> None:
    from world.seeds.combat_checks import seed_combat_check_content  # noqa: PLC0415

    seed_combat_check_content()


def _seed_social() -> None:
    from world.seeds.social_checks import seed_social_check_content  # noqa: PLC0415

    seed_social_check_content()


def _seed_investigation() -> None:
    from world.seeds.investigation_checks import seed_investigation_check_content  # noqa: PLC0415

    seed_investigation_check_content()


def _seed_social_relationships() -> None:
    from world.seeds.social_relationships import seed_social_relationship_content  # noqa: PLC0415

    seed_social_relationship_content()


def _seed_relationship_scale() -> None:
    from world.seeds.relationship_scale import seed_relationship_scale_content  # noqa: PLC0415

    seed_relationship_scale_content()


def _seed_propaganda() -> None:
    from world.seeds.propaganda import seed_propaganda_content  # noqa: PLC0415

    seed_propaganda_content()


def _seed_social_actions() -> None:
    from world.seeds.social_actions import seed_social_action_content  # noqa: PLC0415

    seed_social_action_content()


def _seed_social_combat() -> None:
    from world.combat.social_combat_content import ensure_social_combat_content  # noqa: PLC0415

    ensure_social_combat_content()


def _seed_consent() -> None:
    from world.seeds.consent import seed_social_consent_categories  # noqa: PLC0415

    seed_social_consent_categories()


def _seed_character_creation() -> None:
    from world.seeds.character_creation import seed_character_creation_dev  # noqa: PLC0415

    seed_character_creation_dev()


def _seed_missions() -> None:
    from world.seeds.game_content.missions import seed_missions_dev  # noqa: PLC0415

    seed_missions_dev()


def _seed_progression() -> None:
    from world.progression.seeds import seed_durance_officiants  # noqa: PLC0415

    seed_durance_officiants()


def _seed_justice() -> None:
    from world.seeds.justice import seed_crime_kinds  # noqa: PLC0415

    seed_crime_kinds()


def _seed_governance() -> None:
    from world.seeds.governance_checks import seed_governance_check_content  # noqa: PLC0415

    seed_governance_check_content()


def _seed_scandal_archetypes() -> None:
    from world.seeds.scandal_archetypes import seed_scandal_archetypes  # noqa: PLC0415

    seed_scandal_archetypes()


def _seed_domain_dev() -> None:
    from world.seeds.domain_dev import ensure_dev_domain  # noqa: PLC0415

    ensure_dev_domain()


def _seed_stealth() -> None:
    from world.seeds.stealth_checks import seed_stealth_check_content  # noqa: PLC0415

    seed_stealth_check_content()


def _seed_perception() -> None:
    from world.seeds.perception_conditions import seed_perception_condition_content  # noqa: PLC0415

    seed_perception_condition_content()


def _seed_civic_hubs() -> None:
    from world.room_features.seeds import (  # noqa: PLC0415
        ensure_notice_board_kind,
        ensure_town_crier_kind,
    )

    ensure_notice_board_kind()
    ensure_town_crier_kind()


def _seed_building_condition() -> None:
    from world.buildings.seeds import ensure_preparation_contribution_method  # noqa: PLC0415

    ensure_preparation_contribution_method()


def _seed_market() -> None:
    from world.seeds.market import seed_market_demo  # noqa: PLC0415

    seed_market_demo()


def _seed_kinship() -> None:
    from world.seeds.kinship import seed_kinship_demo  # noqa: PLC0415

    seed_kinship_demo()


def _seed_houses() -> None:
    from world.seeds.houses import seed_houses_demo  # noqa: PLC0415

    seed_houses_demo()


def _seed_kudos() -> None:
    from world.progression.seeds import seed_kudos_content  # noqa: PLC0415

    seed_kudos_content()


def _seed_gm() -> None:
    from world.gm.factories import (  # noqa: PLC0415
        seed_catalog_starter_content,
        seed_default_gm_level_caps,
    )
    from world.gm.models import GMRewardConfig  # noqa: PLC0415

    seed_default_gm_level_caps()
    # GM scenario catalog: starter SituationKind taxonomy + difficulty guides
    # (#2127) -- Big Button acceptance criterion.
    seed_catalog_starter_content()
    # GM Story Reward config singleton (#2123) — .load() lazily creates the
    # row with its field defaults (the spec's recommended values) if absent.
    GMRewardConfig.load()


def _seed_covenant_roles() -> None:
    from world.seeds.game_content.covenant_roles import (  # noqa: PLC0415
        seed_role_catalog_content,
    )

    seed_role_catalog_content()


def _seed_skills() -> None:
    from world.seeds.game_content.skills import (  # noqa: PLC0415
        seed_skill_breakthrough_catalog,
    )

    seed_skill_breakthrough_catalog()


def _seed_project_resonance() -> None:
    from world.projects.seeds import ensure_project_kind_resonance_awards  # noqa: PLC0415

    ensure_project_kind_resonance_awards()


CLUSTER_SEEDERS: dict[str, Callable[[], None]] = {
    # The checks spine owns the global resolution charts/outcomes; seed it first
    # so the canonical rows exist before the other clusters run. (Idempotency
    # holds regardless of order — magic also ensures the spine itself.)
    "checks": _seed_checks,
    # Combat checks: the Melee Combat skill catalog + weapon-class specializations
    # + the Melee Attack CheckType (stat + skill + spec). After "checks" for the
    # resolution spine; before "social" and "combat" (the penetration/flee retrofits
    # in "combat" depend on the Melee Combat skill existing) (#1706).
    "combat_checks": _seed_combat_checks,
    # Social checks: retrofit the social CheckTypes to stat + skill (+ spec) and seed the
    # Persuasion/Performance skills + their specializations (#1688). After "checks" so the
    # resolution spine exists; authoritative, so it corrects the placeholder stat+stat seed.
    "social": _seed_social,
    # Investigation: the Search check (perception + Investigation) + the Investigation skill.
    # After "checks" for the resolution spine; authoritative (#1705).
    "investigation": _seed_investigation,
    # Social relationships: the allure ModifierTarget + Attracted To / Very Attracted conditions
    # the directed-allure engine reads + Flirt/Seduce effects set (#1697).
    "social_relationships": _seed_social_relationships,
    # Relationship scale: the Regard/Friction system tracks ambient bumps write to,
    # their 25/100/500/2000 tier bands, and the ReactionEmoji catalog (#1699).
    "relationship_scale": _seed_relationship_scale,
    # Social actions: authoritative social ActionTemplates + pools + Flirt/Seduce attraction
    # effects. After social_relationships (its conditions) + checks (its CheckTypes) (#1697).
    "social_actions": _seed_social_actions,
    # Social combat: the rally/demoralize/taunt/parley CheckTypes + Inspired
    # condition + charm technique (#2015). After social_actions (its skills/specs)
    # + magic (the Charmed condition).
    "social_combat": _seed_social_combat,
    "magic": _seed_magic,
    "items": _seed_items,
    "combat": _seed_combat,
    # Battles: the Champion-duel-outcome ENCOUNTER_COMPLETED wiring (#1710). After
    # "combat" — depends on the combat seed cluster's content existing first.
    "battles": _seed_battles,
    # Consent: seeds default SocialConsentCategory rows; tags ActionTemplates if present.
    "consent": _seed_consent,
    # Character-creation "world" content (Realm/StartingArea/Beginnings/Species/
    # Gender/TarotCard/HeightBand/Build/stats/Rosters/Path) — after magic because
    # finalize_character picks the magic-seeded cantrip + resonance. (#1333)
    "character_creation": _seed_character_creation,
    # Missions: the starter notice board (1 BOARD MissionGiver + 3 OPEN
    # MissionTemplate rows) so `mission opportunities` isn't dead-on-arrival on
    # a fresh DB (#2121). After "character_creation" (needs the canonical
    # starting room the board sits in) and "checks"/"combat_checks" (the
    # authored MissionOption's CheckType composition).
    "missions": _seed_missions,
    # Progression: one NPC Durance-training officiant + DuranceTrainingSite per
    # PROSPECT path, at the canonical starting room, so the first-ever Ritual
    # of the Durance is conductible without a live higher-level PC (#2121).
    # After "character_creation" (the room) and "magic" (the Ritual of the
    # Durance row + the 5 PROSPECT Path rows, both seeded by seed_magic_dev).
    "progression": _seed_progression,
    # Justice: the starter CrimeKind vocabulary (#1765). Laws are world data, not seeds.
    "justice": _seed_justice,
    # Governance: Scholarship/Economics + Organization/Stewardship skills and the
    # Tax Collection / Domain Investment checks (#930). After "checks" for the spine.
    "governance": _seed_governance,
    # Dev domain slice: PLACEHOLDER house/streams/steward offers/scandal archetypes
    # so the books + scandal loops are walkable on a dev DB (#930/#1464). After
    # governance (its CheckTypes) and character_creation (the Arx realm).
    # Scandal vocabulary: the nine authored "X Scandal" archetype categories
    # (#1464/#1806 — Apostate, 2026-07-03). Authoritative on vectors.
    "scandal": _seed_scandal_archetypes,
    "domain_dev": _seed_domain_dev,
    # Stealth: the act-time concealment skill + check (#1464). After "checks".
    "stealth": _seed_stealth,
    # Perception: the Concealed condition primitive (#1225) — the seam Stealth
    # witness-reduction (#1464) and forms disguise-piercing will apply/clear.
    "perception": _seed_perception,
    # Civic hubs: the Notice Board / Town Crier RoomFeatureKinds + the crier
    # NPCRole (#1450). Instances (which room carries one) are world data.
    "civic_hubs": _seed_civic_hubs,
    # Building condition: the Grand Preparation AP-check contribution method
    # (#1930). After "governance" (rides its Household Command CheckType).
    "building_condition": _seed_building_condition,
    # Kudos: the KudosSourceCategory rows the pose_kudos / spread_assist / social_engagement
    # reaction-kind + weekly-grant paths need, plus the "relationship_writeup" category and the
    # "xp" KudosClaimCategory the claim UI needs to offer anything (#2026). No dependencies on
    # any other cluster.
    "kudos": _seed_kudos,
    # Market: the PLACEHOLDER capital square + NPC stock stall (#2066).
    "market": _seed_market,
    # Kinship: the PLACEHOLDER ducal demo tree + slots/pool + truth-pair (#2062).
    "kinship": _seed_kinship,
    # Houses: the demo house made a landed peer — org + particle + recognition
    # rules + succession law + fealty + ducal title + domain/holding (#1884).
    # Rides "kinship" (calls its seed first).
    "houses": _seed_houses,
    # GM trust ladder: the 5 default GMLevelCap rows (max_beat_risk,
    # allow_custom_stakes, allow_global_scope_authoring per GMLevel), so a fresh
    # deploy's staff-review gates aren't silently maximally-restrictive (#2000).
    "gm": _seed_gm,
    # Covenant role catalog: granted gifts + techniques + capabilities +
    # archetype action scaling for the 3 canonical roles (#2022). After "items"
    # (creates the role rows + gear compat) and "magic" (EffectType/Style/Gift).
    "covenant_roles": _seed_covenant_roles,
    # Propaganda: PLACEHOLDER campaign-tier catalog for the money→prestige
    # project kind (#1621).
    "propaganda": _seed_propaganda,
    # Skill breakthroughs: default TraitRatingUnlock catalog at every skill's four
    # XP boundaries (20/30/40/50), so the #2115 breakthrough purchase is always
    # reachable instead of a landmine. Registered LAST — it iterates every
    # currently-seeded Skill row, so it must run after every cluster that seeds
    # new skills (combat_checks/social/investigation/governance/stealth); safe to
    # re-run (idempotent) after authoring a skill outside those clusters.
    "skills": _seed_skills,
    # Project-kind resonance payout: the ORGANIZATION_CAPABILITY opt-in row for the
    # PROJECT_CONTRIBUTION GainSource (#2038 — "projects to add gifts to
    # organizations"). No dependencies on any other cluster.
    "project_resonance": _seed_project_resonance,
}


def seeded_models() -> list[type[Model]]:
    """Representative content models per cluster for row-count progress tracking."""
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.items.models import ItemTemplate, Style  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415

    return [
        Affinity,
        Resonance,
        ItemTemplate,
        Style,
        CheckType,
        ResultChart,
        SocialConsentCategory,
        StartingArea,
        Beginnings,
        Species,
        CrimeKind,
    ]


def seeded_models_by_cluster() -> dict[str, list[type[Model]]]:
    """Per-cluster representative content models for the Game Setup inventory.

    A cluster key exists for every registered seeder (so the inventory can
    surface every cluster, even ``combat`` which has no single representative
    content row). Keys are ordered to match :data:`CLUSTER_SEEDERS` insertion
    order so the admin hub lists clusters in their seed sequence.
    """
    from actions.models import ActionTemplate  # noqa: PLC0415
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.gm.models import GMLevelCap, GMRewardConfig, SituationKind  # noqa: PLC0415
    from world.items.market.models import MarketSquare  # noqa: PLC0415
    from world.items.models import ItemTemplate, Style  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance, Ritual  # noqa: PLC0415
    from world.magic.models.techniques import Technique  # noqa: PLC0415
    from world.missions.models import MissionGiver, MissionTemplate  # noqa: PLC0415
    from world.progression.models import (  # noqa: PLC0415
        DuranceTrainingSite,
        KudosSourceCategory,
        TraitRatingUnlock,
    )
    from world.projects.models import (  # noqa: PLC0415
        ContributionMethod,
        ProjectKindResonanceAward,
    )
    from world.relationships.models import RelationshipCondition, RelationshipTier  # noqa: PLC0415
    from world.room_features.models import RoomFeatureKind  # noqa: PLC0415
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.scenes.models import ReactionEmoji  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415
    from world.societies.models import PropagandaCampaignTier  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415

    return {
        "checks": [CheckType, ResultChart],
        # Combat checks: the Melee Combat skill + weapon-class specializations + the
        # Melee Attack CheckType (stat + skill + spec) (#1706). Shared spine/skill rows
        # counted under "checks"; appears as a seeded cluster.
        "combat_checks": [],
        # Social: seeds Persuasion/Performance skills + their specializations + the
        # stat+skill(+spec) social CheckType compositions (#1688).
        "social": [Specialization],
        # Investigation seeds the Search CheckType + Investigation skill (shared spine/skill
        # rows counted under "checks"); it still appears as a seeded cluster (#1705).
        "investigation": [],
        # Social relationships: the allure target + Attracted/Very-Attracted RelationshipConditions
        # (a shared lookup); represented by RelationshipCondition (#1697).
        "social_relationships": [RelationshipCondition],
        # Relationship scale: Regard/Friction system tracks + tier bands + emoji
        # catalog; represented by RelationshipTier and ReactionEmoji (#1699).
        "relationship_scale": [RelationshipTier, ReactionEmoji],
        # Social actions seed ActionTemplate rows (#1697).
        "social_actions": [ActionTemplate],
        # Social combat: 4 CheckTypes + Inspired condition + Charming Word
        # technique (#2015). Represented by Technique (the charm technique).
        "social_combat": [Technique],
        # Ritual counts the covenant/org lifecycle rituals seeded by
        # wire_covenant_lifecycle_rituals() (#2114) alongside Rite of Imbuing/
        # Atonement and the Soul Tether rituals — so operators can see the
        # covenant-lifecycle content landed after the Big Button run.
        "magic": [Affinity, Resonance, Ritual],
        # Style also carries the seeded aesthetic vocabulary spread across the four
        # audacity tiers (#2029).
        "items": [ItemTemplate, Style],
        # Combat seeds check-types used by the resolution spine, not standalone
        # content rows; it still appears in the inventory as a seeded cluster.
        "combat": [],
        # Battles seeds the ENCOUNTER_COMPLETED trigger wiring, not standalone
        # content rows; it still appears in the inventory as a seeded cluster.
        "battles": [],
        "consent": [SocialConsentCategory],
        "character_creation": [StartingArea, Beginnings, Species],
        # Missions: the starter notice board (#2121) — 1 BOARD MissionGiver +
        # 3 OPEN MissionTemplate rows so `mission opportunities` isn't
        # dead-on-arrival.
        "missions": [MissionGiver, MissionTemplate],
        # Progression: one Durance training officiant + site per PROSPECT path
        # (#2121), so the first-ever Ritual of the Durance is conductible.
        "progression": [DuranceTrainingSite],
        # Justice: the starter CrimeKind vocabulary (#1765); AreaLaw rows are world data.
        "justice": [CrimeKind],
        # Governance seeds skills/specs + CheckTypes (shared spine rows counted under
        # "checks"); appears as a seeded cluster with no standalone content model (#930).
        "governance": [],
        # Dev domain slice: PLACEHOLDER house + steward offers (#930/#1464).
        # Scandal vocabulary: the authored archetype categories (#1464/#1806).
        "scandal": [],
        "domain_dev": [],
        # Stealth seeds skill/check rows counted under "checks" (#1464).
        "stealth": [],
        # Perception seeds the Concealed ConditionCategory + ConditionTemplate (#1225).
        "perception": [ConditionTemplate],
        # Civic hubs: the two reader RoomFeatureKinds + the crier NPCRole (#1450).
        "civic_hubs": [RoomFeatureKind],
        # Building condition: the Grand Preparation "Direct the Household"
        # ContributionMethod (#1930).
        "building_condition": [ContributionMethod],
        # Kudos: 4 KudosSourceCategory rows (pose_kudos/spread_assist/social_engagement/
        # relationship_writeup) + the "xp" KudosClaimCategory; represented by
        # KudosSourceCategory (#2026).
        "kudos": [KudosSourceCategory],
        # Market: the PLACEHOLDER capital square (#2066).
        "market": [MarketSquare],
        # GM trust ladder: the 5 default GMLevelCap rows, one per GMLevel (#2000).
        # Also seeds the starter scenario-catalog SituationKind taxonomy + difficulty
        # guides (#2127); represented by SituationKind alongside GMLevelCap.
        # Plus the GM Story Reward config singleton (#2123).
        "gm": [GMLevelCap, GMRewardConfig, SituationKind],
        # Kinship: the PLACEHOLDER ducal demo tree (#2062).
        "kinship": [Kinsperson],
        # Houses: the landed demo house; represented by Title (#1884).
        "houses": [Title],
        # Covenant role catalog: granted gifts + techniques + capabilities +
        # archetype scaling for the 3 canonical roles (#2022).
        "covenant_roles": [],
        # Propaganda: the PLACEHOLDER campaign-tier catalog (#1621).
        "propaganda": [PropagandaCampaignTier],
        # Skill breakthroughs: default TraitRatingUnlock catalog at every skill's
        # four XP boundaries (#2115).
        "skills": [TraitRatingUnlock],
        # Project-kind resonance payout: the ORGANIZATION_CAPABILITY opt-in row
        # (#2038).
        "project_resonance": [ProjectKindResonanceAward],
    }
