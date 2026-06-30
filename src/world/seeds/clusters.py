from __future__ import annotations

from collections.abc import Callable

from django.db.models import Model


def _seed_magic() -> None:
    from integration_tests.game_content.magic import seed_magic_dev  # noqa: PLC0415

    seed_magic_dev()


def _seed_items() -> None:
    from integration_tests.game_content.items import seed_items_dev  # noqa: PLC0415

    seed_items_dev()


def _seed_combat() -> None:
    from integration_tests.game_content.combat import (  # noqa: PLC0415
        seed_flee_check,
        seed_penetration_contest,
    )

    seed_penetration_contest()
    seed_flee_check()


def _seed_checks() -> None:
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415

    seed_check_resolution_tables()


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


CLUSTER_SEEDERS: dict[str, Callable[[], None]] = {
    # The checks spine owns the global resolution charts/outcomes; seed it first
    # so the canonical rows exist before the other clusters run. (Idempotency
    # holds regardless of order — magic also ensures the spine itself.)
    "checks": _seed_checks,
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
    # Consent: seeds default SocialConsentCategory rows; tags ActionTemplates if present.
    "consent": _seed_consent,
    # Character-creation "world" content (Realm/StartingArea/Beginnings/Species/
    # Gender/TarotCard/HeightBand/Build/stats/Rosters/Path) — after magic because
    # finalize_character picks the magic-seeded cantrip + resonance. (#1333)
    "character_creation": _seed_character_creation,
}


def seeded_models() -> list[type[Model]]:
    """Representative content models per cluster for row-count progress tracking."""
    from world.character_creation.models import Beginnings, StartingArea  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
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
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.magic.models import Affinity, Resonance  # noqa: PLC0415
    from world.relationships.models import RelationshipCondition  # noqa: PLC0415
    from world.skills.models import Specialization  # noqa: PLC0415
    from world.species.models import Species  # noqa: PLC0415
    from world.traits.models import ResultChart  # noqa: PLC0415

    return {
        "checks": [CheckType, ResultChart],
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
        "consent": [SocialConsentCategory],
        "character_creation": [StartingArea, Beginnings, Species],
    }
