"""Magic test-infrastructure: seed helpers and MagicContent.

Exports:
- ``seed_magic_dev()`` — master orchestrator for the entire magic cluster.
  Composes all Phase 1 seed helpers into a single idempotent call. This is
  the magic-cluster contribution to Phase 3's ``seed_dev_database()``.
- ``seed_magic_config()`` — Task 1.1 — singletons + IntensityTier + MishapPoolTier
- ``seed_canonical_rituals()`` — Task 1.2 — Rite of Imbuing + Rite of Atonement +
  Ritual of the Durance (#2121)
- ``seed_thread_pull_catalog()`` — Task 1.3 — ThreadPullCost + ThreadPullEffect catalog
- ``MagicContent`` — static factory helpers for integration-test technique wiring

Note: the starter Gift/Technique/PathGiftGrant/Tradition catalog formerly seeded
here by ``seed_starter_gift_catalog()`` is retired (#2474) — that catalog is now
real lore-repo content, loaded via ``load_world_content()``. Consumers
(``world.npc_services.seeds``'s Academy trainer roles) read the loaded catalog
via ORM lookups (``Gift.objects`` / ``Technique.objects`` /
``PathGiftGrant.objects`` / ``Tradition.objects``) and log a loud warning
pointing at the content repo / Big Button when it's absent — never falling
back to seeding a synthetic arxii-resident catalog. A hard raise isn't used
here: this lookup runs inside ``seed_dev_database()``'s cluster loop alongside
many unrelated clusters, and every existing content-repo-less test in the repo
would otherwise abort the entire Big Button run over this one seed's slice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from world.magic.seeds_checks import MagicCheckContentResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from actions.models.action_templates import ActionTemplate
    from actions.models.consequence_pools import ConsequencePool
    from world.classes.models import Path
    from world.conditions.models import CapabilityType, ConditionStage
    from world.magic.audere import AudereThreshold
    from world.magic.models import (
        Affinity,
        AnimaConfig,
        Gift,
        IntensityTier,
        MagicalAlterationTemplate,
        MishapPoolTier,
        PortalAnchorKind,
        Resonance,
        Ritual,
        SoulfrayConfig,
        Technique,
        TechniqueCapabilityGrant,
        Tradition,
    )
    from world.magic.models.corruption_config import CorruptionConfig
    from world.magic.models.gain_config import ResonanceGainConfig
    from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant
    from world.magic.models.threads import ThreadPullCost, ThreadPullEffect
    from world.magic.models.weaving import ThreadWeavingUnlock
    from world.mechanics.models import Property
    from world.relationships.models import RelationshipTrack
    from world.seeds.game_content.combat import FleeSeedResult, PenetrationContestResult

# Maps action_key → technique name (narrative, not mechanical)
ACTION_TECHNIQUE_MAP: dict[str, str] = {
    "intimidate": "Soul Crush",
    "persuade": "Silver Tongue",
    "deceive": "Veil of Lies",
    "flirt": "Heartstring Pull",
    "perform": "Echoing Song",
    "entrance": "Commanding Presence",
}

# Evennia typeclass path repeated across room lookups; centralized for dedup.
_ROOM_MODEL = "typeclasses.rooms.Room"

_ELEMENTAL_TECHNIQUES: list[tuple[str, list[str], str]] = [
    ("Flame Lance", ["generation", "force", "projection"], "Fire"),
    ("Shadow Step", ["traversal", "perception"], "Shadow"),
    ("Stone Ward", ["barrier", "force"], "Earth"),
    ("Gale Burst", ["manipulation", "projection"], "Air"),
]

_SOCIAL_TECHNIQUE_CAPABILITIES: dict[str, list[str]] = {
    "Soul Crush": ["intimidation", "charm"],
    "Silver Tongue": ["persuasion", "deception"],
    "Veil of Lies": ["deception", "charm"],
    "Heartstring Pull": ["charm", "persuasion"],
    "Echoing Song": ["inspiration", "charm"],
    "Commanding Presence": ["intimidation", "inspiration"],
}

_EFFECT_PROPERTY_DEFINITIONS: list[tuple[str, str]] = [
    ("fire", "Effect carries fire energy"),
    ("shadow", "Effect carries shadow energy"),
    ("earth", "Effect carries earth energy"),
    ("air", "Effect carries air energy"),
]

# Outcome-tier labels and content names reused across seed rows (S1192).
_CRITICAL_SUCCESS = "Critical Success"
_CRITICAL_FAILURE = "Critical Failure"
_PARTIAL_SUCCESS = "Partial Success"
_TEMPERED_AGAINST_LIGHT = "Tempered Against Light"
_HALLOWED_BURN = "Hallowed Burn"
_MARKED_PATH = "Marked Path"
_WEAPON_ENHANCEMENT = "Weapon Enhancement"
_RANGED_ATTACK = "Ranged Attack"


@dataclass
class MagicContentResult:
    """Returned by MagicContent.create_all()."""

    techniques: dict[str, Technique]  # action_key → Technique
    enhancements: dict[str, ActionEnhancement]  # action_key → ActionEnhancement
    elemental_techniques: dict[str, Technique] = field(default_factory=dict)
    capability_grants: list[TechniqueCapabilityGrant] = field(default_factory=list)


@dataclass
class AlterationContentResult:
    """Returned by MagicContent.create_alteration_content()."""

    tier1_entry: MagicalAlterationTemplate  # AlterationTier.COSMETIC_TOUCH
    tier2_entry: MagicalAlterationTemplate  # AlterationTier.MARKED
    tier3_entry: MagicalAlterationTemplate  # AlterationTier.TOUCHED
    affinity: Affinity
    resonance: Resonance
    soulfray_consequence_pool: ConsequencePool  # pool with MAGICAL_SCARS entry
    soulfray_stage: ConditionStage  # stage whose consequence_pool fires MAGICAL_SCARS


@dataclass
class StarterCatalogFixtureResult:
    """Returned by MagicContent.create_starter_gift_catalog() (test-only, #2474).

    Synthetic stand-in for the retired ``seed_starter_gift_catalog()`` (#2426)
    — arxii holds no catalog content (that is real lore-repo content, loaded
    via ``load_world_content()``); this builds an equivalent-shaped fixture via
    factories for tests exercising CG / NPC-trainer code paths that read the
    loaded catalog through the ORM (``Gift.objects`` / ``Technique.objects`` /
    ``PathGiftGrant.objects`` / ``TraditionGiftGrant.objects``) on a
    content-repo-less test database.
    """

    tradition: Tradition
    paths: dict[str, Path]  # path_name → Path
    gifts: dict[str, Gift]  # path_name → Gift (one MAJOR gift per path)
    techniques: dict[str, Technique]  # technique_name → Technique
    path_gift_grants: dict[str, PathGiftGrant]  # path_name → PathGiftGrant
    tradition_gift_grants: dict[str, TraditionGiftGrant]  # path_name → TraditionGiftGrant


class MagicContent:
    """Creates techniques and ActionEnhancement records for social action integration tests."""

    @staticmethod
    def create_starter_gift_catalog(
        specs: list[tuple[str, str, str]],
        *,
        tradition_name: str = "Unbound",
    ) -> StarterCatalogFixtureResult:
        """Factory-build a synthetic starter Gift/Technique/PathGiftGrant/Tradition pool.

        Test-only replacement for the retired ``seed_starter_gift_catalog()``
        (#2474) — see ``StarterCatalogFixtureResult``. Builds one PROSPECT
        ``Path`` + MAJOR ``Gift`` + ``Technique`` + ``PathGiftGrant`` per
        ``(path_name, gift_name, technique_name)`` triple in ``specs``, plus a
        shared ``Tradition`` (get_or_create by name — defaults to "Unbound" so
        tests can look it up the same way production code does) with a
        ``TraditionGiftGrant`` for every Gift created.

        Args:
            specs: one ``(path_name, gift_name, technique_name)`` triple per
                (Path, Gift) pair to create. Each Gift gets exactly one
                Technique (set as that Gift's sole ``starter_techniques``
                entry) — callers needing more than one Technique per Gift
                should call ``TechniqueFactory`` directly for the extras.
            tradition_name: ``Tradition.name`` to get-or-create.

        Returns:
            StarterCatalogFixtureResult keyed by ``path_name`` throughout
            (except ``techniques``, keyed by ``technique_name``).
        """
        from world.classes.factories import PathFactory  # noqa: PLC0415
        from world.magic.factories import (  # noqa: PLC0415
            GiftFactory,
            PathGiftGrantFactory,
            TechniqueFactory,
            TraditionFactory,
            TraditionGiftGrantFactory,
        )

        tradition = TraditionFactory(name=tradition_name)

        paths: dict[str, Path] = {}
        gifts: dict[str, Gift] = {}
        techniques: dict[str, Technique] = {}
        path_gift_grants: dict[str, PathGiftGrant] = {}
        tradition_gift_grants: dict[str, TraditionGiftGrant] = {}
        for path_name, gift_name, technique_name in specs:
            path = PathFactory(name=path_name)
            gift = GiftFactory(name=gift_name)
            technique = TechniqueFactory(name=technique_name, gift=gift)
            grant = PathGiftGrantFactory(path=path, gift=gift)
            grant.starter_techniques.set([technique])
            tradition_grant = TraditionGiftGrantFactory(tradition=tradition, gift=gift)

            paths[path_name] = path
            gifts[path_name] = gift
            techniques[technique_name] = technique
            path_gift_grants[path_name] = grant
            tradition_gift_grants[path_name] = tradition_grant

        return StarterCatalogFixtureResult(
            tradition=tradition,
            paths=paths,
            gifts=gifts,
            techniques=techniques,
            path_gift_grants=path_gift_grants,
            tradition_gift_grants=tradition_gift_grants,
        )

    @staticmethod
    def seed_magic_checks() -> MagicCheckContentResult:
        """Seed #709 magical check content (skills + CheckTypes + ritual configs)."""
        from world.magic.seeds_checks import ensure_magic_check_content  # noqa: PLC0415
        from world.magic.seeds_sanctum import ensure_sanctum_rituals  # noqa: PLC0415

        ensure_sanctum_rituals()
        return ensure_magic_check_content()

    @staticmethod
    def create_all() -> MagicContentResult:
        """Create 6 techniques and 6 ActionEnhancement records (one per social action).

        Techniques use intensity=2, control=2, anima_cost=12.
        The social safety bonus adds +10 control for unengaged characters, giving
        control_delta=10 and effective_cost = max(12 - 10, 0) = 2 per use.

        Idempotent: uses get_or_create on technique name and on
        (base_action_key, technique) for enhancements, so calling this method
        twice produces exactly 6 techniques and 6 enhancements.

        Safe to call from setUpTestData across multiple test classes.

        Returns:
            MagicContentResult with techniques and enhancements dicts.
        """
        from actions.constants import EnhancementSourceType  # noqa: PLC0415
        from actions.models import ActionEnhancement  # noqa: PLC0415
        from world.magic.factories import (  # noqa: PLC0415
            AffinityFactory,
            GiftFactory,
            ResonanceFactory,
        )
        from world.magic.models import EffectType, Technique, TechniqueStyle  # noqa: PLC0415
        from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

        gift = GiftFactory(name="Social Arts")

        # Wire one resonance into the Social Arts supported set so gift-thread
        # variants can be authored against it (#1581).  Uses get_or_create on both
        # the affinity and the resonance so repeated calls are a no-op.
        social_affinity = AffinityFactory(name="Social")
        social_resonance = ResonanceFactory(name="Social Influence", affinity=social_affinity)
        gift.resonances.add(social_resonance)

        # Ensure a minimal style and effect_type exist for social techniques.
        # get_or_create so re-runs don't create duplicates.
        style, _ = TechniqueStyle.objects.get_or_create(
            name="Social",
            defaults={"description": "Magic expressed through social interaction."},
        )
        effect_type, _ = EffectType.objects.get_or_create(
            name="Social Influence",
            defaults={
                "description": "Magical enhancement of social action.",
                "base_power": None,
                "base_anima_cost": 2,
                "has_power_scaling": False,
            },
        )

        techniques: dict[str, Technique] = {}
        enhancements: dict[str, ActionEnhancement] = {}

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            technique, _ = Technique.objects.get_or_create(
                name=technique_name,
                defaults={
                    "gift": gift,
                    "style": style,
                    "effect_type": effect_type,
                    "intensity": 2,
                    "control": 2,
                    "anima_cost": 12,
                    "description": f"Social magic technique: {technique_name}.",
                },
            )
            techniques[action_key] = technique

            variant_name = f"Magical {action_key.title()}"
            enhancement, _ = ActionEnhancement.objects.get_or_create(
                base_action_key=action_key,
                technique=technique,
                defaults={
                    "variant_name": variant_name,
                    "is_involuntary": False,
                    "source_type": EnhancementSourceType.TECHNIQUE,
                    "distinction": None,
                    "condition": None,
                },
            )
            enhancements[action_key] = enhancement

        # #1581: author a resonance-specific variant per gift technique so deepening
        # the gift-thread to level 3 surfaces a discoverable, slightly-stronger
        # renamed form.  Keyed on the unique triple (parent_technique, resonance,
        # unlock_thread_level); get_or_create makes repeated calls a no-op.
        seeded_gift_techniques = list(techniques.values())
        for technique in seeded_gift_techniques:
            resonance = technique.gift.resonances.first()
            if resonance is None:
                continue
            TechniqueVariant.objects.get_or_create(
                parent_technique=technique,
                resonance=resonance,
                unlock_thread_level=3,
                defaults={
                    "name_override": f"{resonance.name} {technique.name}",
                    "intensity_delta": 2,
                    "control_delta": 1,
                },
            )

        return MagicContentResult(techniques=techniques, enhancements=enhancements)

    @staticmethod
    def grant_techniques_to_character(
        character: ObjectDB,
        techniques: list[Technique],
    ) -> None:
        """Create CharacterTechnique records so the character knows each technique.

        Args:
            character: The ObjectDB character (must have a CharacterSheet already created).
            techniques: Techniques to grant. Duplicate grants are ignored (get_or_create).
        """
        from world.magic.factories import CharacterTechniqueFactory  # noqa: PLC0415

        sheet = character.sheet_data
        for technique in techniques:
            CharacterTechniqueFactory(character=sheet, technique=technique)

    @staticmethod
    def create_elemental_techniques(
        capability_types: dict[str, CapabilityType],
    ) -> tuple[dict[str, Technique], list[TechniqueCapabilityGrant]]:
        """Create 4 elemental techniques with capability grants and effect properties.

        Builds the full Resonance → Gift → Technique → TechniqueCapabilityGrant chain,
        plus a PropertyCategory "Effect" with 4 effect Properties wired via Resonance M2M.

        Args:
            capability_types: name → CapabilityType lookup (must contain all capabilities
                referenced in ``_ELEMENTAL_TECHNIQUES``).

        Returns:
            Tuple of (name → Technique dict, list of all TechniqueCapabilityGrants).
        """
        from world.magic.factories import (  # noqa: PLC0415
            AffinityFactory,
            GiftFactory,
            ResonanceFactory,
            TechniqueCapabilityGrantFactory,
            TechniqueFactory,
        )
        from world.mechanics.factories import (  # noqa: PLC0415
            PropertyCategoryFactory,
            PropertyFactory,
        )

        # Effect properties
        effect_category = PropertyCategoryFactory(name="Effect")
        effect_properties: dict[str, Property] = {}
        for prop_name, prop_desc in _EFFECT_PROPERTY_DEFINITIONS:
            effect_properties[prop_name] = PropertyFactory(
                name=prop_name,
                description=prop_desc,
                category=effect_category,
            )

        # Resonances (one per element, all sharing "Primal" affinity)
        affinity = AffinityFactory(name="Primal")
        resonances: dict[str, object] = {}
        element_names = ["Fire", "Shadow", "Earth", "Air"]
        element_prop_keys = ["fire", "shadow", "earth", "air"]
        for elem_name, prop_key in zip(element_names, element_prop_keys, strict=True):
            resonances[elem_name] = ResonanceFactory(
                name=elem_name,
                affinity=affinity,
                properties=[effect_properties[prop_key]],
            )

        # Gift wired to all resonances
        gift = GiftFactory(name="Elemental Arts")
        gift.resonances.set(resonances.values())

        # Techniques and capability grants
        techniques: dict[str, Technique] = {}
        grants: list[TechniqueCapabilityGrant] = []

        for tech_name, cap_names, _resonance_name in _ELEMENTAL_TECHNIQUES:
            technique = TechniqueFactory(
                name=tech_name,
                gift=gift,
                intensity=3,
                control=3,
                anima_cost=15,
            )
            techniques[tech_name] = technique

            for cap_name in cap_names:
                grant = TechniqueCapabilityGrantFactory(
                    technique=technique,
                    capability=capability_types[cap_name],
                    base_value=5,
                    intensity_multiplier=Decimal("1.0"),
                )
                grants.append(grant)

        return techniques, grants

    @staticmethod
    def wire_social_technique_capabilities(
        techniques: dict[str, Technique],
        capability_types: dict[str, CapabilityType],
    ) -> list[TechniqueCapabilityGrant]:
        """Add TechniqueCapabilityGrants to existing social techniques.

        Args:
            techniques: action_key → Technique dict (from ``create_all()``).
            capability_types: name → CapabilityType lookup.

        Returns:
            List of all created TechniqueCapabilityGrant instances.
        """
        from world.magic.factories import (  # noqa: PLC0415
            TechniqueCapabilityGrantFactory,
        )

        # Build reverse lookup: technique.name → Technique
        name_to_technique: dict[str, Technique] = {t.name: t for t in techniques.values()}

        grants: list[TechniqueCapabilityGrant] = []
        for tech_name, cap_names in _SOCIAL_TECHNIQUE_CAPABILITIES.items():
            technique = name_to_technique[tech_name]
            for cap_name in cap_names:
                grant = TechniqueCapabilityGrantFactory(
                    technique=technique,
                    capability=capability_types[cap_name],
                    base_value=5,
                    intensity_multiplier=Decimal("1.0"),
                )
                grants.append(grant)

        return grants

    @staticmethod
    def create_alteration_content() -> AlterationContentResult:
        """Create library entries at three tiers for alteration pipeline tests.

        Creates:
        - Three staff library MagicalAlterationTemplate entries at tiers
          COSMETIC_TOUCH (1), MARKED (2), and TOUCHED (3), each backed by a
          ConditionTemplate with permanent duration and a ConditionResistanceModifier
          effect row (the one effect type that resolve_pending_alteration authors).
        - A shared Affinity + Resonance so library query filtering by affinity
          works correctly across all three entries.
        - A Soulfray ConditionTemplate with one stage whose consequence_pool contains
          a Consequence with a MAGICAL_SCARS ConsequenceEffect, so end-to-end tests
          can drive the full use_technique → Soulfray → MAGICAL_SCARS → PendingAlteration
          pipeline without mocking.

        Safe to call from setUpTestData. Returns an AlterationContentResult
        dataclass with the three templates, shared affinity/resonance, and the
        soulfray consequence pool + stage for pipeline wiring.

        Returns:
            AlterationContentResult dataclass.
        """
        from actions.factories import (  # noqa: PLC0415
            ConsequencePoolEntryFactory,
            ConsequencePoolFactory,
        )
        from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
        from world.checks.factories import (  # noqa: PLC0415
            CheckTypeFactory,
            ConsequenceEffectFactory,
            ConsequenceFactory,
        )
        from world.conditions.constants import DurationType  # noqa: PLC0415
        from world.conditions.factories import (  # noqa: PLC0415
            ConditionCategoryFactory,
            ConditionCheckModifierFactory,
            ConditionResistanceModifierFactory,
            ConditionStageFactory,
            ConditionTemplateFactory,
        )
        from world.magic.audere import SOULFRAY_CONDITION_NAME  # noqa: PLC0415
        from world.magic.constants import AlterationTier  # noqa: PLC0415
        from world.magic.factories import (  # noqa: PLC0415
            AffinityFactory,
            MagicalAlterationTemplateFactory,
            ResonanceFactory,
        )

        alteration_cat = ConditionCategoryFactory(name="Magical Alteration")
        affinity = AffinityFactory(name="Primal (Alteration Test)")
        resonance = ResonanceFactory(name="Ember Touch (Alteration Test)", affinity=affinity)
        check_type = CheckTypeFactory(name="Resilience (Alteration Test)")

        # --- Library entries with full effect rows ---
        # Each entry gets a ConditionResistanceModifier (the one effect that
        # resolve_pending_alteration actually creates on scratch-path resolution).
        tier_data = [
            (AlterationTier.COSMETIC_TOUCH, "Faint Ember Traces"),
            (AlterationTier.MARKED, "Seared Markings"),
            (AlterationTier.TOUCHED, "Flame-Written Flesh"),
        ]
        templates = []
        for tier, cond_name in tier_data:
            from world.conditions.factories import DamageTypeFactory  # noqa: PLC0415

            damage_type = DamageTypeFactory(name=f"Fire (tier {tier} test)")
            condition_template = ConditionTemplateFactory(
                name=cond_name,
                category=alteration_cat,
                description=f"A permanent magical mark from overburn at tier {tier}.",
                default_duration_type=DurationType.PERMANENT,
            )
            # Resistance modifier: fire vulnerability — the effect row type that is
            # authored by resolve_pending_alteration on the scratch path.
            ConditionResistanceModifierFactory(
                condition=condition_template,
                stage=None,
                damage_type=damage_type,
                modifier_value=-5,  # small vulnerability for test purposes
            )
            # Check penalty (social/observer reactivity analogue — for completeness).
            ConditionCheckModifierFactory(
                condition=condition_template,
                stage=None,
                check_type=check_type,
                modifier_value=-5,
                scales_with_severity=False,
            )
            template = MagicalAlterationTemplateFactory(
                condition_template=condition_template,
                tier=tier,
                origin_affinity=affinity,
                origin_resonance=resonance,
                is_library_entry=True,
                is_visible_at_rest=(tier >= AlterationTier.MARKED_PROFOUNDLY),
            )
            templates.append(template)

        # --- Soulfray stage with MAGICAL_SCARS consequence pool ---
        # This wires the full pipeline:
        #   use_technique (low anima) → _handle_soulfray_accumulation
        #     → stage.consequence_pool fires
        #       → Consequence with MAGICAL_SCARS effect
        #         → _apply_magical_scars handler → create_pending_alteration
        soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
            default_duration_type=DurationType.PERMANENT,
        )

        pool = ConsequencePoolFactory(name="Soulfray Stage 1 Consequences (Alteration Test)")

        # Consequence whose effect fires MAGICAL_SCARS with severity=2 → tier MARKED
        magical_scars_consequence = ConsequenceFactory(label="Mage Scars (alteration test)")
        ConsequenceEffectFactory(
            consequence=magical_scars_consequence,
            effect_type=CheckEffectType.MAGICAL_SCARS,
            condition_severity=2,  # severity 2 → AlterationTier.MARKED
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=magical_scars_consequence)

        soulfray_stage = ConditionStageFactory(
            condition=soulfray_template,
            stage_order=1,
            name="Searing (alteration test)",
            consequence_pool=pool,
            severity_threshold=1,  # fires on first severity increment past zero (i.e. second use)
        )

        return AlterationContentResult(
            tier1_entry=templates[0],
            tier2_entry=templates[1],
            tier3_entry=templates[2],
            affinity=affinity,
            resonance=resonance,
            soulfray_consequence_pool=pool,
            soulfray_stage=soulfray_stage,
        )


# ---------------------------------------------------------------------------
# Task 1.11 — seed_canonical_affinities()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 13a — _seed_endure_hallowed_ground_check()
# ---------------------------------------------------------------------------


def _seed_endure_hallowed_ground_check() -> None:
    """Seed the endure_hallowed_ground CheckType and ensure the resolution spine.

    The global resolution charts/outcomes (the ``ResultChart`` rows keyed by
    ``rank_difference`` and the ``CheckOutcome`` catalog they reference) are owned
    by ``world.seeds.checks`` — this helper no longer defines its own
    ``rank_difference=0`` chart (which previously collided with the spine's diff=0
    chart). It calls :func:`seed_check_resolution_tables` so the canonical spine
    (including the "Critical Failure" outcome the magic backfire pools fetch)
    exists even when ``seed_magic_dev()`` is run standalone in integration tests.

    The Magic CheckCategory and endure_hallowed_ground CheckType are seeded via
    ``world.magic.seeds_checks.ensure_magic_check_types()`` (#709). The pipeline
    test uses ``force_check_outcome`` to bypass the dice, so it depends only on
    the CheckOutcome rows existing, not on specific chart bands.
    """
    from world.magic.seeds_checks import ensure_magic_check_types  # noqa: PLC0415
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415

    # --- Ensure the "Magic" CheckCategory + all Magic CheckTypes (incl. endure_hallowed_ground) ---
    ensure_magic_check_types()

    # --- Ensure the canonical resolution spine (charts + outcomes) exists ---
    # The checks spine is the single authority for global resolution charts; this
    # keeps seed_magic_dev() self-sufficient when run standalone.
    seed_check_resolution_tables()


# ---------------------------------------------------------------------------
# Task 13b — _seed_hallowed_reaction_conditions()
# ---------------------------------------------------------------------------

#: SINGLE SOURCE OF TRUTH for the 5 Hallowed-Threshold reaction conditions.
#: ``outcome_tier`` is the CheckOutcome tier this condition is applied on.
#: ``HALLOWED_REACTION_CONDITION_NAMES`` and ``CRIT_FAIL_CONDITION_NAMES`` are
#: DERIVED from this list (see below) so the names live in exactly one place.
#: ``_seed_hallowed_reaction_conditions()`` only reads name/description/
#: player_description/observer_description and ignores ``outcome_tier``.
_HALLOWED_REACTION_SPECS: list[dict[str, str]] = [
    {
        "name": _TEMPERED_AGAINST_LIGHT,
        "outcome_tier": _CRITICAL_SUCCESS,
        "description": (
            "The caster's flesh remembers an old burn; they walk hallowed ground unscathed."
        ),
        "player_description": (
            "You walked into the light and walked out unchanged. Some part of you is being remade."
        ),
        "observer_description": "Their skin barely flickers in the consecrated air.",
    },
    {
        "name": "Singed",
        "outcome_tier": "Success",
        "description": "A faint mark of celestial rejection.",
        "player_description": (
            "Light glances along your skin. A faint mark stings where the spell met sanctified air."
        ),
        "observer_description": "A pale brand glows briefly on their skin.",
    },
    {
        "name": "Burning",
        "outcome_tier": "Failure",
        "description": "Sanctified flame on Abyssal flesh.",
        "player_description": "Your skin burns where it meets the consecrated air.",
        "observer_description": "They smolder, marked by light they cannot bear.",
    },
    {
        "name": _HALLOWED_BURN,
        "outcome_tier": _CRITICAL_FAILURE,
        "description": "A grievous, self-rebuking mark from sanctified ground.",
        "player_description": (
            "The sanctified ground answers the spell with fire. "
            "You are flung from the working, burning."
        ),
        "observer_description": (
            "They are flung from their spell, burning where the light touched them."
        ),
    },
    {
        "name": "Cast Disrupted",
        "outcome_tier": _CRITICAL_FAILURE,
        "description": "The casting failed mid-working; threads in the caster's hands snap.",
        "player_description": (
            "The threads in your hands snap. Whatever you were weaving has come undone."
        ),
        "observer_description": "The spell goes wide and collapses around them.",
    },
]


def _seed_hallowed_reaction_conditions() -> None:
    """Seed the 5 reaction conditions for the Hallowed Threshold pipeline.

    These conditions are applied on different check outcomes when an
    Abyssal-aligned caster uses a technique in a Celestial-aura room:
      Critical Success -> Tempered Against Light
      Success          -> Singed
      Failure          -> Burning
      Critical Failure -> Hallowed Burn + Cast Disrupted

    Burning may already exist (factory-created in some tests); get_or_create
    reuses an existing row with the same name.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415

    # Ensure a "Magical" category exists. Reuse if already present.
    category, _ = ConditionCategory.objects.get_or_create(
        name="Magical",
        defaults={
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
    )

    for spec in _HALLOWED_REACTION_SPECS:
        ConditionTemplate.objects.get_or_create(
            name=spec["name"],
            defaults={
                "category": category,
                "description": spec["description"],
                "player_description": spec["player_description"],
                "observer_description": spec["observer_description"],
                "default_duration_type": DurationType.ROUNDS,
                "default_duration_value": 3,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": True,
            },
        )


# ---------------------------------------------------------------------------
# T12 — consequence pool constants and seed helper
# ---------------------------------------------------------------------------

#: The Critical Failure tier — the only tier with >1 spec (two APPLY_CONDITION
#: effects on one Consequence). All other tiers map 1:1 to a single condition.
_CRIT_FAIL_TIER: str = _CRITICAL_FAILURE


def _derive_tier_condition_names() -> dict[str, str]:
    """CheckOutcome tier name → FIRST condition name at that tier.

    Derived from ``_HALLOWED_REACTION_SPECS`` (the single source of truth).
    Tier insertion order follows spec order; the first spec at each tier wins
    (so Critical Failure → the primary _HALLOWED_BURN). The full list of
    crit-fail names lives in ``CRIT_FAIL_CONDITION_NAMES``.
    """
    names: dict[str, str] = {}
    for spec in _HALLOWED_REACTION_SPECS:
        names.setdefault(spec["outcome_tier"], spec["name"])
    return names


#: DERIVED: CheckOutcome tier name → ConditionTemplate name for the OPPOSED
#: backfire consequence pools. Single source of truth is
#: ``_HALLOWED_REACTION_SPECS`` — do not restate condition names anywhere else.
HALLOWED_REACTION_CONDITION_NAMES: dict[str, str] = _derive_tier_condition_names()

#: DERIVED: every condition applied by the Critical Failure tier, in spec order
#: (two APPLY_CONDITION effects on the same Consequence row).
CRIT_FAIL_CONDITION_NAMES: list[str] = [
    spec["name"] for spec in _HALLOWED_REACTION_SPECS if spec["outcome_tier"] == _CRIT_FAIL_TIER
]

#: Pool names for pair #4 (Abyssal→Celestial) and pair #7 (Primal→Celestial).
_ABYSSAL_CELESTIAL_POOL_NAME: str = "OPPOSED Backfire: Abyssal caster in Celestial place"
_PRIMAL_CELESTIAL_POOL_NAME: str = "OPPOSED Backfire: Primal caster in Celestial place"


def _seed_resonance_environment_consequence_pools() -> None:
    """Seed OPPOSED consequence pools for pair #4 (Abyssal→Celestial) and #7 (Primal→Celestial).

    Creates two ConsequencePool rows (one per pairing), each with four
    ConsequencePoolEntry → Consequence rows keyed by CheckOutcome tier,
    with ConsequenceEffect(effect_type=APPLY_CONDITION) wiring:

        Critical Success  → Tempered Against Light (1 effect)
        Success           → Singed                 (1 effect)
        Failure           → Burning                (1 effect)
        Critical Failure  → Hallowed Burn          (2 effects)
                            + Cast Disrupted

    Then sets AffinityInteraction.consequence_pool on both rows and saves.

    Depends on:
    - seed_canonical_affinities()      (Celestial/Primal/Abyssal must exist)
    - _seed_affinity_interactions()    (9 AffinityInteraction rows)
    - _seed_hallowed_reaction_conditions() (all 5 ConditionTemplate rows)
    - _seed_endure_hallowed_ground_check() (ensures the resolution-spine
      CheckOutcome rows via seed_check_resolution_tables)

    Idempotent: get_or_create keyed on stable names at every layer.  Duplicate
    ConsequencePoolEntry rows are prevented by the (pool, consequence) unique
    constraint; duplicate ConsequenceEffect rows are guarded explicitly.
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
    from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import AffinityInteraction  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    # --- Fetch CheckOutcome tiers (seeded by the resolution spine via
    # _seed_endure_hallowed_ground_check -> seed_check_resolution_tables) ---
    outcome_map: dict[str, CheckOutcome] = {}
    for name in (_CRITICAL_SUCCESS, "Success", "Failure", _CRITICAL_FAILURE):
        outcome_map[name] = CheckOutcome.objects.get(name=name)

    # --- Fetch injury ConditionTemplates (created by _seed_hallowed_reaction_conditions) ---
    # Names come from the single source of truth (_HALLOWED_REACTION_SPECS) and are
    # unique per spec, so no de-dup guard is needed when building this map.
    cond_map: dict[str, ConditionTemplate] = {
        spec["name"]: ConditionTemplate.objects.get(name=spec["name"])
        for spec in _HALLOWED_REACTION_SPECS
    }

    def _build_pool(pool_name: str, description: str) -> ConsequencePool:
        """Create (or fetch) a pool and wire its 4 Consequence + ConsequenceEffect rows."""
        pool, _ = ConsequencePool.objects.get_or_create(
            name=pool_name,
            defaults={"description": description},
        )

        # --- Single-effect outcomes: every tier except Critical Failure ---
        # Derived inline from the single source of truth (no separate map constant).
        for outcome_name, condition_name in HALLOWED_REACTION_CONDITION_NAMES.items():
            if outcome_name == _CRIT_FAIL_TIER:
                continue
            outcome = outcome_map[outcome_name]
            condition = cond_map[condition_name]
            # SOFT NATURAL KEY: there is no DB constraint on (outcome_tier, label).
            # Idempotency relies on ConsequencePool.name being unique=True and the
            # label embedding that unique pool name, so (outcome_tier, label) is
            # effectively pool-scoped-unique. A label-format change across runs
            # would create duplicates (acceptable for seed; do NOT change the model).
            consequence, _ = Consequence.objects.get_or_create(
                outcome_tier=outcome,
                label=f"{pool_name}: {outcome_name}",
                defaults={
                    "mechanical_description": f"Apply {condition_name}.",
                    "weight": 1,
                    "character_loss": False,
                },
            )
            ConsequencePoolEntry.objects.get_or_create(
                pool=pool,
                consequence=consequence,
            )
            # SOFT NATURAL KEY: the (consequence, effect_type, condition_template)
            # triple is functionally unique for this seed but is NOT DB-enforced
            # (pre-existing model-wide gap affecting all ConsequenceEffect callers;
            # out of scope for this seed task — tracked as a separate follow-up).
            ConsequenceEffect.objects.get_or_create(
                consequence=consequence,
                effect_type=CheckEffectType.APPLY_CONDITION,
                condition_template=condition,
                defaults={"execution_order": 0},
            )

        # --- Critical Failure: two APPLY_CONDITION effects on one Consequence ---
        crit_fail_outcome = outcome_map[_CRITICAL_FAILURE]
        crit_fail_label = f"{pool_name}: Critical Failure"
        # SOFT NATURAL KEY (same rationale as above): (outcome_tier, label) is not
        # DB-unique; idempotency relies on the unique pool name embedded in label.
        crit_fail_consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=crit_fail_outcome,
            label=crit_fail_label,
            defaults={
                "mechanical_description": "Apply Hallowed Burn and Cast Disrupted.",
                "weight": 1,
                "character_loss": False,
            },
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=crit_fail_consequence,
        )
        for order, cond_name in enumerate(CRIT_FAIL_CONDITION_NAMES):
            # SOFT NATURAL KEY: (consequence, effect_type, condition_template) is
            # functionally unique here but NOT DB-enforced (pre-existing model-wide
            # gap; out of scope for this seed task — tracked separately).
            ConsequenceEffect.objects.get_or_create(
                consequence=crit_fail_consequence,
                effect_type=CheckEffectType.APPLY_CONDITION,
                condition_template=cond_map[cond_name],
                defaults={"execution_order": order},
            )

        return pool

    # --- Build both pools ---
    abyssal_celestial_pool = _build_pool(
        _ABYSSAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for an Abyssal caster working magic in a Celestial place.",
    )
    primal_celestial_pool = _build_pool(
        _PRIMAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for a Primal caster working magic in a Celestial place.",
    )

    # --- Wire AffinityInteraction.consequence_pool for pair #4 and #7 ---
    abyssal = Affinity.objects.get(name="Abyssal")
    primal = Affinity.objects.get(name="Primal")
    celestial = Affinity.objects.get(name="Celestial")

    pair4 = AffinityInteraction.objects.get(
        source_affinity=abyssal,
        environment_affinity=celestial,
    )
    if pair4.consequence_pool_id != abyssal_celestial_pool.pk:
        pair4.consequence_pool = abyssal_celestial_pool
        pair4.save(update_fields=["consequence_pool"])

    pair7 = AffinityInteraction.objects.get(
        source_affinity=primal,
        environment_affinity=celestial,
    )
    if pair7.consequence_pool_id != primal_celestial_pool.pk:
        pair7.consequence_pool = primal_celestial_pool
        pair7.save(update_fields=["consequence_pool"])


# ---------------------------------------------------------------------------
# T13 — _seed_resonance_alignment_boons()
# ---------------------------------------------------------------------------

#: Authored buff ConditionTemplate specs for the Abyssal/Abyssal ALIGNED boon family.
#: Two bands: LOW (min_magnitude=1) → minor empowerment; HIGH (min_magnitude=40) → deep attuned.
#: Descriptions narrate WHY an abyssal place empowers an abyssal caster.
_ABYSSAL_BOON_SPECS: list[dict[str, str]] = [
    {
        "name": "Abyssal Resonance — Minor Attunement",
        "band": "low",
        "description": (
            "The dissolution that permeates this place recognises the caster's touch. "
            "The boundary between intent and effect thins slightly, smoothing the passage "
            "of abyssal workings."
        ),
        "player_description": (
            "Something in the air here knows you. Your spells feel lighter, the threads "
            "a little more willing than usual."
        ),
        "observer_description": (
            "A subtle ease settles over their gestures — as though the place itself is "
            "helping them."
        ),
    },
    {
        "name": "Abyssal Resonance — Deep Attunement",
        "band": "high",
        "description": (
            "The concentrated dissolution saturating this place and the caster's own "
            "abyssal nature are in alignment so deep that the distinction between them "
            "blurs. The caster's workings are carried on the current of the place's power."
        ),
        "player_description": (
            "The place pours into you. Every thread you reach for is already half-woven "
            "by the dissolution around you. You are not working against the world here — "
            "you are the world working."
        ),
        "observer_description": (
            "The dissolution in the air seems to gather toward them, pulled by the same "
            "source that moves in their hands."
        ),
    },
]

#: min_magnitude thresholds for the low and high Abyssal boon bands.
#: LOW=1: any non-zero magnitude qualifies for the lesser buff.
#: HIGH=40: above the low band; the seeded Abyssal Sanctum room (magnitude=60) qualifies.
_ABYSSAL_BOON_LOW_MIN_MAGNITUDE: int = 1
_ABYSSAL_BOON_HIGH_MIN_MAGNITUDE: int = 40

#: Name for the positive ConditionCategory that owns buff/boon templates.
#: Must NOT match the negative "Magical" category used by injury/reaction conditions.
_MAGICAL_BOON_CATEGORY_NAME: str = "Magical Boon"


def _seed_resonance_alignment_boons() -> None:
    """Seed ALIGNED boon tiers for pair #5 (Abyssal source → Abyssal environment).

    Creates:
    - A "Magical Boon" ConditionCategory with is_negative=False (or reuses if already present).
      This is DISTINCT from the negative "Magical" category used by injury/reaction conditions.
      is_negative is load-bearing: services filter positive vs negative conditions by this flag.
    - Two named buff ConditionTemplate rows (low and high band) with authored
      descriptions narrating why an abyssal place empowers an abyssal caster.
    - Two ResonanceAlignmentBoonTier rows for pair #5 with ascending min_magnitude:
        LOW  band (min_magnitude=1)  → minor attunement template
        HIGH band (min_magnitude=40) → deep attunement template

    IMPORTANT: full_clean() is called before every tier.save() to exercise the
    ALIGNED-valence validation in ResonanceAlignmentBoonTier.clean(). A bare
    objects.create() bypasses clean(), so this explicit call is mandatory.

    Depends on:
    - seed_canonical_affinities()   (Abyssal must exist)
    - _seed_affinity_interactions() (pair #5 AffinityInteraction must exist)

    Idempotent: get_or_create keyed on stable natural keys (template by name;
    tier by (affinity_interaction, min_magnitude) unique constraint).
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import (  # noqa: PLC0415
        AffinityInteraction,
        ResonanceAlignmentBoonTier,
    )

    # --- Positive "Magical Boon" ConditionCategory for buff templates ---
    # MUST be separate from the negative "Magical" category (used by injury conditions).
    # is_negative=False is load-bearing: services/views count and filter positive vs negative
    # conditions by this flag (see conditions/services.py only_negative filter and
    # conditions/views.py positive/negative counting).
    category, _ = ConditionCategory.objects.get_or_create(
        name=_MAGICAL_BOON_CATEGORY_NAME,
        defaults={
            "description": (
                "Positive magical conditions from resonance alignment and aura attunement."
            ),
            "is_negative": False,
            "display_order": 10,
        },
    )

    # --- Seed the two boon ConditionTemplates ---
    # DurationType.PERMANENT + default_duration_value=0: persists until cleared by the
    # movement service on the next move (no inherent expiry timer).
    template_map: dict[str, ConditionTemplate] = {}
    for spec in _ABYSSAL_BOON_SPECS:
        template, _ = ConditionTemplate.objects.get_or_create(
            name=spec["name"],
            defaults={
                "category": category,
                "description": spec["description"],
                "player_description": spec["player_description"],
                "observer_description": spec["observer_description"],
                "default_duration_type": DurationType.PERMANENT,
                "default_duration_value": 0,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": False,
            },
        )
        template_map[spec["band"]] = template

    # --- Fetch pair #5: Abyssal → Abyssal (ALIGNED) ---
    abyssal = Affinity.objects.get(name="Abyssal")
    pair5 = AffinityInteraction.objects.get(
        source_affinity=abyssal,
        environment_affinity=abyssal,
    )

    # --- Seed two boon tiers with full_clean() guard before every save() ---
    # full_clean() is MANDATORY here: ResonanceAlignmentBoonTier.clean() validates
    # ALIGNED valence but there is no save() override — objects.create() bypasses it.
    # Calling full_clean() before save() ensures a non-ALIGNED interaction can never
    # be silently attached, even if this helper is mis-called with wrong data.
    tier_specs: list[tuple[int, str]] = [
        (_ABYSSAL_BOON_LOW_MIN_MAGNITUDE, "low"),
        (_ABYSSAL_BOON_HIGH_MIN_MAGNITUDE, "high"),
    ]
    for min_magnitude, band in tier_specs:
        condition_template = template_map[band]
        # get_or_create keyed on the unique (affinity_interaction, min_magnitude) pair.
        # On the CREATE path: build the instance, full_clean(), then save().
        # On the GET path: no save needed; full_clean is already guaranteed on prior run.
        try:
            ResonanceAlignmentBoonTier.objects.get(
                affinity_interaction=pair5,
                min_magnitude=min_magnitude,
            )
        except ResonanceAlignmentBoonTier.DoesNotExist:
            tier = ResonanceAlignmentBoonTier(
                affinity_interaction=pair5,
                min_magnitude=min_magnitude,
                condition_template=condition_template,
            )
            tier.full_clean()  # CRITICAL: validates ALIGNED valence (clean() not called by save())
            tier.save()


# ---------------------------------------------------------------------------
# Task 13c — _seed_hallowed_achievement_bridge()
# ---------------------------------------------------------------------------

_HALLOWED_ACHIEVEMENT_BRIDGE_SPECS: list[dict[str, object]] = [
    {
        "condition_name": _TEMPERED_AGAINST_LIGHT,
        "stat_key": "conditions.tempered_against_light.gained",
        "stat_name": "Tempered Against Light Gained",
        "achievement_name": "Hallowed-Hardened",
        "achievement_description": (
            "Walked into hallowed ground unscathed. The wound your blood "
            "remembers has hardened to a callus."
        ),
        "notification_level": "gamewide",
    },
    {
        "condition_name": "Singed",
        "stat_key": "conditions.singed.gained",
        "stat_name": "Singed Gained",
        "achievement_name": "Touched by Light",
        "achievement_description": "Light glanced your skin. You carry a faint mark.",
        "notification_level": "personal",
    },
    {
        "condition_name": _HALLOWED_BURN,
        "stat_key": "conditions.hallowed_burn.gained",
        "stat_name": "Hallowed Burn Gained",
        "achievement_name": "Cast Out by the Light",
        "achievement_description": (
            "Broken against the threshold. Sanctified ground answered the spell with fire."
        ),
        "notification_level": "gamewide",
    },
]


def _seed_hallowed_achievement_bridge() -> None:
    """Seed the achievement bridge for the Hallowed Threshold pipeline.

    For Tempered Against Light / Singed / Hallowed Burn (3 of the 4 reaction
    outcomes — Burning is common-failure, not noteworthy enough for an
    achievement), creates:

        StatDefinition → ConditionStatRule → Achievement → AchievementRequirement

    Discoveries fire automatically via the existing achievements engine when
    the first character earns each Achievement.

    Depends on _seed_hallowed_reaction_conditions() having run first to
    create the ConditionTemplate rows we reference.
    """
    from django.utils.text import slugify  # noqa: PLC0415

    from world.achievements.constants import (  # noqa: PLC0415
        ComparisonType,
        ConditionEventType,
    )
    from world.achievements.models import (  # noqa: PLC0415
        Achievement,
        AchievementRequirement,
        ConditionStatRule,
        StatDefinition,
    )
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415

    for spec in _HALLOWED_ACHIEVEMENT_BRIDGE_SPECS:
        condition = ConditionTemplate.objects.get(name=spec["condition_name"])
        stat, _ = StatDefinition.objects.get_or_create(
            key=spec["stat_key"],
            defaults={
                "name": spec["stat_name"],
                "description": (
                    f"Count of times this character has gained {spec['condition_name']}."
                ),
            },
        )
        ConditionStatRule.objects.get_or_create(
            stat=stat,
            condition=condition,
            event_type=ConditionEventType.GAINED,
            defaults={"increment_amount": 1},
        )
        notification_level = spec["notification_level"]
        achievement, _ = Achievement.objects.get_or_create(
            name=spec["achievement_name"],
            defaults={
                "slug": slugify(spec["achievement_name"]),
                "description": spec["achievement_description"],
                "hidden": True,
                "notification_level": notification_level,
                "is_active": True,
            },
        )
        # Key on (achievement, stat, threshold, comparison) to stay idempotent
        # without requiring a DB-level unique constraint on AchievementRequirement.
        AchievementRequirement.objects.get_or_create(
            achievement=achievement,
            stat=stat,
            threshold=1,
            comparison=ComparisonType.GTE,
        )


# ---------------------------------------------------------------------------
# Task RC4 — _seed_resonance_environment_rooms()
# ---------------------------------------------------------------------------

#: Cascade magnitude for the Low celestial room.
_CELESTIAL_LOW_MAGNITUDE: int = 10

#: Cascade magnitude for the High celestial room.
_CELESTIAL_HIGH_MAGNITUDE: int = 80

#: Cascade magnitude for the Abyssal aligned-pole room.
_ABYSSAL_ALIGNED_MAGNITUDE: int = 60


def _seed_resonance_environment_rooms() -> None:
    """Seed three cascade-resonance rooms for the resonance-environment pipeline.

    Replaces the deleted RoomAuraProfile/RoomResonance approach. Room resonance
    magnitudes now live as LocationValueModifier rows (key_type=RESONANCE),
    created via tag_room_resonance and then magnitude-tuned to the desired level.

    The "Hallowed Rejection" marker ConditionTemplate is also seeded here as
    flavor content for the story.

    Three rooms:
      - "The Hallowed Threshold (Low)"   — Celestial / Light, magnitude=10
      - "The Hallowed Threshold (High)"  — Celestial / Light, magnitude=80
      - "The Resonant Sanctum (Aligned)" — Abyssal / Dissolution, magnitude=60

    Idempotent at every layer:
      - rooms: filter().first() + create_object(nohome=True) when absent
      - RoomProfile: get_or_create
      - LocationValueModifier: tag_room_resonance uses update_or_create keyed on
        (room_profile, resonance, source) then we set .value + .save() to tune
        magnitude — re-runs restore the desired value.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Resonance  # noqa: PLC0415
    from world.magic.services.gain import tag_room_resonance  # noqa: PLC0415

    # ----- Hallowed Rejection marker (flavor condition for the story) -----
    category, _ = ConditionCategory.objects.get_or_create(
        name="Magical",
        defaults={
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
    )
    ConditionTemplate.objects.get_or_create(
        name="Hallowed Rejection",
        defaults={
            "category": category,
            "description": (
                "An Abyssal-aligned soul remembers a wound made by sanctified light. "
                "Whenever the bearer casts in a celestial-aura room, the rejection "
                "answers with fire."
            ),
            "player_description": "You bear a scar that hates hallowed ground.",
            "observer_description": "They flinch from sanctified air.",
            "default_duration_type": DurationType.PERMANENT,
            "default_duration_value": 0,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": False,
        },
    )

    # ----- Rooms with cascade resonance -----
    light = Resonance.objects.get(name="Light")
    dissolution = Resonance.objects.get(name="Dissolution")

    room_specs: list[tuple[str, Resonance, int]] = [
        ("The Hallowed Threshold (Low)", light, _CELESTIAL_LOW_MAGNITUDE),
        ("The Hallowed Threshold (High)", light, _CELESTIAL_HIGH_MAGNITUDE),
        ("The Resonant Sanctum (Aligned)", dissolution, _ABYSSAL_ALIGNED_MAGNITUDE),
    ]

    for db_key, resonance, magnitude in room_specs:
        # ObjectDB.db_key is not unique in Evennia — use filter().first() for idempotency.
        existing = ObjectDB.objects.filter(
            db_key=db_key,
            db_typeclass_path=_ROOM_MODEL,
        ).first()
        if existing is not None:
            room = existing
        else:
            # Evennia's create_object fires at_object_creation, which auto-creates
            # the RoomProfile OneToOne extension for typeclasses.rooms.Room.
            room = evennia_create.create_object(
                typeclass=_ROOM_MODEL,
                key=db_key,
                nohome=True,
            )
        # RoomProfile is auto-created by Room.at_object_creation().
        profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
        # Tag the room with the resonance (update_or_create, idempotent).
        # Returns the LocationValueModifier row; tune value to the desired magnitude.
        modifier = tag_room_resonance(profile, resonance)
        if modifier.value != magnitude:
            modifier.value = magnitude
            modifier.save(update_fields=["value"])


# ---------------------------------------------------------------------------
# Task 13f — _seed_hallowed_threshold_story()
# ---------------------------------------------------------------------------


def _seed_hallowed_threshold_story() -> None:
    """Seed the Hallowed Threshold Story DAG.

    Structure:
      Story "The Hallowed Threshold" (CHARACTER scope, no character_sheet — template)
        Chapter "First Trial" (order=1)
          Episode "Stepping Into Light" (order=1, source)
            Beat-Tempered: CONDITION_HELD Tempered Against Light
            Beat-Singed: CONDITION_HELD Singed
            Beat-Burning: CONDITION_HELD Burning
            Beat-Hallowed-Burn: CONDITION_HELD Hallowed Burn
          Episode "Tempered Walk" (order=2, destination)
          Episode _MARKED_PATH (order=3, destination, shared SUCCESS+FAILURE)
          Episode "Cast Out" (order=4, destination)

      Transitions out of Stepping Into Light (in order):
        1 → Tempered Walk (TRO: Beat-Tempered SUCCESS)
        2 → Cast Out (TRO: Beat-Hallowed-Burn SUCCESS)
        3 → Marked Path (TRO: Beat-Singed SUCCESS)
        4 → Marked Path (TRO: Beat-Burning SUCCESS)

    ZERO EpisodeProgressionRequirement rows — gate is open; routing depends
    purely on which beat the reactive flow satisfies.

    Idempotent via get_or_create throughout. Re-running on a populated DB is a
    no-op; staff edits to existing rows are preserved.
    """
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.stories.constants import (  # noqa: PLC0415
        BeatOutcome,
        BeatPredicateType,
        StoryScope,
    )
    from world.stories.models import (  # noqa: PLC0415
        Beat,
        Chapter,
        Episode,
        Story,
        Transition,
        TransitionRequiredOutcome,
    )
    from world.stories.types import StoryPrivacy, StoryStatus  # noqa: PLC0415

    # --- Story (CHARACTER scope, no character_sheet — used as a template;
    #     the pipeline test wires character_sheet at runtime per playthrough) ---
    story, _ = Story.objects.get_or_create(
        title="The Hallowed Threshold",
        defaults={
            "description": (
                "A threshold of sanctified light. Abyssal-aligned casters who attempt "
                "to work magic here will find the ground remembers them."
            ),
            "scope": StoryScope.CHARACTER,
            "character_sheet": None,
            "status": StoryStatus.INACTIVE,
            "privacy": StoryPrivacy.PUBLIC,
        },
    )

    # --- Chapter ---
    chapter, _ = Chapter.objects.get_or_create(
        story=story,
        order=1,
        defaults={"title": "First Trial"},
    )

    # --- Episodes ---
    episodes_by_title: dict[str, Episode] = {}
    for ep_title, ep_order in [
        ("Stepping Into Light", 1),
        ("Tempered Walk", 2),
        (_MARKED_PATH, 3),
        ("Cast Out", 4),
    ]:
        ep, _ = Episode.objects.get_or_create(
            chapter=chapter,
            order=ep_order,
            defaults={"title": ep_title},
        )
        episodes_by_title[ep_title] = ep

    source = episodes_by_title["Stepping Into Light"]

    # --- Beats on source episode ---
    beat_specs: list[tuple[str, str]] = [
        (
            _TEMPERED_AGAINST_LIGHT,
            "The light bends around you instead of burning. The wound your blood "
            "remembers has hardened to a callus.",
        ),
        (
            "Singed",
            "Light glances along your skin. A faint mark stings where the spell "
            "met sanctified air.",
        ),
        (
            "Burning",
            "The ground rejects you. Your skin burns where it meets the "
            "consecrated air, and the spell goes wide.",
        ),
        (
            _HALLOWED_BURN,
            "The sanctified ground answers the spell with fire. You are flung "
            "from the working, burning, and the threads in your hands snap.",
        ),
    ]
    beats_by_condition_name: dict[str, Beat] = {}
    for cond_name, player_resolution_text in beat_specs:
        condition = ConditionTemplate.objects.get(name=cond_name)
        beat, _ = Beat.objects.get_or_create(
            episode=source,
            predicate_type=BeatPredicateType.CONDITION_HELD,
            required_condition_template=condition,
            defaults={
                "internal_description": (
                    f"Beat satisfied when character gains the '{cond_name}' condition "
                    "as a result of the hallowed-ground endurance check."
                ),
                "player_resolution_text": player_resolution_text,
            },
        )
        beats_by_condition_name[cond_name] = beat

    # --- Transitions out of source episode ---
    marked_summary = (
        "The light marked you. You carry the burn now — and a question about what you are."
    )
    transition_specs: list[tuple[int, str, str, str]] = [
        (
            1,
            "Tempered Walk",
            _TEMPERED_AGAINST_LIGHT,
            "You walked into hallowed ground and walked out unchanged. "
            "Some part of you is being remade.",
        ),
        (
            2,
            "Cast Out",
            _HALLOWED_BURN,
            "You broke against the threshold. Whatever was watching turned away. "
            "You will not try this again the same way.",
        ),
        (3, _MARKED_PATH, "Singed", marked_summary),
        (4, _MARKED_PATH, "Burning", marked_summary),
    ]
    for order, target_title, beat_cond_name, connection_summary in transition_specs:
        target = episodes_by_title[target_title]
        transition, _ = Transition.objects.get_or_create(
            source_episode=source,
            target_episode=target,
            order=order,
            defaults={"connection_summary": connection_summary},
        )
        beat = beats_by_condition_name[beat_cond_name]
        TransitionRequiredOutcome.objects.get_or_create(
            transition=transition,
            beat=beat,
            defaults={"required_outcome": BeatOutcome.SUCCESS},
        )


def seed_canonical_affinities() -> None:
    """Seed the 3 canonical magic Affinities (Celestial / Primal / Abyssal).

    Idempotent. Re-running on a populated DB is a no-op for these rows.
    Other magic content (resonances, room aura, etc.) can depend on these
    existing — call this before any seed that references Affinity FKs.
    """
    from world.magic.models.affinity import Affinity  # noqa: PLC0415

    for name in ("Celestial", "Primal", "Abyssal"):
        Affinity.objects.get_or_create(name=name)


def seed_canonical_resonances() -> None:
    """Seed canonical Resonances for the magic-story slice.

    Celestial: Light / Sanctity / Radiance
    Abyssal: Dissolution

    Depends on seed_canonical_affinities(). Idempotent via get_or_create.
    The Celestial resonances are used by Hallowed Threshold room cascade rows.
    Dissolution (Abyssal) is used by the Resonant Sanctum room for the
    ALIGNED-pole amplification subtest (an Abyssal caster casting in an Abyssal
    resonance room gets the boon).
    """
    from world.magic.models.affinity import Affinity, Resonance  # noqa: PLC0415

    celestial = Affinity.objects.get(name="Celestial")
    for name in ("Light", "Sanctity", "Radiance"):
        Resonance.objects.get_or_create(
            name=name,
            defaults={"affinity": celestial},
        )

    abyssal = Affinity.objects.get(name="Abyssal")
    Resonance.objects.get_or_create(
        name="Dissolution",
        defaults={"affinity": abyssal},
    )


# Task RC1 — directed RPS affinity interaction matrix
# (source_name, env_name, valence, kind, aggressor, severity_multiplier, caster_dominance_defiles)
# caster_dominance_defiles=True ONLY for the Abyssal-caster OPPOSED pairs (#4 Abyssal->Celestial,
# #6 Abyssal->Primal): a strong-enough Abyssal caster overpowers and defiles those places.
_AFFINITY_INTERACTION_ROWS: list[tuple[str, str, str, str, str, str, bool]] = [
    ("Celestial", "Celestial", "aligned", "amplify", "environment", "1.00", False),
    ("Celestial", "Abyssal", "opposed", "reject", "environment", "1.00", False),
    ("Celestial", "Primal", "opposed", "repel", "environment", "0.30", False),
    ("Abyssal", "Celestial", "opposed", "reject", "environment", "1.00", True),
    ("Abyssal", "Abyssal", "aligned", "amplify", "environment", "1.00", False),
    ("Abyssal", "Primal", "opposed", "corrupt", "caster", "1.00", True),
    ("Primal", "Celestial", "opposed", "reject", "environment", "1.00", False),
    ("Primal", "Abyssal", "opposed", "corrupt", "environment", "1.00", False),
    ("Primal", "Primal", "aligned", "amplify", "environment", "1.00", False),
]


def _seed_affinity_interactions() -> None:
    """Seed the 9 directed AffinityInteraction rows (caster affinity → place affinity).

    Depends on seed_canonical_affinities() (Celestial / Primal / Abyssal must exist).
    Idempotent: get_or_create keyed on (source_affinity, environment_affinity).
    Staff edits to valence/kind/aggressor/severity_multiplier are preserved.

    ``caster_dominance_defiles`` is authored lore (not a staff tuning knob), so it is
    enforced even on pre-existing rows via an explicit set-after-get — this avoids the
    get_or_create "defaults dropped when the row already exists" gotcha, while leaving
    the genuinely-tunable fields untouched.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import AffinityInteraction  # noqa: PLC0415

    canonical_names = ("Celestial", "Primal", "Abyssal")
    affinity_cache: dict[str, Affinity] = {
        obj.name: obj for obj in Affinity.objects.filter(name__in=canonical_names)
    }
    for row in _AFFINITY_INTERACTION_ROWS:
        src_name, env_name, valence, kind, aggressor, mult_str, defiles = row
        obj, created = AffinityInteraction.objects.get_or_create(
            source_affinity=affinity_cache[src_name],
            environment_affinity=affinity_cache[env_name],
            defaults={
                "valence": valence,
                "kind": kind,
                "aggressor": aggressor,
                "severity_multiplier": Decimal(mult_str),
                "caster_dominance_defiles": defiles,
            },
        )
        if not created and obj.caster_dominance_defiles != defiles:
            obj.caster_dominance_defiles = defiles
            obj.save(update_fields=["caster_dominance_defiles"])


def _seed_resonance_environment_config() -> None:
    """Seed (lazy-create) the ResonanceEnvironmentConfig singleton (pk=1).

    Delegates to get_resonance_environment_config() which is idempotent by
    construction — it uses get_or_create(pk=1) internally.
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        get_resonance_environment_config,
    )

    get_resonance_environment_config()


# ---------------------------------------------------------------------------
# Task 1.1 — seed_magic_config()
# ---------------------------------------------------------------------------

#: Canonical IntensityTier definitions: (name, threshold, control_modifier)
_INTENSITY_TIERS: list[tuple[str, int, int]] = [
    ("Minor", 5, 0),
    ("Moderate", 10, -2),
    ("Major", 15, -5),
]

#: Name for the default mishap consequence pool
_MISHAP_POOL_NAME: str = "Magic Mishap Pool (default)"


@dataclass
class MagicConfigResult:
    """Returned by seed_magic_config().

    All singletons are lazy-created via get_or_create.  Re-running preserves
    any edits to existing rows (idempotent).
    """

    anima_config: AnimaConfig
    soulfray_config: SoulfrayConfig
    resonance_gain_config: ResonanceGainConfig
    corruption_config: CorruptionConfig
    audere_threshold: AudereThreshold
    intensity_tiers: dict[str, IntensityTier]  # name → tier
    mishap_pool_tier: MishapPoolTier


def seed_magic_config() -> MagicConfigResult:
    """Lazy-create the 5 magic config singletons plus IntensityTier and MishapPoolTier rows.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    Existing rows are never modified; staff edits survive repeated calls.

    Creates:
    - AnimaConfig (pk=1)
    - SoulfrayConfig (pk=1, resilience_check_type="Magical Endurance")
    - ResonanceGainConfig (pk=1)
    - CorruptionConfig (pk=1)
    - IntensityTier rows: Minor (threshold=5), Moderate (threshold=10), Major (threshold=15)
    - AudereThreshold (minimum_intensity_tier=Major, minimum_warp_stage=Soulfray "Ripping")
    - MishapPoolTier (min_deficit=1, max_deficit=None) backed by a minimal ConsequencePool
    - AnimaRitualBudgetAward / SanctumHomecomingGainAward / SanctumPurgingRetentionAward /
      SanctumDissolutionRecoveryAward: one row per canonical CheckOutcome tier for each of
      the 4 outcome-tier award tables (#1207). Without these, the corresponding
      ``.objects.get(outcome_tier=...)`` lookups raise ``DoesNotExist`` on a missing row.

    Returns:
        MagicConfigResult dataclass with all created/fetched instances.
    """
    from actions.models.consequence_pools import ConsequencePool  # noqa: PLC0415
    from world.magic.audere import AudereThreshold  # noqa: PLC0415
    from world.magic.factories import SoulfrayContentFactory  # noqa: PLC0415
    from world.magic.models import (  # noqa: PLC0415
        AnimaConfig,
        IntensityTier,
        MishapPoolTier,
        SoulfrayConfig,
    )
    from world.magic.models.corruption_config import CorruptionConfig  # noqa: PLC0415
    from world.magic.models.gain_config import ResonanceGainConfig  # noqa: PLC0415
    from world.magic.models.sanctum import (  # noqa: PLC0415
        SanctumDissolutionRecoveryAward,
        SanctumHomecomingGainAward,
        SanctumPurgingRetentionAward,
    )
    from world.magic.models.soulfray import AnimaRitualBudgetAward  # noqa: PLC0415

    # --- AnimaConfig (has its own get_or_create helper) ---
    anima_config = AnimaConfig.get_singleton()

    # --- SoulfrayConfig (singleton, no get_or_create on factory) ---
    # Delegate to seeds_checks so the canonical composition (skills, aspects,
    # trait weights) is also present, not just the bare CheckType row.
    from world.magic.seeds_checks import (  # noqa: PLC0415
        MAGICAL_ENDURANCE_CHECK_TYPE_NAME,
        ensure_magic_check_types,
    )

    resilience_check_type = ensure_magic_check_types()[MAGICAL_ENDURANCE_CHECK_TYPE_NAME]
    soulfray_config, _ = SoulfrayConfig.objects.get_or_create(
        pk=1,
        defaults={
            "soulfray_threshold_ratio": Decimal("0.30"),
            "severity_scale": 10,
            "deficit_scale": 5,
            "resilience_check_type": resilience_check_type,
            "base_check_difficulty": 15,
            "ritual_severity_cost_per_point": 1,
        },
    )

    # --- AnimaRitualBudgetAward: one authored row per canonical CheckOutcome tier ---
    # Replaces the old SoulfrayConfig.ritual_budget_critical_success/_success/_partial/
    # _failure fields (#1207). seed_check_resolution_tables() is idempotent
    # (get_or_create on natural keys), so it's safe to call unconditionally here to
    # guarantee the 5 canonical CheckOutcome rows exist before keying awards on them —
    # this seed helper is called standalone in some test setUpTestData blocks without
    # the check-resolution spine already seeded.
    from world.seeds.checks import seed_check_resolution_tables  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    seed_check_resolution_tables()
    for name, budget in (
        (_CRITICAL_SUCCESS, 10),
        ("Success", 6),
        (_PARTIAL_SUCCESS, 3),
        ("Failure", 1),
        (_CRITICAL_FAILURE, 1),
    ):
        AnimaRitualBudgetAward.objects.get_or_create(
            outcome_tier=CheckOutcome.objects.get(name=name),
            defaults={"budget": budget},
        )

    # --- Sanctum ritual award tables: one authored row per canonical CheckOutcome
    # tier for each of the 3 award models (#1207). These replace the deleted
    # module-level HOMECOMING_GAIN_MULTIPLIERS / PURGING_RETENTION_MODIFIERS /
    # DISSOLUTION_RECOVERY_* constants (Tasks 5/6) — without these seeded rows,
    # `perform_homecoming_ritual`/`perform_purging_ritual`
    # (`world/magic/services/sanctum_rituals.py`) and `_dissolution_recovery_fraction`
    # (`world/magic/services/sanctum_install.py`) all do a bare `.objects.get(...)`
    # that raises `DoesNotExist` on a missing row — an exception NOT in
    # `actions.definitions.sanctum.SANCTUM_EXC`, so it would surface as an
    # unhandled 500. The 4-tier tuning values below are the original module
    # constants (see the plan's Task 4/5/6 sections); "Partial Success" is a new
    # tier introduced by the canonical 5-tier CheckOutcome spine and is seeded at
    # the midpoint between the original Success/Failure values, per the plan's own
    # seed guidance.
    for name, gain_multiplier in (
        (_CRITICAL_SUCCESS, Decimal("1.25")),
        ("Success", Decimal("1.00")),
        (_PARTIAL_SUCCESS, Decimal("0.75")),
        ("Failure", Decimal("0.50")),
        (_CRITICAL_FAILURE, Decimal("0.25")),
    ):
        SanctumHomecomingGainAward.objects.get_or_create(
            outcome_tier=CheckOutcome.objects.get(name=name),
            defaults={"gain_multiplier": gain_multiplier},
        )

    for name, retention_modifier in (
        (_CRITICAL_SUCCESS, Decimal("0.25")),
        ("Success", Decimal("0.00")),
        (_PARTIAL_SUCCESS, Decimal("-0.075")),
        ("Failure", Decimal("-0.15")),
        (_CRITICAL_FAILURE, Decimal("-0.30")),
    ):
        SanctumPurgingRetentionAward.objects.get_or_create(
            outcome_tier=CheckOutcome.objects.get(name=name),
            defaults={"retention_modifier": retention_modifier},
        )

    for name, recovery_fraction in (
        (_CRITICAL_SUCCESS, Decimal("0.80")),
        ("Success", Decimal("0.50")),
        (_PARTIAL_SUCCESS, Decimal("0.30")),
        ("Failure", Decimal("0.10")),
        (_CRITICAL_FAILURE, Decimal("0.0")),
    ):
        SanctumDissolutionRecoveryAward.objects.get_or_create(
            outcome_tier=CheckOutcome.objects.get(name=name),
            defaults={"recovery_fraction": recovery_fraction},
        )

    # --- ResonanceGainConfig (pk=1) ---
    resonance_gain_config, _ = ResonanceGainConfig.objects.get_or_create(pk=1, defaults={})

    # --- CorruptionConfig (pk=1) ---
    corruption_config, _ = CorruptionConfig.objects.get_or_create(pk=1, defaults={})

    # --- IntensityTier reference rows ---
    intensity_tiers: dict[str, IntensityTier] = {}
    for tier_name, threshold, control_mod in _INTENSITY_TIERS:
        tier, _ = IntensityTier.objects.get_or_create(
            name=tier_name,
            defaults={
                "threshold": threshold,
                "control_modifier": control_mod,
                "description": f"{tier_name} intensity level.",
            },
        )
        intensity_tiers[tier_name] = tier

    major_tier = intensity_tiers["Major"]

    # --- Soulfray condition + stages (needed for AudereThreshold.minimum_warp_stage) ---
    # SoulfrayContentFactory() is idempotent — uses get_or_create internally.
    soulfray_content = SoulfrayContentFactory()
    ripping_stage = next(
        s
        for s in soulfray_content.stages
        if s.name == "Ripping"  # noqa: STRING_LITERAL
    )

    # --- AudereThreshold (singleton, no get_or_create on factory) ---
    audere_threshold, _ = AudereThreshold.objects.get_or_create(
        pk=1,
        defaults={
            "minimum_intensity_tier": major_tier,
            "minimum_warp_stage": ripping_stage,
            "intensity_bonus": 20,
            "anima_pool_bonus": 30,
            "warp_multiplier": 2,
        },
    )

    # --- MishapPoolTier: one catch-all tier (min_deficit=1, max_deficit=None) ---
    mishap_pool, _ = ConsequencePool.objects.get_or_create(
        name=_MISHAP_POOL_NAME,
        defaults={"description": "Default pool for magic mishaps from control deficit."},
    )
    mishap_pool_tier, _ = MishapPoolTier.objects.get_or_create(
        min_deficit=1,
        max_deficit=None,
        defaults={"consequence_pool": mishap_pool},
    )

    return MagicConfigResult(
        anima_config=anima_config,
        soulfray_config=soulfray_config,
        resonance_gain_config=resonance_gain_config,
        corruption_config=corruption_config,
        audere_threshold=audere_threshold,
        intensity_tiers=intensity_tiers,
        mishap_pool_tier=mishap_pool_tier,
    )


# ---------------------------------------------------------------------------
# Task 1.2 — seed_canonical_rituals()
# ---------------------------------------------------------------------------


@dataclass
class RitualSeedResult:
    """Returned by seed_canonical_rituals().

    Wraps the canonical Rite of Imbuing, Rite of Atonement, and Ritual of the
    Durance rituals. All are lazy-created via factory django_get_or_create on
    name, so re-running preserves any edits to existing rows (idempotent).
    """

    rite_of_imbuing: Ritual
    rite_of_atonement: Ritual
    ritual_of_the_durance: Ritual


def seed_canonical_rituals() -> RitualSeedResult:
    """Lazy-create the canonical rituals: Imbuing, Atonement, and the Durance.

    All factories use django_get_or_create(name=...) so re-running on a
    populated DB is a no-op. Existing rows are never modified; staff edits
    survive repeated calls.

    Creates:
    - Ritual: "Rite of Imbuing" (SERVICE dispatch to spend_resonance_for_imbuing)
    - Ritual: "Rite of Atonement" (SERVICE dispatch to atonement service)
    - Ritual: "Ritual of the Durance" (SERVICE dispatch to
      advance_class_level_via_session, #1352/#2121) — as canonical as Imbuing/
      Atonement: every character needs it eventually, not just covenant
      members. Previously created only in test factories, so even a live
      officiant's ``ritual draft "Ritual of the Durance"`` failed by name on a
      fresh DB (RitualOfTheDuranceFactory also lazy-creates the companion
      RitualLiturgy row via its post_generation hook).

    Returns:
        RitualSeedResult dataclass with all three ritual instances.
    """
    from world.magic.factories import (  # noqa: PLC0415
        AtonementRitualFactory,
        ImbuingRitualFactory,
        RitualOfTheDuranceFactory,
    )

    imbuing = ImbuingRitualFactory()
    atonement = AtonementRitualFactory()
    durance = RitualOfTheDuranceFactory()
    return RitualSeedResult(
        rite_of_imbuing=imbuing,
        rite_of_atonement=atonement,
        ritual_of_the_durance=durance,
    )


# ---------------------------------------------------------------------------
# Task 1.3 — seed_thread_pull_catalog()
# ---------------------------------------------------------------------------

#: Canonical resonance name for the thread pull catalog.
#: Must not collide with names used by other seed helpers
#: ("Wild Hunt", "Web of Spiders" are claimed by corruption content).
_CATALOG_RESONANCE_NAME: str = "Tideborne"
_CATALOG_AFFINITY_NAME: str = "Primal (Tideborne)"

#: Per-tier pull cost definitions: (tier, resonance_cost, anima_per_thread, label)
#: These are the UNIVERSAL default rows (target_kind=None) that apply to all
#: thread kinds without a kind-specific override.
_PULL_COST_TIERS: list[tuple[int, int, int, str]] = [
    (1, 1, 1, "soft"),
    (2, 3, 2, "medium"),
    (3, 6, 3, "hard"),
]

#: Canonical capability name for CAPABILITY_GRANT effect.
_CATALOG_CAPABILITY_NAME: str = "endurance"


@dataclass
class ThreadPullCatalogResult:
    """Returned by seed_thread_pull_catalog().

    All rows are lazy-created via get_or_create. Re-running preserves any edits
    to existing rows (idempotent).
    """

    pull_costs: dict[int, ThreadPullCost]  # tier → cost row
    canonical_resonance: Resonance
    pull_effects: dict[str, ThreadPullEffect]  # EffectKind value → effect row


def seed_thread_pull_catalog() -> ThreadPullCatalogResult:
    """Lazy-create ThreadPullCost rows (tiers 1/2/3) and a 4-row ThreadPullEffect catalog.

    All writes use get_or_create so re-running on a populated DB is a no-op.
    Existing rows are never modified; staff edits survive repeated calls.

    Creates:
    - ThreadPullCost rows: tier 1 (soft), tier 2 (medium), tier 3 (hard)
    - Affinity "Primal (Tideborne)" — shared affinity for the catalog resonance
    - Resonance "Tideborne" — canonical reference resonance for the catalog
    - CapabilityType "endurance" — used by the CAPABILITY_GRANT effect
    - ThreadPullEffect rows:
        - FLAT_BONUS (tier=1, min_thread_level=0, flat_bonus_amount=10)
        - INTENSITY_BUMP (tier=2, min_thread_level=0, intensity_bump_amount=10)
        - VITAL_BONUS (tier=0, min_thread_level=0, vital_bonus_amount=10, MAX_HEALTH)
        - CAPABILITY_GRANT (tier=3, min_thread_level=5, capability=endurance)

    Returns:
        ThreadPullCatalogResult dataclass with all created/fetched instances.
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget  # noqa: PLC0415
    from world.magic.factories import (  # noqa: PLC0415
        AffinityFactory,
        ResonanceFactory,
        ThreadPullCostFactory,
    )
    from world.magic.models.threads import ThreadPullEffect  # noqa: PLC0415

    # --- ThreadPullCost rows (universal defaults; target_kind=None) ---
    pull_costs: dict[int, ThreadPullCost] = {}
    for tier, resonance_cost, anima_per_thread, label in _PULL_COST_TIERS:
        cost = ThreadPullCostFactory(
            tier=tier,
            target_kind=None,
            resonance_cost=resonance_cost,
            anima_per_thread=anima_per_thread,
            label=label,
        )
        pull_costs[tier] = cost

    # --- ThreadPullCost row (GIFT imbue premium only; #1581: pull cost is uniform) ---
    # GIFT carries an IMBUE premium only (no pull-cost premium; #1581). One tier-1
    # GIFT row carries imbue_cost_multiplier; its pull-cost fields mirror universal.
    ThreadPullCostFactory(
        tier=1,
        target_kind=TargetKind.GIFT,
        resonance_cost=_PULL_COST_TIERS[0][1],  # == universal tier-1 resonance_cost
        anima_per_thread=_PULL_COST_TIERS[0][2],  # == universal tier-1 anima_per_thread
        imbue_cost_multiplier=2,
        label="gift-imbue",
    )

    # --- Canonical resonance (both factory calls use django_get_or_create on name) ---
    affinity = AffinityFactory(name=_CATALOG_AFFINITY_NAME)
    resonance = ResonanceFactory(name=_CATALOG_RESONANCE_NAME, affinity=affinity)

    # --- CapabilityType for CAPABILITY_GRANT (get_or_create on name) ---
    capability, _ = CapabilityType.objects.get_or_create(
        name=_CATALOG_CAPABILITY_NAME,
        defaults={"description": "Endurance capability — used by thread pull catalog."},
    )

    # --- ThreadPullEffect rows (natural key: target_kind, resonance, tier, min_thread_level) ---
    # Using direct ORM get_or_create per task spec to avoid non-idempotent factory calls.
    pull_effects: dict[str, ThreadPullEffect] = {}

    flat_bonus_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=1,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.FLAT_BONUS,
            "flat_bonus_amount": 10,
        },
    )
    pull_effects[EffectKind.FLAT_BONUS] = flat_bonus_effect

    intensity_bump_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=2,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.INTENSITY_BUMP,
            "intensity_bump_amount": 10,
        },
    )
    pull_effects[EffectKind.INTENSITY_BUMP] = intensity_bump_effect

    vital_bonus_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=0,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.VITAL_BONUS,
            "vital_bonus_amount": 10,
            "vital_target": VitalBonusTarget.MAX_HEALTH,
        },
    )
    pull_effects[EffectKind.VITAL_BONUS] = vital_bonus_effect

    capability_grant_effect, _ = ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.TRAIT,
        resonance=resonance,
        tier=3,
        min_thread_level=5,
        defaults={
            "effect_kind": EffectKind.CAPABILITY_GRANT,
            "capability_grant": capability,
        },
    )
    pull_effects[EffectKind.CAPABILITY_GRANT] = capability_grant_effect

    return ThreadPullCatalogResult(
        pull_costs=pull_costs,
        canonical_resonance=resonance,
        pull_effects=pull_effects,
    )


def ensure_relationship_pull_content() -> None:
    """Seed RELATIONSHIP_TRACK ThreadPullEffect rows with a survivability skew (#2021).

    Creates one 4-tier chain per canonical resonance (Light, Sanctity, Radiance,
    Dissolution) = 16 rows total. Tier 0 is passive (always-on); tiers 1-3 are
    paid pulls. All effects are survivability-oriented: VITAL_BONUS to
    DAMAGE_TAKEN_REDUCTION / DEATH_SAVE / KNOCKOUT_RESIST, plus RESISTANCE.

    Idempotent via get_or_create. The relationship_bond_modulation saturating
    curve (#1849) scales these by bond strength when the target IS the threaded
    person or is hostile to them.
    """
    from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget  # noqa: PLC0415
    from world.magic.models import Resonance, ThreadPullEffect  # noqa: PLC0415

    # The four canonical production resonances (seeded by seed_canonical_resonances)
    resonance_names = ["Light", "Sanctity", "Radiance", "Dissolution"]

    for resonance_name in resonance_names:
        resonance = Resonance.objects.filter(name=resonance_name).first()
        if resonance is None:
            continue

        # Tier 0 (passive): VITAL_BONUS(DAMAGE_TAKEN_REDUCTION, 10)
        # Amount bumped from 3 → 10 per #1845: thread_level_multiplier(level 1) = 0.1
        # (#1718's corrected ramp), so round(3 * 0.1) = round(0.3) = 0 — a no-op
        # bonus at low thread levels. 10 clears the floor with margin.
        ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=resonance,
            tier=0,
            min_thread_level=0,
            defaults={
                "effect_kind": EffectKind.VITAL_BONUS,
                "vital_bonus_amount": 10,
                "vital_target": VitalBonusTarget.DAMAGE_TAKEN_REDUCTION,
                "narrative_snippet": "The bond sustains you, reducing harm.",
            },
        )

        # Tier 1 (paid): VITAL_BONUS(DEATH_SAVE, 10)
        # Amount bumped from 5 → 10 per #1845: round(5 * 0.1) = round(0.5) = 0
        # (banker's rounding) at level 1. 10 clears the floor with margin.
        ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=resonance,
            tier=1,
            min_thread_level=0,
            defaults={
                "effect_kind": EffectKind.VITAL_BONUS,
                "vital_bonus_amount": 10,
                "vital_target": VitalBonusTarget.DEATH_SAVE,
                "narrative_snippet": "Fighting for them steadies your hand against death.",
            },
        )

        # Tier 2 (paid): RESISTANCE(2, all damage types)
        ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=resonance,
            tier=2,
            min_thread_level=0,
            defaults={
                "effect_kind": EffectKind.RESISTANCE,
                "resistance_amount": 2,
                "narrative_snippet": "The bond hardens you against all damage.",
            },
        )

        # Tier 3 (paid): VITAL_BONUS(KNOCKOUT_RESIST, 10)
        # Amount bumped from 5 → 10 per #1845: round(5 * 0.1) = round(0.5) = 0
        # (banker's rounding) at level 1. 10 clears the floor with margin.
        ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=resonance,
            tier=3,
            min_thread_level=0,
            defaults={
                "effect_kind": EffectKind.VITAL_BONUS,
                "vital_bonus_amount": 10,
                "vital_target": VitalBonusTarget.KNOCKOUT_RESIST,
                "narrative_snippet": "The deepest bond refuses to fall.",
            },
        )


# ---------------------------------------------------------------------------
# Task 6 (#2222) — ensure_portal_travel_content()
# ---------------------------------------------------------------------------

#: Catalog name for the mirror anchor kind (#2222 Decision 2/5b).
_MIRROR_ANCHOR_KIND_NAME = "Mirror"

#: The starter portal-travel Minor Gift + its single Technique (#2222 Decision 3).
_MIRRORWALKING_GIFT_NAME = "Mirrorwalking"
_MIRRORWALK_TECHNIQUE_NAME = "Mirrorwalk"

#: No prior ``GiftUnlock`` row exists anywhere in seed content to read a norm
#: from (verified — the model has shipped since #1587 but nothing has ever
#: seeded a row). Matches the baseline this same module already uses twice for
#: a single-purpose magic unlock (``seed_facet_thread_unlock`` /
#: ``seed_relationship_track_thread_unlock``, both ``xp_cost=50``) rather than
#: inventing a new number.
_MIRRORWALK_UNLOCK_XP_COST = 50

#: Starter public rooms that get a Mirror anchor so the network has real,
#: reachable nodes on a fresh Big Button run — not just catalog rows (#2222
#: "Seed content"). "The Wanderer's Rest" (the canonical fallback starting
#: room every fresh character passes through) is guaranteed by calling
#: ``ensure_canonical_fallback_room()`` directly. The two magic-story cascade
#: rooms below are seeded earlier in THIS module by
#: ``_seed_resonance_environment_rooms()`` (part of ``seed_starter_magic_story()``,
#: which ``seed_magic_dev()`` calls before this function) — resolved
#: defensively via ``filter().first()`` and skipped (never crash) when absent,
#: e.g. if this function is ever called standalone ahead of that step. No
#: other named public room exists in production seed content today (verified
#: — grepped every ``game_content``/``seeds`` module for room creation).
#: (room db_key, anchor's descriptive name)
_MIRROR_ANCHOR_ROOM_SPECS: list[tuple[str, str]] = [
    ("The Hallowed Threshold (Low)", "a clouded looking-glass"),
    ("The Resonant Sanctum (Aligned)", "a smoke-dark mirror"),
]


def _ensure_mirror_anchor(kind: PortalAnchorKind, room: ObjectDB, name: str) -> None:
    """Get-or-create an active Mirror ``PortalAnchor`` of ``kind`` in ``room``.

    Mirrors the cascade-room ``RoomProfile`` resolution in
    ``_seed_resonance_environment_rooms`` above (``get_or_create`` — a fresh
    ``typeclasses.rooms.Room`` already carries an auto-created ``RoomProfile``
    via ``at_object_creation``, but ``get_or_create`` is the defensive,
    idempotent way to fetch it regardless).
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.magic.models import PortalAnchor  # noqa: PLC0415

    profile, _ = RoomProfile.objects.get_or_create(objectdb=room)
    PortalAnchor.objects.get_or_create(
        room_profile=profile,
        kind=kind,
        defaults={"name": name, "is_network_open": True},
    )


def ensure_portal_travel_content() -> None:
    """Idempotently seed the Mirror portal network's starter content (#2222).

    Creates (get_or_create throughout):

    1. ``PortalAnchorKind`` "Mirror" — arrival "steps out of" / departure
       "steps into" (#2222 Decision 2).
    2. A self-contained "Reflection" Resonance (Celestial affinity) + MINOR
       ``Gift`` "Mirrorwalking" carrying it — mirrors
       ``world.companions.content.ensure_companion_content``'s shape (a MINOR
       gift gets its own dedicated Resonance rather than reusing one of the
       canonical story resonances).
    3. ``Technique`` "Mirrorwalk" — ``travel_anchor_kind=Mirror``,
       ``anima_cost=0`` (#2222 Decision 5d: per-use cost is the technique's
       own ``anima_cost``; 0 for the seeded starter technique is convenience
       by design). Reuses the "Translocation Stance" style and "Teleport"
       ``EffectType`` already seeded by ``ensure_teleport_content`` — both
       fit movement/travel, so this is reuse, not a parallel catalog
       (anti-reinvention pass) — plus the shared standalone cast template so
       the technique is fully castable like every other technique.
    4. A ``GiftUnlock`` row gating Mirrorwalking behind XP
       (``xp_cost=50`` — see ``_MIRRORWALK_UNLOCK_XP_COST``).
    5. Starter Mirror ``PortalAnchor`` rows in 2-3 seeded public rooms (see
       ``_MIRROR_ANCHOR_ROOM_SPECS``) so the mirror network is actually
       reachable, not just cataloged.

    Idempotent at every layer. Re-running on a populated DB preserves staff
    edits (never ``update_or_create``).
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from actions.constants import ActionTargetType  # noqa: PLC0415
    from world.magic.constants import GiftKind  # noqa: PLC0415
    from world.magic.effect_palette_content import (  # noqa: PLC0415
        TRANSLOCATION_STANCE_STYLE_NAME,
    )
    from world.magic.models import (  # noqa: PLC0415
        Affinity,
        EffectType,
        Gift,
        GiftUnlock,
        PortalAnchorKind,
        Resonance,
        Technique,
        TechniqueStyle,
    )
    from world.magic.seeds_cast import get_standalone_cast_template  # noqa: PLC0415
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415

    # 1. Anchor kind.
    mirror_kind, _ = PortalAnchorKind.objects.get_or_create(
        name=_MIRROR_ANCHOR_KIND_NAME,
        defaults={
            "description": (
                "A tall, silvered mirror — a threshold to every other mirror open on its network."
            ),
            "arrival_verb": "steps out of",
            "departure_verb": "steps into",
        },
    )

    # 2. MINOR Gift + its own dedicated Resonance.
    celestial, _ = Affinity.objects.get_or_create(name="Celestial")
    reflection, _ = Resonance.objects.get_or_create(
        name="Reflection",
        defaults={
            "description": "The resonance of thresholds and mirrored passage.",
            "affinity": celestial,
        },
    )
    gift, _ = Gift.objects.get_or_create(
        name=_MIRRORWALKING_GIFT_NAME,
        defaults={
            "description": "Step through an open mirror here and out of its twin elsewhere.",
            "kind": GiftKind.MINOR,
        },
    )
    gift.resonances.add(reflection)  # idempotent M2M add

    # 3. Technique — reuse the existing movement-fitting style + EffectType.
    style, _ = TechniqueStyle.objects.get_or_create(
        name=TRANSLOCATION_STANCE_STYLE_NAME,
        defaults={"description": "A magical style for space-bending techniques."},
    )
    effect_type, _ = EffectType.objects.get_or_create(
        name="Teleport",
        defaults={
            "description": "Instant relocation through bent space.",
            "base_power": None,
            "base_anima_cost": 0,
            "has_power_scaling": False,
        },
    )
    Technique.objects.get_or_create(
        name=_MIRRORWALK_TECHNIQUE_NAME,
        gift=gift,
        defaults={
            "description": (
                "Step into an open mirror and out the other side, wherever its "
                "twin waits open on the network."
            ),
            "style": style,
            "effect_type": effect_type,
            "level": 1,
            "intensity": 1,
            "control": 1,
            "anima_cost": 0,
            "target_type": ActionTargetType.SELF,
            "travel_anchor_kind": mirror_kind,
            "action_template": get_standalone_cast_template(),
        },
    )

    # 4. XP-gated unlock.
    GiftUnlock.objects.get_or_create(
        gift=gift,
        defaults={"xp_cost": _MIRRORWALK_UNLOCK_XP_COST},
    )

    # 5. Starter anchors — the canonical fallback room is guaranteed; the
    #    magic-story cascade rooms are resolved defensively (skip if absent).
    _ensure_mirror_anchor(mirror_kind, ensure_canonical_fallback_room(), "a tall silvered mirror")
    for room_key, anchor_name in _MIRROR_ANCHOR_ROOM_SPECS:
        room = ObjectDB.objects.filter(
            db_key=room_key,
            db_typeclass_path=_ROOM_MODEL,
        ).first()
        if room is None:
            continue
        _ensure_mirror_anchor(mirror_kind, room, anchor_name)


# ---------------------------------------------------------------------------
# Task 1.9 — seed_magic_dev()
# ---------------------------------------------------------------------------


@dataclass
class FacetThreadUnlockResult:
    """Returned by seed_facet_thread_unlock()."""

    unlock: ThreadWeavingUnlock


@dataclass
class RelationshipTrackThreadUnlockResult:
    """Returned by seed_relationship_track_thread_unlock()."""

    track: RelationshipTrack
    unlock: ThreadWeavingUnlock


@dataclass
class MagicDevSeedResult:
    """Returned by seed_magic_dev().

    Composes all Phase 1 seed results into one dataclass.
    ``author_reference_corruption_content()`` returns None so it is not
    represented here; callers can query Wild Hunt / Web of Spiders rows directly.
    ``penetration`` holds the penetration CheckType, factor ladder, and
    check-scoped ModifierTarget seeded by seed_penetration_contest() (#767).
    ``flee`` holds the flee CheckType, ModifierTarget, and FleeConfig singleton
    seeded by seed_flee_check() (#878).
    ``technique_cast_template`` is the shared Technique Cast ActionTemplate seeded
    by ensure_technique_cast_content() (#1306).
    ``relationship_track_thread_unlock`` holds the canonical RELATIONSHIP_TRACK
    ThreadWeavingUnlock (+ backing RelationshipTrack) seeded by
    seed_relationship_track_thread_unlock() (#2027) — the Soul Tether formation
    prerequisite.
    ``soul_tether_content`` holds the Soul Tether authored content (Rituals,
    ConditionTemplates, TriggerDefinitions) seeded by wire_soul_tether_content()
    (#2027) — without this, Soul Tether formation is unreachable in a live game.
    ``covenant_lifecycle_content`` holds the covenant/org lifecycle Rituals
    (Covenant Formation, Covenant Induction, Call the Banners, Mentor's Vow,
    Renew the Oath, Organization Induction) + the MentorBondConfig singleton
    seeded by wire_covenant_lifecycle_rituals() (#2114) — without this, the
    fully-built covenant session machinery is unreachable in a live game.
    ``dramatic_entrance_content`` is the "Grand Entrance" DramaticMomentType
    seeded by ensure_dramatic_entrance_content() (#2183) — flagged
    (suggest_on_technique_entrance=True) so the technique-entrance suggestion
    bridge has real authored content in a live game, not only test factories.
    """

    config: MagicConfigResult
    rituals: RitualSeedResult
    thread_pull_catalog: ThreadPullCatalogResult
    magic_content: MagicContentResult
    facet_thread_unlock: FacetThreadUnlockResult
    penetration: PenetrationContestResult
    flee: FleeSeedResult
    magic_checks: MagicCheckContentResult
    technique_cast_template: ActionTemplate
    relationship_track_thread_unlock: RelationshipTrackThreadUnlockResult
    soul_tether_content: object
    covenant_lifecycle_content: object
    dramatic_entrance_content: object


def seed_facet_thread_unlock() -> FacetThreadUnlockResult:
    """Lazy-create the single global ThreadWeavingUnlock for FACET kind.

    No specific facet is pinned — the unlock applies to weaving any Facet
    thread. Idempotency is guaranteed by ``get_or_create`` semantics keyed on
    ``target_kind=FACET``. The model has no DB-level uniqueness for FACET
    unlocks, but only one global unlock is ever needed (no per-facet variant).
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.weaving import ThreadWeavingUnlock  # noqa: PLC0415

    unlock, _ = ThreadWeavingUnlock.objects.get_or_create(
        target_kind=TargetKind.FACET,
        defaults={"xp_cost": 50},  # baseline cost; staff may tune
    )
    return FacetThreadUnlockResult(unlock=unlock)


def seed_relationship_track_thread_unlock() -> RelationshipTrackThreadUnlockResult:
    """Lazy-create the canonical RELATIONSHIP_TRACK ThreadWeavingUnlock (+ backing track).

    Soul Tether formation (``accept_soul_tether`` in
    ``world.magic.services.soul_tether``) gates on the Sinner holding a
    ``CharacterThreadWeavingUnlock`` for ``TargetKind.RELATIONSHIP_TRACK``
    (``_validate_unlock``) before they can weave the RELATIONSHIP_CAPSTONE
    Thread that carries the Hollow. Unlike FACET, ``ThreadWeavingUnlock.unlock_track``
    is a required non-null FK (per-kind CheckConstraint) — there is no
    RelationshipTrack seeded anywhere in production content yet, so this
    function also lazy-creates one canonical track ("Devotion") to hang the
    unlock off of. This is the minimum authored content needed for the Rite of
    the Soul Tether to be purchasable/reachable at all; a richer multi-track
    catalog (Trust/Respect/Rivalry/Fear, etc.) is separate content-authoring
    work, not framework work.

    Idempotent via ``get_or_create`` on both the track (keyed on ``name``) and
    the unlock (keyed on the ``unique_threadweaving_unlock_track`` constraint's
    natural key: ``target_kind`` + ``unlock_track``).
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.weaving import ThreadWeavingUnlock  # noqa: PLC0415
    from world.relationships.constants import TrackSign  # noqa: PLC0415
    from world.relationships.models import RelationshipTrack  # noqa: PLC0415

    track, _ = RelationshipTrack.objects.get_or_create(
        name="Devotion",
        defaults={
            "slug": "devotion",
            "description": (
                "Depth of bond between two souls — the axis Soul Tether capstones anchor to."
            ),
            "sign": TrackSign.POSITIVE,
        },
    )
    unlock, _ = ThreadWeavingUnlock.objects.get_or_create(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        defaults={"xp_cost": 50},  # baseline cost; staff may tune
    )
    return RelationshipTrackThreadUnlockResult(track=track, unlock=unlock)


def seed_starter_magic_story() -> None:
    """Seed the entire magic-story pipeline slice content set.

    Composes the per-phase helpers in dependency order:

      1. seed_canonical_affinities() — the 3 magic Affinities
      2. seed_canonical_resonances() — Celestial (Light/Sanctity/Radiance) + Abyssal (Dissolution)
     RC1. _seed_affinity_interactions() — 9 directed AffinityInteraction rows (needs affinities)
     RC1. _seed_resonance_environment_config() — ResonanceEnvironmentConfig singleton
      B. _seed_hallowed_reaction_conditions() — 5 OPPOSED reaction conditions
      C. _seed_hallowed_achievement_bridge() — stats, rules, achievements
                                                (needs reaction conditions)
      A. _seed_endure_hallowed_ground_check() — CheckType + resolution spine
                                                (via seed_check_resolution_tables)
     RC4. _seed_resonance_environment_rooms() — 3 cascade rooms (needs resonances)
      F. _seed_hallowed_threshold_story() — Story + Chapter + Episodes + Beats + Transitions + TROs

    All sub-helpers are idempotent (get_or_create at every layer), so the
    orchestrator itself is idempotent. Re-running on an edited DB preserves
    edits (per project seed rule: never update_or_create).
    """
    seed_canonical_affinities()
    seed_canonical_resonances()
    _seed_affinity_interactions()
    _seed_resonance_environment_config()
    _seed_hallowed_reaction_conditions()
    _seed_hallowed_achievement_bridge()
    _seed_endure_hallowed_ground_check()
    _seed_resonance_environment_consequence_pools()  # T12: OPPOSED backfire pools
    _seed_resonance_alignment_boons()  # T13: ALIGNED boon tiers + named buffs
    _seed_resonance_environment_rooms()
    _seed_hallowed_threshold_story()


def seed_magic_dev() -> MagicDevSeedResult:
    """Seed the entire magic cluster in one idempotent call.

    Composes all Phase 1 seed helpers:

    1. ``seed_magic_config()`` — AnimaConfig, SoulfrayConfig, ResonanceGainConfig,
       CorruptionConfig, AudereThreshold, IntensityTier × 3, MishapPoolTier
    2. ``seed_canonical_rituals()`` — Rite of Imbuing, Rite of Atonement, Ritual
       of the Durance (#2121)
    3. ``seed_thread_pull_catalog()`` — ThreadPullCost × 3, ThreadPullEffect × 4,
       canonical Tideborne resonance; then ``seed_thread_survivability_tuning()`` —
       ThreadSurvivabilityTuning × 2 (DR + MAX_HEALTH baseline tuning rows, #1175)
    4. ``author_reference_corruption_content()`` — Wild Hunt (Primal) + Web of
       Spiders (Abyssal) Corruption ConditionTemplates + CORRUPTION_TWIST entries
    5. ``MagicContent.create_all()`` — 6 social action Techniques + 6
       ActionEnhancements
    6. ``seed_facet_thread_unlock()`` — single global FACET ThreadWeavingUnlock
    7. ``seed_starter_magic_story()`` — magic-story pipeline slice (Affinities,
       Resonances, Hallowed Rejection conditions + triggers, Hallowed Threshold story)
    8. ``seed_penetration_contest()`` — penetration CheckType + factor ladder +
       check-scoped ModifierTarget (#767)
    9. ``seed_flee_check()`` — flee CheckType + ModifierTarget + FleeConfig
       singleton + tier modifiers + starter consequence pool (#878)
    10. ``seed_relationship_track_thread_unlock()`` — canonical "Devotion"
        RelationshipTrack + its RELATIONSHIP_TRACK ThreadWeavingUnlock (#2027)
    11. ``wire_soul_tether_content()`` — Soul Tether Rituals (accept_soul_tether,
        soul_tether_rescue), Tether Strain / Soul Tether Active ConditionTemplates,
        and the two reactive TriggerDefinitions (#2027). Previously created only
        in tests/factories — Soul Tether was unreachable in a live game.
    12. ``wire_covenant_lifecycle_rituals()`` — Covenant/org lifecycle Rituals
        (Covenant Formation, Covenant Induction, Call the Banners, Mentor's Vow,
        Renew the Oath, Organization Induction) + the MentorBondConfig singleton
        (#2114). Previously created only in tests/factories — the fully-built
        covenant session machinery was unreachable in a live game.
    13. ``ensure_dramatic_entrance_content()`` — "Grand Entrance" DramaticMomentType,
        flagged ``suggest_on_technique_entrance=True`` (#2183). Without this, the
        technique-entrance suggestion bridge has nothing authored to surface.
    14. ``ensure_portal_travel_content()`` — "Mirror" PortalAnchorKind, the
        "Mirrorwalking" MINOR Gift + "Mirrorwalk" Technique
        (``travel_anchor_kind=Mirror``), its GiftUnlock, and starter Mirror
        PortalAnchor rows in seeded public rooms (#2222). Without this, the
        portal-travel network has no reachable content in a live game.

    The starter Gift/Technique/PathGiftGrant/Tradition catalog formerly seeded
    here at this point (Task 7, #2426) is retired (#2474) — real starter-catalog
    content is lore-repo content loaded via ``load_world_content()`` ahead of
    this orchestrator in the dev-seed flow (``seed_dev_database()``); this
    function no longer authors a synthetic one.

    All writes are idempotent (get_or_create throughout). Re-running on a
    populated database is a no-op; staff edits to existing rows are preserved
    (the MentorBondConfig singleton is the one exception — it is reset to its
    authored defaults on every run, same as other pre-launch tuning knobs).

    Returns:
        MagicDevSeedResult composing all sub-results.
    """
    from world.magic.factories import (  # noqa: PLC0415
        author_reference_corruption_content,
        ensure_dramatic_entrance_content,
        wire_covenant_lifecycle_rituals,
        wire_soul_tether_content,
    )
    from world.magic.services import seed_thread_survivability_tuning  # noqa: PLC0415
    from world.seeds.game_content.combat import (  # noqa: PLC0415
        seed_flee_check,
        seed_penetration_contest,
    )

    config = seed_magic_config()
    rituals = seed_canonical_rituals()
    thread_pull_catalog = seed_thread_pull_catalog()
    seed_thread_survivability_tuning()
    author_reference_corruption_content()
    magic_content = MagicContent.create_all()
    facet_thread_unlock = seed_facet_thread_unlock()
    relationship_track_thread_unlock = seed_relationship_track_thread_unlock()
    seed_starter_magic_story()
    penetration = seed_penetration_contest()
    flee = seed_flee_check()
    magic_checks = MagicContent.seed_magic_checks()
    from world.magic.seeds_cast import (  # noqa: PLC0415
        ensure_technique_cast_content,
        ensure_technique_catalog_content,
    )

    technique_cast_template = ensure_technique_cast_content()
    ensure_technique_catalog_content()
    from world.combat.seeds_offense import ensure_combat_offense_catalog_content  # noqa: PLC0415

    ensure_combat_offense_catalog_content()
    soul_tether_content = wire_soul_tether_content()
    covenant_lifecycle_content = wire_covenant_lifecycle_rituals()
    dramatic_entrance_content = ensure_dramatic_entrance_content()
    ensure_relationship_pull_content()
    from world.seeds.game_content.combos import seed_combo_palette  # noqa: PLC0415

    seed_combo_palette()

    from world.seeds.game_content.elemental_interactions import (  # noqa: PLC0415
        seed_elemental_interactions,
    )

    seed_elemental_interactions()

    ensure_portal_travel_content()

    from world.magic.factories import wire_fall_redemption_content  # noqa: PLC0415

    wire_fall_redemption_content()

    from world.magic.factories import wire_ghost_tutor_content  # noqa: PLC0415

    wire_ghost_tutor_content()

    return MagicDevSeedResult(
        config=config,
        rituals=rituals,
        thread_pull_catalog=thread_pull_catalog,
        magic_content=magic_content,
        facet_thread_unlock=facet_thread_unlock,
        penetration=penetration,
        flee=flee,
        magic_checks=magic_checks,
        technique_cast_template=technique_cast_template,
        relationship_track_thread_unlock=relationship_track_thread_unlock,
        soul_tether_content=soul_tether_content,
        covenant_lifecycle_content=covenant_lifecycle_content,
        dramatic_entrance_content=dramatic_entrance_content,
    )
