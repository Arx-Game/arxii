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
    from world.combat.sent_flying_content import ensure_sent_flying_content  # noqa: PLC0415
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
    # Sent Flying marker content (#2638). Belongs conceptually beside the
    # reactive-challenge content family (interpose/catch/redirect — #2636's
    # "reactive_challenges" cluster) but that cluster is not yet in this
    # branch's ancestry (df34c23cf, #2636, is a main-tip sibling not merged
    # into #2637/#2638's base as of this branch — see the #2638 commit body).
    # Wired here instead, in the existing production "combat" cluster;
    # trivially movable to "reactive_challenges" at the next rebase — both are
    # idempotent get_or_create seeders, so no reconciliation risk either way.
    ensure_sent_flying_content()


def _seed_battles() -> None:
    from world.battles.seeds import (  # noqa: PLC0415
        seed_war_funding_contribution_methods,
    )
    from world.seeds.game_content.battles import (  # noqa: PLC0415
        seed_battle_staging_catalog,
        seed_champion_duel_outcome_wiring,
        seed_place_encounter_outcome_wiring,
    )

    seed_champion_duel_outcome_wiring()
    seed_place_encounter_outcome_wiring()
    # Starter GM battle-staging catalog: 2 BattleMapBlueprint + 3
    # BattleUnitTemplate rows (#2010) — self-contained (get-or-creates its own
    # Property/CapabilityType rows by name), no ordering dependency on another
    # cluster.
    seed_battle_staging_catalog()
    # WAR_FUNDING check-based contribution methods (#2382).
    seed_war_funding_contribution_methods()


def _seed_reactive_challenges() -> None:
    from world.areas.positioning.plummet_content import ensure_fall_content  # noqa: PLC0415
    from world.combat.interpose_content import ensure_interpose_content  # noqa: PLC0415
    from world.combat.redirect_content import ensure_redirect_content  # noqa: PLC0415
    from world.combat.succor_content import ensure_succor_content  # noqa: PLC0415

    # Interpose first: it creates the four shared guardian CapabilityType rows
    # (telekinesis/shield/barrier/pull_aside) that Succor reuses, and looks up
    # the Melee Defense CheckType seeded by the "combat_checks" cluster.
    ensure_interpose_content()
    ensure_succor_content()
    # Fall content also seeds the Catch-the-Faller challenge (shares the
    # Reflexes catch CheckType with Interpose).
    ensure_fall_content()
    ensure_redirect_content()


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


def _seed_worship() -> None:
    from world.seeds.worship_content import seed_worship_content  # noqa: PLC0415

    seed_worship_content()


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


def _seed_tutorial() -> None:
    from world.seeds.game_content.tutorial import seed_tutorial_dev  # noqa: PLC0415

    seed_tutorial_dev()


def _seed_progression() -> None:
    from world.progression.seeds import (  # noqa: PLC0415
        seed_durance_officiants,
        seed_major_gift_technique_level_requirement,
    )

    seed_durance_officiants()
    seed_major_gift_technique_level_requirement()


def _seed_npc_services() -> None:
    from world.npc_services.seeds import (  # noqa: PLC0415
        ensure_academy_generalist_trainer_role,
        ensure_academy_registrar_role,
        ensure_great_archive_librarian_role,
    )
    from world.seeds.styling import seed_styling_content  # noqa: PLC0415

    ensure_great_archive_librarian_role()
    # #2428 whole-branch fix: the Registrar (settle the entrance debt) and an
    # ungated generalist trainer close the fresh-DB training loop end to end —
    # see world.npc_services.seeds for why both are needed alongside the
    # achievement-gated Great Archive self-study seed above.
    ensure_academy_registrar_role()
    ensure_academy_generalist_trainer_role()
    # #2632 — stylist + Archive profile scribe roles, cosmetic item templates.
    # Depends on the character_creation appearance traits (skips gracefully
    # when absent).
    seed_styling_content()


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


def _seed_security() -> None:
    from world.seeds.security_checks import seed_security_check_content  # noqa: PLC0415

    seed_security_check_content()


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


def _seed_counterplay() -> None:
    from world.room_features.seeds import ensure_workshop_of_iniquity_kind  # noqa: PLC0415
    from world.seeds.justice import ensure_frame_job_contribution_method  # noqa: PLC0415

    ensure_workshop_of_iniquity_kind()
    ensure_frame_job_contribution_method()


def _seed_building_condition() -> None:
    from world.buildings.seeds import ensure_preparation_contribution_method  # noqa: PLC0415

    ensure_preparation_contribution_method()


def _seed_property_grants() -> None:
    from world.buildings.seeds import ensure_placeholder_property_grant_profile  # noqa: PLC0415

    ensure_placeholder_property_grant_profile()


def _seed_agriculture() -> None:
    from world.agriculture.seeds import (  # noqa: PLC0415
        ensure_field_granary_kinds,
        ensure_starter_crop_types,
    )

    ensure_field_granary_kinds()
    ensure_starter_crop_types()


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


def _seed_survivability() -> None:
    from world.vitals.seeds import seed_survivability_content  # noqa: PLC0415

    seed_survivability_content()


def _seed_ceremonies() -> None:
    from world.ceremonies.seeds import seed_ceremony_types  # noqa: PLC0415

    seed_ceremony_types()


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


def _seed_roster() -> None:
    from world.roster.seeds import seed_invite_trust_category  # noqa: PLC0415

    seed_invite_trust_category()


def _seed_traits() -> None:
    """No-op cluster (#2266): Trait rows are created by other clusters already —

    ``character_creation`` seeds the 12 core stat Traits; the checks-family
    clusters (``combat_checks``/``social``/``investigation``/``governance``/
    ``stealth``/``security``) seed skill Traits alongside their CheckTypes.
    Registered purely so the Game Setup inventory can show a Trait row count:
    the #944 Phase-1 content-pipeline domain (``stats/``/``skills/`` via
    ``core_management.content_fixtures``) had no inventory visibility at all
    until this cluster existed, even though the rows themselves were always
    seeded.
    """


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
    # Worship: the Rites skill + tradition specializations, the Ceremony Rites CheckType
    # (+ Devotion aspect for Path of the Chosen), God's Favorite achievements, and
    # PLACEHOLDER traditions/beings (#2355). After "social" so the check spine + social
    # category exist.
    "worship": _seed_worship,
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
    # Reactive challenges (#2636): the declared-guardian / environmental-rescue
    # content family — Interpose, Succor, fall/Plummeting + Catch the Faller,
    # and the redirect detonation example Property. Built for #1273/#1744/#1228/
    # #2210 but previously staff/test-invoked only; wiring it here makes
    # declared interpose, succor, and the reactive catch live in real play
    # (covenant-vow reactive grammar, gap G1). After "combat_checks" (Interpose
    # looks up its Melee Defense CheckType) and "combat" (same family of
    # resolution content); all four seeds are get_or_create-idempotent.
    "reactive_challenges": _seed_reactive_challenges,
    # Consent: seeds default SocialConsentCategory rows; tags ActionTemplates if present.
    "consent": _seed_consent,
    # Character-creation "world" content (Realm/StartingArea/Beginnings/Species/
    # Gender/TarotCard/HeightBand/Build/stats/Rosters/Path) — after magic because
    # finalize_character picks the magic-seeded catalog Gift/Technique + resonance
    # (#2426; the pre-#2426 starter-catalog model was retired in Task 8, #1333).
    "character_creation": _seed_character_creation,
    # Missions: the starter notice board (1 BOARD MissionGiver + 3 OPEN
    # MissionTemplate rows) so `mission opportunities` isn't dead-on-arrival on
    # a fresh DB (#2121). After "character_creation" (needs the canonical
    # starting room the board sits in) and "checks"/"combat_checks" (the
    # authored MissionOption's CheckType composition).
    "missions": _seed_missions,
    # Tutorial chain (#1035): seven-template new-player arc. After "missions"
    # (board object + fieldwork check), "character_creation" (starting room),
    # and self-contained for the tutor NPCRole (no other cluster's content is
    # required to create it).
    "tutorial": _seed_tutorial,
    # Progression: one NPC Durance-training officiant + DuranceTrainingSite per
    # PROSPECT path, at the canonical starting room, so the first-ever Ritual
    # of the Durance is conductible without a live higher-level PC (#2121).
    # After "character_creation" (the room) and "magic" (the Ritual of the
    # Durance row). The PROSPECT Path rows themselves are real lore-repo
    # content, loaded via load_world_content() ahead of every cluster (#2474)
    # — no longer seeded here by seed_magic_dev().
    "progression": _seed_progression,
    # NPC services: the Great Archive Librarian role + self-study TRAIN offers
    # (#2440 ruling 5), gated by a PLACEHOLDER quest-completion Achievement.
    # After "progression" (itself after "character_creation" for the
    # Shroudwatch Academy org). The starter Gift/Technique catalog the
    # self-study offers reference is real lore-repo content, loaded via
    # load_world_content() before any cluster runs (#2474) — not seeded by
    # the "magic" cluster.
    "npc_services": _seed_npc_services,
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
    # Security: Skulduggery(né Larceny)/Athletics skills + lockpick/break/escape/guard-detection
    # CheckTypes (#2180). After "stealth" (reuses its Stealth skill for SNEAK)
    # and "investigation" (reuses its Investigation skill for Guard Detection).
    "security": _seed_security,
    # Perception: the Concealed condition primitive (#1225) — the seam Stealth
    # witness-reduction (#1464) and forms disguise-piercing will apply/clear.
    "perception": _seed_perception,
    # Civic hubs: the Notice Board / Town Crier RoomFeatureKinds + the crier
    # NPCRole (#1450). Instances (which room carries one) are world data.
    "civic_hubs": _seed_civic_hubs,
    # Counter-play (#1825): the Workshop of Iniquity RoomFeatureKind + the
    # frame-job Forgery contribution method. After "security" (rides its
    # Forge Evidence CheckType) and "justice" (crime kinds).
    "counterplay": _seed_counterplay,
    # Building condition: the Grand Preparation AP-check contribution method
    # (#1930). After "governance" (rides its Household Command CheckType).
    "building_condition": _seed_building_condition,
    # Property grants: a generic placeholder PropertyGrantProfile so
    # grant_property_house is exercisable on a fresh dev DB before any real
    # fixture content wires a Beginnings row at a PropertyGrantProfile.
    "property_grants": _seed_property_grants,
    "agriculture": _seed_agriculture,
    # Kudos: the KudosSourceCategory rows the pose_kudos / spread_assist / social_engagement
    # reaction-kind + weekly-grant paths need, plus the "relationship_writeup" category and the
    # "xp" KudosClaimCategory the claim UI needs to offer anything (#2026). No dependencies on
    # any other cluster.
    "kudos": _seed_kudos,
    # Survivability: the knockout/default-death/default-wound pools + Bleeding
    # Out staged condition + Unconscious capability zeroing + foundational
    # CapabilityTypes + the liminal dream room + the death KudosSourceCategory
    # (#2287). Without this cluster the damage pipeline never KOs or kills.
    # After "kudos" (shares the KudosSourceCategory model) and "checks" (the
    # outcome spine); both idempotent either way.
    "survivability": _seed_survivability,
    # Ceremony types: Funeral/Blessing/Sermon/Seance CeremonyType rows (#2289/#2393).
    # Without this cluster, opening ANY ceremony fails with "not recognized" on a
    # fresh database — no other seed or migration ever creates these rows.
    "ceremonies": _seed_ceremonies,
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
    # Roster: the INVITE TrustCategory for game-invite eligibility (#2483).
    # No dependencies on any other cluster.
    "roster": _seed_roster,
    # Traits: no-op — see _seed_traits docstring. Registered so the Game Setup
    # inventory can show a Trait row count for the #944 content-pipeline domain,
    # which had zero inventory visibility before #2266.
    "traits": _seed_traits,
}


def seeded_models() -> list[type[Model]]:
    """Representative content models per cluster for row-count progress tracking."""
    from world.agriculture.models import CropType  # noqa: PLC0415
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
        CropType,
    ]


def seeded_models_by_cluster() -> dict[str, list[type[Model]]]:
    """Per-cluster representative content models for the Game Setup inventory.

    A cluster key exists for every registered seeder (so the inventory can
    surface every cluster, even ``combat`` which has no single representative
    content row). Keys are ordered to match :data:`CLUSTER_SEEDERS` insertion
    order so the admin hub lists clusters in their seed sequence.
    """
    from actions.models import ActionTemplate, ConsequencePool  # noqa: PLC0415
    from world.agriculture.models import CropType  # noqa: PLC0415
    from world.battles.models import BattleMapBlueprint, BattleUnitTemplate  # noqa: PLC0415
    from world.buildings.models import (  # noqa: PLC0415
        BuildingKind,
        DecorationKind,
        PropertyGrantProfile,
    )
    from world.ceremonies.models import CeremonyType  # noqa: PLC0415
    from world.character_creation.models import (  # noqa: PLC0415
        Beginnings,
        CGExplanation,
        StartingArea,
    )
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.gm.models import GMLevelCap, GMRewardConfig, SituationKind  # noqa: PLC0415
    from world.items.market.models import MarketSquare  # noqa: PLC0415
    from world.items.models import ItemTemplate, Style  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance, Ritual  # noqa: PLC0415
    from world.magic.models.techniques import Technique  # noqa: PLC0415
    from world.mechanics.models import ChallengeTemplate  # noqa: PLC0415
    from world.missions.models import MissionGiver, MissionTemplate  # noqa: PLC0415
    from world.npc_services.models import NPCRole  # noqa: PLC0415
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
    from world.roster.models import GameInvite, Kinsperson  # noqa: PLC0415
    from world.scenes.models import ReactionEmoji  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415
    from world.societies.models import PropagandaCampaignTier  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.traits.models import ResultChart, Trait  # noqa: PLC0415
    from world.worship.models import WorshippedBeing, WorshipTradition  # noqa: PLC0415

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
        # Worship: traditions + worshippable beings (Rites skill/specs ride the shared
        # skills tables); represented by WorshipTradition and WorshippedBeing (#2355).
        "worship": [WorshipTradition, WorshippedBeing],
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
        # audacity tiers (#2029). BuildingKind/DecorationKind (#2266) — no cluster
        # seeds these via the Big Button today (they're staff/content authored,
        # e.g. `world.buildings.seeds.ensure_urban_building_kinds`); tracked here
        # so a content load against them is inventory-visible.
        "items": [ItemTemplate, Style, BuildingKind, DecorationKind],
        # Combat seeds check-types used by the resolution spine, not standalone
        # content rows; it still appears in the inventory as a seeded cluster.
        "combat": [],
        # Battles seeds the ENCOUNTER_COMPLETED trigger wiring plus the starter
        # GM battle-staging catalog: 2 BattleMapBlueprint + 3 BattleUnitTemplate
        # rows (#2010).
        "battles": [BattleMapBlueprint, BattleUnitTemplate],
        # Reactive challenges: Interpose/Succor/Catch-the-Faller ChallengeTemplates
        # + the Plummeting marker condition + the redirect detonation Property
        # (#2636 — activates the #1273/#1744/#1228/#2210 content family).
        "reactive_challenges": [ChallengeTemplate],
        "consent": [SocialConsentCategory],
        "character_creation": [StartingArea, Beginnings, Species, CGExplanation],
        # Missions: the starter notice board (#2121) — 1 BOARD MissionGiver +
        # 3 OPEN MissionTemplate rows so `mission opportunities` isn't
        # dead-on-arrival.
        "missions": [MissionGiver, MissionTemplate],
        # Tutorial chain: seven-template T1-T7 new-player arc (#1035) — trigger/
        # environmental discovery, an NPC-carried external-act beat, a board job
        # that summons the next step, and the durable external-act beats ending
        # in the first legend-risk mission. Represented by NPCRole (the tutor).
        "tutorial": [NPCRole],
        # Progression: one Durance training officiant + site per PROSPECT path
        # (#2121), so the first-ever Ritual of the Durance is conductible. Also
        # seeds the level-2 ClassLevelUnlock + MajorGiftTechniqueRequirement gate
        # (#2440 ruling 4) — no standalone representative model (rides the
        # existing ClassLevelUnlock/requirement tables).
        "progression": [DuranceTrainingSite],
        # NPC services: the Great Archive Librarian role + self-study TRAIN offers
        # (#2440 ruling 5), the Academy Registrar's SETTLE_OBLIGATION offer, and an
        # ungated Academy generalist trainer (both #2428 whole-branch fix — the
        # live caller for settle_obligation and the fresh-DB-completable training
        # loop), represented by NPCRole (mirrors "tutorial" above).
        "npc_services": [NPCRole],
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
        # Security seeds skill/check rows counted under "checks" (#2180).
        "security": [],
        # Perception seeds the Concealed ConditionCategory + ConditionTemplate (#1225).
        "perception": [ConditionTemplate],
        # Civic hubs: the two reader RoomFeatureKinds + the crier NPCRole (#1450).
        "civic_hubs": [RoomFeatureKind],
        # Counter-play: the Workshop of Iniquity kind + the frame-job
        # ContributionMethod (#1825); represented by ContributionMethod.
        "counterplay": [ContributionMethod],
        # Building condition: the Grand Preparation "Direct the Household"
        # ContributionMethod (#1930).
        "building_condition": [ContributionMethod],
        # Property grants: a generic placeholder PropertyGrantProfile so
        # grant_property_house is exercisable on a fresh dev DB before any
        # real fixture content wires a Beginnings row at one.
        "property_grants": [PropertyGrantProfile],
        # Kudos: 4 KudosSourceCategory rows (pose_kudos/spread_assist/social_engagement/
        # relationship_writeup) + the "xp" KudosClaimCategory; represented by
        # KudosSourceCategory (#2026).
        "kudos": [KudosSourceCategory],
        # Survivability: knockout/default-death/default-wound pools + Bleeding Out
        # staged condition + foundational CapabilityTypes + dream room (#2287).
        # Represented by ConsequencePool (the tier pools).
        "survivability": [ConsequencePool],
        # Ceremony types: the four authored CeremonyType rows (#2289/#2393).
        "ceremonies": [CeremonyType],
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
        # Roster: the INVITE TrustCategory for game-invite eligibility (#2483).
        "roster": [GameInvite],
        # Agriculture: Field + Granary RoomFeatureKinds + starter CropTypes (#1864).
        "agriculture": [CropType, RoomFeatureKind],
        # Traits: no-op seeder — see _seed_traits (#2266). Row count for the #944
        # content-pipeline domain (stats/skills), previously invisible in this hub.
        "traits": [Trait],
    }
