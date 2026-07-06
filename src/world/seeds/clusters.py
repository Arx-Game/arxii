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
    from world.seeds.game_content.combat import (  # noqa: PLC0415
        seed_encounter_beat_wiring,
        seed_flee_check,
        seed_penetration_contest,
    )

    seed_penetration_contest()
    seed_flee_check()
    seed_encounter_beat_wiring()


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


def _seed_social_actions() -> None:
    from world.seeds.social_actions import seed_social_action_content  # noqa: PLC0415

    seed_social_action_content()


def _seed_consent() -> None:
    from world.seeds.consent import seed_social_consent_categories  # noqa: PLC0415

    seed_social_consent_categories()


def _seed_character_creation() -> None:
    from world.seeds.character_creation import seed_character_creation_dev  # noqa: PLC0415

    seed_character_creation_dev()


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
    # Social actions: authoritative social ActionTemplates + pools + Flirt/Seduce attraction
    # effects. After social_relationships (its conditions) + checks (its CheckTypes) (#1697).
    "social_actions": _seed_social_actions,
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
}


def seeded_models() -> list[type[Model]]:
    """Representative content models per cluster for row-count progress tracking."""
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415

    return [
        Affinity,
        Resonance,
        ItemTemplate,
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
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.relationships.models import RelationshipCondition  # noqa: PLC0415
    from world.room_features.models import RoomFeatureKind  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415
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
        # Social actions seed ActionTemplate rows (#1697).
        "social_actions": [ActionTemplate],
        "magic": [Affinity, Resonance],
        "items": [ItemTemplate],
        # Combat seeds check-types used by the resolution spine, not standalone
        # content rows; it still appears in the inventory as a seeded cluster.
        "combat": [],
        # Battles seeds the ENCOUNTER_COMPLETED trigger wiring, not standalone
        # content rows; it still appears in the inventory as a seeded cluster.
        "battles": [],
        "consent": [SocialConsentCategory],
        "character_creation": [StartingArea, Beginnings, Species],
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
    }
