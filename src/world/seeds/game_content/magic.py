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
import logging
from typing import TYPE_CHECKING

from world.magic.seeds_checks import MagicCheckContentResult

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionEnhancement
    from actions.models.action_templates import ActionTemplate
    from actions.models.consequence_pools import ConsequencePool
    from world.classes.models import Path
    from world.conditions.models import CapabilityType, ConditionStage, ConditionTemplate
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
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

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
        from world.magic.factories import GiftFactory  # noqa: PLC0415
        from world.magic.models import EffectType, Technique  # noqa: PLC0415
        from world.magic.seeds_resonance import reference_resonance  # noqa: PLC0415
        from world.magic.specialization.models import TechniqueVariant  # noqa: PLC0415

        gift = GiftFactory(name="Social Arts")

        # The gift's supported set stays EMPTY -- empty means unrestricted since
        # #2968, so wiring a resonance in would narrow the gift, not widen it.
        # This used to mint a "Social Influence" Resonance under a "Social"
        # Affinity, which is neither authored nor claimable, and which perturbed
        # the resonance catalog mid-seed so later steps were not idempotent
        # (#2967). The #1581 variants below take an authored resonance instead.

        # Ensure a minimal effect_type exists for social techniques.
        # get_or_create so re-runs don't create duplicates.
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
        resonance = reference_resonance(
            TechniqueVariant.objects.filter(parent_technique__in=seeded_gift_techniques)
        )
        for technique in seeded_gift_techniques:
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


def _resolve_hallowed_reaction_conditions() -> dict[str, ConditionTemplate]:
    """Resolve the 5 reaction ConditionTemplates for the Hallowed Threshold pipeline.

    These conditions are applied on different check outcomes when an
    Abyssal-aligned caster uses a technique in a Celestial-aura room:
      Critical Success -> Tempered Against Light
      Success          -> Singed
      Failure          -> Burning
      Critical Failure -> Hallowed Burn + Cast Disrupted

    Burning may already exist (factory-created in some tests); get_or_create
    reuses an existing row with the same name.

    ``conditions.ConditionCategory``/``conditions.ConditionTemplate`` are
    content-repo-owned (#2698) — looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. Returns a dict of ``{name: ConditionTemplate}``
    for whichever of the 5 are actually present (authored, or sampled) — a
    name absent from the dict means it isn't there yet.

    #2973: SINGLE SOURCE OF TRUTH for the authored_or_sample-by-name
    resolution of these 5 templates — both
    ``_seed_hallowed_reaction_conditions()`` (the test-fixture builder) and
    ``_seed_resonance_environment_consequence_pools()`` (the KEEP-side
    production resolver) call this rather than each re-stating the
    category/defaults dict, so the two can't silently drift apart on the
    sample-content path.
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    # Ensure a "Magical" category exists. Reuse if already present.
    category = authored_or_sample(
        ConditionCategory,
        {
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
        name="Magical",
    )

    conditions: dict[str, ConditionTemplate] = {}
    for spec in _HALLOWED_REACTION_SPECS:
        template = authored_or_sample(
            ConditionTemplate,
            {
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
            name=spec["name"],
        )
        if template is not None:
            conditions[spec["name"]] = template
    return conditions


def _seed_hallowed_reaction_conditions() -> dict[str, ConditionTemplate]:
    """Seed the 5 reaction conditions for the Hallowed Threshold pipeline.

    Thin wrapper over ``_resolve_hallowed_reaction_conditions()`` (the single
    source of truth for the authored_or_sample-by-name resolution) — kept as
    its own name/signature because it's the public test-fixture builder suites
    import directly.

    #2973: no longer called from ``seed_starter_magic_story()`` — the 5
    conditions are lore-repo content, so the production seeder resolves them
    itself via ``_resolve_hallowed_reaction_conditions()``, called from
    ``_seed_resonance_environment_consequence_pools()``. This function
    survives as an importable test-fixture builder; suites that need the 5
    conditions call it directly in their own setup.
    """
    return _resolve_hallowed_reaction_conditions()


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


def _build_hallowed_backfire_pool(
    pool_name: str,
    description: str,
    outcome_map: dict[str, CheckOutcome],
    cond_map: dict[str, ConditionTemplate],
) -> ConsequencePool:
    """Create (or fetch) one OPPOSED backfire pool and wire its Consequence/effect rows.

    Extracted from ``_seed_resonance_environment_consequence_pools`` (a module-level
    function keeps its branch count off that function's own C901 budget). See that
    function's docstring for the full dependency/skip-on-missing-condition contract.
    """
    from actions.models import ConsequencePool, ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
    from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415

    pool, _ = ConsequencePool.objects.get_or_create(
        name=pool_name,
        defaults={"description": description},
    )

    # --- Single-effect outcomes: every tier except Critical Failure ---
    # Derived inline from the single source of truth (no separate map constant).
    for outcome_name, condition_name in HALLOWED_REACTION_CONDITION_NAMES.items():
        if outcome_name == _CRIT_FAIL_TIER:
            continue
        condition = cond_map.get(condition_name)
        if condition is None:
            continue
        outcome = outcome_map[outcome_name]
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
        condition = cond_map.get(cond_name)
        if condition is None:
            continue
        # SOFT NATURAL KEY: (consequence, effect_type, condition_template) is
        # functionally unique here but NOT DB-enforced (pre-existing model-wide
        # gap; out of scope for this seed task — tracked separately).
        ConsequenceEffect.objects.get_or_create(
            consequence=crit_fail_consequence,
            effect_type=CheckEffectType.APPLY_CONDITION,
            condition_template=condition,
            defaults={"execution_order": order},
        )

    return pool


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
    - _seed_endure_hallowed_ground_check() (ensures the resolution-spine
      CheckOutcome rows via seed_check_resolution_tables)

    Resolves its own 5 reaction ``ConditionTemplate`` rows by name via
    ``_resolve_hallowed_reaction_conditions()`` (content-repo-owned, #2698)
    rather than depending on ``_seed_hallowed_reaction_conditions()`` having
    run first — that function is no longer part of the production seeder
    path (#2973); it survives only as a test-fixture builder suites call
    directly (and itself now delegates to the same resolver, so the two
    can't drift apart). Any of the 5 may be absent (the lookup logs the miss
    rather than raising).

    Idempotent: get_or_create keyed on stable names at every layer.  Duplicate
    ConsequencePoolEntry rows are prevented by the (pool, consequence) unique
    constraint; duplicate ConsequenceEffect rows are guarded explicitly.

    ``ConditionTemplate`` is content-repo-owned (#2698); an outcome tier whose
    condition isn't authored gets its Consequence/ConsequencePoolEntry rows
    (config) but skips the APPLY_CONDITION effect that would need the missing
    condition — the pool still seeds, just without teeth for that tier.
    """
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import AffinityInteraction  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    # --- Fetch CheckOutcome tiers (seeded by the resolution spine via
    # _seed_endure_hallowed_ground_check -> seed_check_resolution_tables) ---
    outcome_map: dict[str, CheckOutcome] = {}
    for name in (_CRITICAL_SUCCESS, "Success", "Failure", _CRITICAL_FAILURE):
        outcome_map[name] = CheckOutcome.objects.get(name=name)

    # --- Resolve the 5 reaction ConditionTemplates by name (content-repo-owned,
    # #2698). _resolve_hallowed_reaction_conditions() is the single source of
    # truth for this authored_or_sample-by-name lookup — it logs a warning and
    # omits a name from the returned map when it isn't authored and
    # SEED_SAMPLE_CONTENT is off, or invents a sample row (from
    # _HALLOWED_REACTION_SPECS) when sampling is on. A name missing from the
    # map is simply absent from it; callers below skip the APPLY_CONDITION
    # effect wiring for it. ---
    cond_map: dict[str, ConditionTemplate] = _resolve_hallowed_reaction_conditions()

    # --- Build both pools ---
    abyssal_celestial_pool = _build_hallowed_backfire_pool(
        _ABYSSAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for an Abyssal caster working magic in a Celestial place.",
        outcome_map,
        cond_map,
    )
    primal_celestial_pool = _build_hallowed_backfire_pool(
        _PRIMAL_CELESTIAL_POOL_NAME,
        "Backfire consequences for a Primal caster working magic in a Celestial place.",
        outcome_map,
        cond_map,
    )

    # --- Wire AffinityInteraction.consequence_pool for pair #4 and #7 ---
    # Affinity is content-repo-owned (#2698); AffinityInteraction depends on
    # it existing (seeded by _seed_affinity_interactions(), which itself
    # skips a pairing whose Affinity is absent) — so both are resolved via
    # filter().first() and this wiring step is skipped rather than raising
    # when either canonical Affinity or its pairing isn't there.
    abyssal = Affinity.objects.filter(name="Abyssal").first()
    primal = Affinity.objects.filter(name="Primal").first()
    celestial = Affinity.objects.filter(name="Celestial").first()
    if abyssal is None or primal is None or celestial is None:
        return

    pair4 = AffinityInteraction.objects.filter(
        source_affinity=abyssal,
        environment_affinity=celestial,
    ).first()
    if pair4 is not None and pair4.consequence_pool_id != abyssal_celestial_pool.pk:
        pair4.consequence_pool = abyssal_celestial_pool
        pair4.save(update_fields=["consequence_pool"])

    pair7 = AffinityInteraction.objects.filter(
        source_affinity=primal,
        environment_affinity=celestial,
    ).first()
    if pair7 is not None and pair7.consequence_pool_id != primal_celestial_pool.pk:
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
        "name": "Abyssal Resonance - Minor Attunement",
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
        "name": "Abyssal Resonance - Deep Attunement",
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

    ``ConditionCategory``/``ConditionTemplate`` are content-repo-owned (#2698)
    — looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on. A
    band whose template isn't authored has its ``ResonanceAlignmentBoonTier``
    skipped below (the tier's ``condition_template`` FK is required).
    """
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.magic.models.resonance_environment import (  # noqa: PLC0415
        AffinityInteraction,
        ResonanceAlignmentBoonTier,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    # --- Positive "Magical Boon" ConditionCategory for buff templates ---
    # MUST be separate from the negative "Magical" category (used by injury conditions).
    # is_negative=False is load-bearing: services/views count and filter positive vs negative
    # conditions by this flag (see conditions/services.py only_negative filter and
    # conditions/views.py positive/negative counting).
    category = authored_or_sample(
        ConditionCategory,
        {
            "description": (
                "Positive magical conditions from resonance alignment and aura attunement."
            ),
            "is_negative": False,
            "display_order": 10,
        },
        name=_MAGICAL_BOON_CATEGORY_NAME,
    )

    # --- Seed the two boon ConditionTemplates ---
    # DurationType.PERMANENT + default_duration_value=0: persists until cleared by the
    # movement service on the next move (no inherent expiry timer).
    template_map: dict[str, ConditionTemplate] = {}
    for spec in _ABYSSAL_BOON_SPECS:
        template = authored_or_sample(
            ConditionTemplate,
            {
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
            name=spec["name"],
        )
        if template is not None:
            template_map[spec["band"]] = template

    # --- Fetch pair #5: Abyssal → Abyssal (ALIGNED) ---
    # Affinity is content-repo-owned (#2698); skip the boon tiers rather than
    # raising when the canonical Affinity or its self-pairing isn't there.
    abyssal = Affinity.objects.filter(name="Abyssal").first()
    if abyssal is None:
        return
    pair5 = AffinityInteraction.objects.filter(
        source_affinity=abyssal,
        environment_affinity=abyssal,
    ).first()
    if pair5 is None:
        return

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
        condition_template = template_map.get(band)
        if condition_template is None:
            continue
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
        "achievement_slug": "hallowed-hardened",
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
        "achievement_slug": "touched-by-light",
        "achievement_description": "Light glanced your skin. You carry a faint mark.",
        "notification_level": "personal",
    },
    {
        "condition_name": _HALLOWED_BURN,
        "stat_key": "conditions.hallowed_burn.gained",
        "stat_name": "Hallowed Burn Gained",
        "achievement_name": "Cast Out by the Light",
        "achievement_slug": "cast-out-by-the-light",
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

        StatDefinition → ConditionStatRule → Achievement → AchievementStatRequirement

    Discoveries fire automatically via the existing achievements engine when
    the first character earns each Achievement.

    Depends on the 3 referenced ConditionTemplate rows (Tempered Against
    Light / Singed / Hallowed Burn) already existing — content-repo-owned
    (#2698), so a given spec's condition may not exist; that spec is skipped
    entirely (stat/rule/achievement all hang off the condition existing). In
    the production path those rows come from
    ``_seed_resonance_environment_consequence_pools()`` (which resolves them
    by name via ``authored_or_sample``); a test-fixture caller of this
    function directly should seed them first, e.g. via
    ``_seed_hallowed_reaction_conditions()``.

    ``achievements.StatDefinition`` is ALSO content-repo-owned (#2698) —
    looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on. A
    spec whose stat isn't authored/sampled skips its rule/achievement too
    (``ConditionStatRule.stat`` is a required FK).

    #2973: no longer called from ``seed_starter_magic_story()`` — the stat/
    achievement bridge rows are lore-repo content. This function survives as
    an importable test-fixture builder only.
    """
    from world.achievements.constants import (  # noqa: PLC0415
        ComparisonType,
        ConditionEventType,
    )
    from world.achievements.models import (  # noqa: PLC0415
        Achievement,
        AchievementStatRequirement,
        ConditionStatRule,
        StatDefinition,
    )
    from world.conditions.models import ConditionTemplate  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    for spec in _HALLOWED_ACHIEVEMENT_BRIDGE_SPECS:
        condition = ConditionTemplate.objects.filter(name=spec["condition_name"]).first()
        if condition is None:
            continue
        stat = authored_or_sample(
            StatDefinition,
            {
                "name": spec["stat_name"],
                "description": (
                    f"Count of times this character has gained {spec['condition_name']}."
                ),
            },
            key=spec["stat_key"],
        )
        if stat is None:
            continue
        authored_or_sample(
            ConditionStatRule,
            {"increment_amount": 1},
            stat=stat,
            condition=condition,
            event_type=ConditionEventType.GAINED,
        )
        notification_level = spec["notification_level"]
        achievement = authored_or_sample(
            Achievement,
            {
                "name": spec["achievement_name"],
                "description": spec["achievement_description"],
                "hidden": True,
                "notification_level": notification_level,
                "is_active": True,
            },
            slug=spec["achievement_slug"],
        )
        if achievement is None:
            continue
        authored_or_sample(
            AchievementStatRequirement,
            {"description": ""},
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
      - "The Hallowed Threshold (Low)"   — the first authored Celestial resonance,
        magnitude=10
      - "The Hallowed Threshold (High)"  — the same Celestial resonance, magnitude=80
      - "The Resonant Sanctum (Aligned)" — the first authored Abyssal resonance,
        magnitude=60

    Idempotent at every layer:
      - rooms: filter().first() + create_object(nohome=True) when absent
      - RoomProfile: get_or_create
      - LocationValueModifier: tag_room_resonance uses update_or_create keyed on
        (room_profile, resonance, source) then we set .value + .save() to tune
        magnitude — re-runs restore the desired value.

    #2973: no longer called from ``seed_starter_magic_story()`` — the 3 rooms
    (+ their resonance tags) ride the #2451 grid-bundle mechanism as lore-repo
    content; "Hallowed Rejection" rides an ordinary lore fixture. This function
    survives as a test-fixture builder; the story-pipeline suite calls it
    directly in its own setup.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.magic.seeds_resonance import first_authored_resonance  # noqa: PLC0415
    from world.magic.services.gain import tag_room_resonance  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    # ----- Hallowed Rejection marker (flavor condition for the story) -----
    # ConditionCategory/ConditionTemplate are content-repo-owned (#2698) —
    # looked up rather than invented unless SEED_SAMPLE_CONTENT is on. The
    # cascade rooms below don't depend on this marker existing.
    category = authored_or_sample(
        ConditionCategory,
        {
            "description": "Magical conditions arising from spellcasting and aura interactions.",
            "is_negative": True,
            "display_order": 0,
        },
        name="Magical",
    )
    authored_or_sample(
        ConditionTemplate,
        {
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
        name="Hallowed Rejection",
    )

    # ----- Rooms with cascade resonance -----
    # These demo rooms need *a* Celestial and *an* Abyssal resonance, not any
    # particular one — they exercise the aligned/opposed cascade poles. They
    # used to name the invented "Light"/"Dissolution" (#2967); they now take
    # whichever the content repo authored, and skip when it authored none.
    celestial_resonance = first_authored_resonance("Celestial")
    abyssal_resonance = first_authored_resonance("Abyssal")
    if celestial_resonance is None or abyssal_resonance is None:
        return

    room_specs = [
        ("The Hallowed Threshold (Low)", celestial_resonance, _CELESTIAL_LOW_MAGNITUDE),
        ("The Hallowed Threshold (High)", celestial_resonance, _CELESTIAL_HIGH_MAGNITUDE),
        ("The Resonant Sanctum (Aligned)", abyssal_resonance, _ABYSSAL_ALIGNED_MAGNITUDE),
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

    Test-fixture builder only (#2973) — no longer called by
    ``seed_starter_magic_story()`` or ``seed_magic_dev()``. This story is
    scaffolding for the story-pipeline test suite (`test_magic_seed.py`'s
    ``SeedHallowedThresholdStoryTests`` and
    ``integration_tests/test_magic_story_pipeline.py``), which call it
    directly in their own setup; it has no non-test consumer and no
    lore-repo destination.

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

    Every beat below requires one of the 4 reaction ``ConditionTemplate``
    rows (content-repo-owned, #2698; seeded by ``_seed_hallowed_reaction_conditions``).
    The whole DAG is skipped — no Story/Chapter/Episode/Beat/Transition rows
    at all — when any of the 4 isn't authored, rather than building a partial
    story with beats missing their routing condition.
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

    needed_condition_names = {_TEMPERED_AGAINST_LIGHT, "Singed", "Burning", _HALLOWED_BURN}
    cond_map: dict[str, ConditionTemplate] = {
        template.name: template
        for template in ConditionTemplate.objects.filter(name__in=needed_condition_names)
    }
    if not needed_condition_names.issubset(cond_map):
        return

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
        condition = cond_map[cond_name]
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

    Content-repo-owned (#2698): looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. Idempotent. Re-running on a populated DB is
    a no-op for these rows. Other magic content (resonances, room aura, etc.)
    depends on these existing — every consumer downstream of this (in this
    module and elsewhere) is written to skip gracefully, never crash, when a
    canonical Affinity is absent.
    """
    from world.magic.models.affinity import Affinity  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    for name in ("Celestial", "Primal", "Abyssal"):
        authored_or_sample(Affinity, {}, name=name)


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

    Affinity is content-repo-owned (#2698): a row missing from
    ``affinity_cache`` (content repo doesn't author it, sample content off)
    skips that pairing rather than raising ``KeyError``.
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
        if src_name not in affinity_cache or env_name not in affinity_cache:
            continue
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

    # checks.CheckType is content-repo-owned (#2698) — ensure_magic_check_types()
    # omits an entry whose category/row isn't authored. resilience_check_type is
    # a required FK on SoulfrayConfig (a pk=1 singleton), so the singleton itself
    # is skipped entirely (never created with a null FK) when the Magical
    # Endurance CheckType isn't authored and SoulfrayConfig doesn't already exist.
    resilience_check_type = ensure_magic_check_types().get(MAGICAL_ENDURANCE_CHECK_TYPE_NAME)
    soulfray_config = SoulfrayConfig.objects.filter(pk=1).first()
    if soulfray_config is None and resilience_check_type is not None:
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
    # Content-repo-owned (#2698): looked up rather than invented unless
    # SEED_SAMPLE_CONTENT is on. A missing tier is simply absent from the
    # returned dict — nothing downstream in the seeder chain asserts a
    # specific tier exists.
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    intensity_tiers: dict[str, IntensityTier] = {}
    for tier_name, threshold, control_mod in _INTENSITY_TIERS:
        tier = authored_or_sample(
            IntensityTier,
            {
                "threshold": threshold,
                "control_modifier": control_mod,
                "description": f"{tier_name} intensity level.",
            },
            name=tier_name,
        )
        if tier is None:
            continue
        intensity_tiers[tier_name] = tier

    major_tier = intensity_tiers.get("Major")

    # --- Soulfray condition + stages (needed for AudereThreshold.minimum_warp_stage) ---
    # SoulfrayContentFactory() is idempotent — uses get_or_create internally.
    # conditions.ConditionTemplate/ConditionStage are content-repo-owned (#2698);
    # soulfray_content.stages is empty when Soulfray isn't authored and
    # SEED_SAMPLE_CONTENT is off — ripping_stage stays None in that case.
    soulfray_content = SoulfrayContentFactory()
    ripping_stage = next(
        (
            s
            for s in soulfray_content.stages
            if s.name == "Ripping"  # noqa: STRING_LITERAL
        ),
        None,
    )

    # --- AudereThreshold (singleton, no get_or_create on factory) ---
    # Skipped when the "Major" IntensityTier or the Soulfray "Ripping" stage
    # (both content-repo-owned, #2698) isn't available — check_audere_eligibility()'s
    # own gate #1 already tolerates a missing AudereThreshold (Audere just stays
    # inactive), so this degrades the same way a real deploy without the row
    # authored would.
    audere_threshold = None
    if major_tier is not None and ripping_stage is not None:
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

    Content-repo-owned (#2698): each Ritual is only invented (by calling its
    factory, preserving side effects like the Durance's companion
    RitualLiturgy post_generation hook) when it's already authored or
    ``SEED_SAMPLE_CONTENT`` is on; otherwise it's skipped (logged, ``None``)
    rather than fabricated.

    Returns:
        RitualSeedResult dataclass with all three ritual instances (a field
        is ``None`` when its content isn't authored and sample content is off).
    """
    from world.magic.factories import (  # noqa: PLC0415
        AtonementRitualFactory,
        ImbuingRitualFactory,
        RitualOfTheDuranceFactory,
    )
    from world.magic.models import Ritual  # noqa: PLC0415
    from world.seeds.sample_content import sample_content_enabled  # noqa: PLC0415

    def _authored_ritual_or_sample(factory_cls: type, name: str) -> Ritual | None:
        if sample_content_enabled() or Ritual.objects.filter(name=name).exists():
            return factory_cls()
        logger.warning(
            "Ritual matching %r is not in the content repo. Skipping. Author the "
            "row in the content repo and re-press the Big Button, or set "
            "ARXII_SEED_SAMPLE_CONTENT=1 to have the seeder invent a sample one "
            "(see #2698).",
            {"name": name},
        )
        return None

    imbuing = _authored_ritual_or_sample(ImbuingRitualFactory, "Rite of Imbuing")
    atonement = _authored_ritual_or_sample(AtonementRitualFactory, "Rite of Atonement")
    durance = _authored_ritual_or_sample(RitualOfTheDuranceFactory, "Ritual of the Durance")
    return RitualSeedResult(
        rite_of_imbuing=imbuing,
        rite_of_atonement=atonement,
        ritual_of_the_durance=durance,
    )


# ---------------------------------------------------------------------------
# Task 1.3 — seed_thread_pull_catalog()
# ---------------------------------------------------------------------------

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
    - the reference TRAIT pull effects, keyed to the first authored Resonance
    - CapabilityType "endurance" — used by the CAPABILITY_GRANT effect
    - ThreadPullEffect rows:
        - FLAT_BONUS (tier=1, min_thread_level=0, flat_bonus_amount=10)
        - INTENSITY_BUMP (tier=2, min_thread_level=0, intensity_bump_amount=10)
        - VITAL_BONUS (tier=0, min_thread_level=0, vital_bonus_amount=10, MAX_HEALTH)
        - CAPABILITY_GRANT (tier=3, min_thread_level=5, capability=endurance)

    The reference resonance is whichever the content repo authored first
    (#2967) — the seeder never invents one. When none is authored, the four
    ThreadPullEffect rows (which need a real ``resonance`` FK) are skipped
    and ``canonical_resonance`` is ``None`` on the returned result. The
    "endurance" ``CapabilityType`` is likewise content-repo-owned (#2698); when
    it's missing, only the CAPABILITY_GRANT row is skipped — FLAT_BONUS/
    INTENSITY_BUMP/VITAL_BONUS don't need it.

    Returns:
        ThreadPullCatalogResult dataclass with all created/fetched instances.
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget  # noqa: PLC0415
    from world.magic.factories import ThreadPullCostFactory  # noqa: PLC0415
    from world.magic.models.threads import ThreadPullEffect  # noqa: PLC0415
    from world.magic.seeds_resonance import reference_resonance  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

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

    # --- Reference resonance for the TRAIT rows — authored, never invented ---
    # This used to invent a "Tideborne" Resonance under a "Primal (Tideborne)"
    # Affinity (#2967), so the reference TRAIT pull effects hung off a resonance
    # no character could ever hold. It now follows whichever authored resonance
    # the existing TRAIT rows already point at, and only picks a fresh one when
    # there are none — otherwise a re-press after the catalog grew would seed a
    # second reference set beside the first.
    resonance = reference_resonance(ThreadPullEffect.objects.filter(target_kind=TargetKind.TRAIT))

    # --- CapabilityType for CAPABILITY_GRANT — content-repo-owned (#2698) ---
    capability = authored_or_sample(
        CapabilityType,
        {"description": "Endurance capability — used by thread pull catalog."},
        name=_CATALOG_CAPABILITY_NAME,
    )

    # --- ThreadPullEffect rows (natural key: target_kind, resonance, tier, min_thread_level) ---
    # Using direct ORM get_or_create per task spec to avoid non-idempotent factory calls.
    # Skipped entirely when the catalog Resonance above isn't available.
    pull_effects: dict[str, ThreadPullEffect] = {}
    if resonance is None:
        return ThreadPullCatalogResult(
            pull_costs=pull_costs,
            canonical_resonance=None,
            pull_effects=pull_effects,
        )

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

    if capability is not None:
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

    Creates one 4-tier chain per **authored** resonance. Tier 0 is passive
    (always-on); tiers 1-3 are paid pulls. All effects are
    survivability-oriented: VITAL_BONUS to DAMAGE_TAKEN_REDUCTION / DEATH_SAVE
    / KNOCKOUT_RESIST, plus RESISTANCE.

    ``ThreadPullEffect`` is seeder-owned tuning data, not ``CONTENT_MODELS``
    content, so covering the whole catalog is free. It used to cover four named
    resonances — "Light", "Sanctity", "Radiance", "Dissolution" — which the
    seeder invented and which no player could hold (#2967); a relationship
    thread woven at any real resonance therefore had no pull effects at all.

    Idempotent via get_or_create. The relationship_bond_modulation saturating
    curve (#1849) scales these by bond strength when the target IS the threaded
    person or is hostile to them.
    """
    from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget  # noqa: PLC0415
    from world.magic.models import ThreadPullEffect  # noqa: PLC0415
    from world.magic.seeds_resonance import authored_resonances  # noqa: PLC0415

    for resonance in authored_resonances():
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

#: Starter public rooms that get a Mirror anchor so the network has real,
#: reachable nodes on a fresh Big Button run — not just catalog rows (#2222
#: "Seed content"). "The Wanderer's Rest" (the canonical fallback starting
#: room every fresh character passes through) is guaranteed by calling
#: ``ensure_canonical_fallback_room()`` directly. The two magic-story cascade
#: rooms below are no longer seeded by ``seed_magic_dev()`` (#2973 stripped
#: ``_seed_resonance_environment_rooms()`` out of ``seed_starter_magic_story()``
#: — it survives only as a test-fixture builder). In production these two rooms
#: exist only once the lore repo's #2451 grid bundle authors rooms under these
#: same ``db_key``s; until then — or if this function is ever called standalone
#: ahead of that content load — they're resolved defensively via
#: ``filter().first()`` and skipped (never crash) when absent. No other named
#: public room exists in production seed content today (verified — grepped
#: every ``game_content``/``seeds`` module for room creation).
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
    """Idempotently place the Mirror portal network's starter anchors (#2222).

    Looks up the ``PortalAnchorKind`` "Mirror" (authored in the content repo)
    and get-or-creates a Mirror ``PortalAnchor`` in the canonical fallback room
    plus each seeded public room in ``_MIRROR_ANCHOR_ROOM_SPECS``, so the mirror
    network is reachable rather than merely cataloged. Idempotent; re-running on
    a populated DB preserves staff edits (never ``update_or_create``).

    **Seeds no gift, technique or resonance (#2967).** It used to invent a
    "Reflection" Resonance, a MINOR ``Gift`` "Mirrorwalking" carrying it, a
    ``Technique`` "Mirrorwalk" and an XP ``GiftUnlock`` — a placeholder set
    ruled out on 2026-08-04 ("at best Mirrorwalk is a placeholder... we can
    obliterate that"). The Gift was the only one in the catalog with a non-empty
    resonance set, and its one resonance was the invented Reflection, so it was
    also the only gift the weave gate could refuse outright.

    Portal travel itself stays fully built: the gate is *knowing a technique
    whose ``travel_anchor_kind`` is set*, and that technique is authored content
    the lore repo owns. Until one is authored these anchors stand unused, which
    is the honest state — a seeded placeholder made it look shipped.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415

    from world.magic.models import PortalAnchorKind  # noqa: PLC0415
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    mirror_kind = authored_or_sample(
        PortalAnchorKind,
        {
            "description": (
                "A tall, silvered mirror: a threshold to every other mirror open on its network."
            ),
            "arrival_verb": "steps out of",
            "departure_verb": "steps into",
        },
        name=_MIRROR_ANCHOR_KIND_NAME,
    )
    if mirror_kind is None:
        return

    # The canonical fallback room is guaranteed; the magic-story cascade rooms
    # are resolved defensively (skip if absent).
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


def ensure_technique_training_content():
    """Seed config + sample content for check-based technique training (#2727).

    The ``TrainingOutcomeAward`` rows are config (staff-tunable tuning
    data, not lore-repo content), so they're always seeded. The
    "Arcane Theory" Skill/Trait, "Technique Training" CheckType, and
    their CheckTypeTrait composition rows ARE content models
    (``CONTENT_MODELS`` per #2698) — they're looked up first and only
    invented under ``SEED_SAMPLE_CONTENT`` (off by default) via
    ``authored_or_sample``. In a real deploy they come from the lore
    repo; in a test/dev DB with sampling on, a stand-in is created.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.magic.models import TrainingOutcomeAward  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import (  # noqa: PLC0415
        CheckOutcome,
        Trait,
        TraitCategory,
        TraitType,
    )

    # 1. Arcane Theory skill + backing trait (content models — sample only).
    arcane_trait = authored_or_sample(
        Trait,
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.MAGIC,
            "is_public": True,
        },
        name="Arcane Theory",
    )
    if arcane_trait is not None:
        Skill.objects.get_or_create(
            trait=arcane_trait,
            defaults={
                "tooltip": "Understanding the theoretical underpinnings of magical techniques.",
                "display_order": 0,
                "is_active": True,
            },
        )

    # 2. intellect stat trait (content model — sample only, may already exist
    # from CG seed).
    intellect_trait = authored_or_sample(
        Trait,
        defaults={
            "trait_type": TraitType.STAT,
            "category": TraitCategory.MENTAL,
            "is_public": True,
        },
        name="intellect",
    )

    # 3. Magic check category (content model — sample only).
    category = authored_or_sample(
        CheckCategory,
        defaults={
            "description": "Checks involving magical theory and practice.",
            "display_order": 40,
        },
        name="Magic",
    )

    # 4. Technique Training CheckType (content model — sample only).
    check_type = None
    if category is not None:
        check_type = authored_or_sample(
            CheckType,
            defaults={"is_active": True, "display_order": 10},
            name="Technique Training",
            category=category,
        )
    if check_type is not None and intellect_trait is not None and arcane_trait is not None:
        weight = Decimal("1.0")
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type,
            trait=intellect_trait,
            defaults={"weight": weight},
        )
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type,
            trait=arcane_trait,
            defaults={"weight": weight},
        )

    # 5. TrainingOutcomeAward rows (config, NOT content models — always seeded).
    award_defaults = {
        "Critical Failure": Decimal("0.00"),
        "Failure": Decimal("0.00"),
        "Partial Success": Decimal("0.50"),
        "Success": Decimal("1.00"),
        "Critical Success": Decimal("1.50"),
    }
    for name, mult in award_defaults.items():
        outcome = CheckOutcome.objects.filter(name=name).first()
        if outcome is not None:
            TrainingOutcomeAward.objects.update_or_create(
                outcome_tier=outcome,
                defaults={"dev_point_multiplier": mult},
            )


@dataclass
class MagicDevSeedResult:
    """Returned by seed_magic_dev().

    Composes all Phase 1 seed results into one dataclass.
    ``author_reference_corruption_content()`` returns None so it is not
    represented here; callers can query Wild Hunt / Web of Spiders rows directly.
    ``MagicContent.create_all()`` (Social Arts Gift/Techniques/ActionEnhancements)
    is no longer called from this orchestrator (#2973 — content-repo-owned), so
    there is no ``magic_content`` field either; callers needing that shape build
    it directly via ``MagicContent.create_all()`` as a test fixture.
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

    Content-repo-owned (#2698): looked up rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.weaving import ThreadWeavingUnlock  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    unlock = authored_or_sample(
        ThreadWeavingUnlock,
        {"xp_cost": 50},  # baseline cost; staff may tune
        target_kind=TargetKind.FACET,
    )
    return FacetThreadUnlockResult(unlock=unlock)


def seed_relationship_track_thread_unlock() -> RelationshipTrackThreadUnlockResult:
    """Resolve the RELATIONSHIP_TRACK ThreadWeavingUnlock (+ its backing track).

    Soul Tether formation (``accept_soul_tether`` in
    ``world.magic.services.soul_tether``) gates on the Sinner holding a
    ``CharacterThreadWeavingUnlock`` for ``TargetKind.RELATIONSHIP_TRACK``
    (``_validate_unlock``) before they can weave the RELATIONSHIP_CAPSTONE
    Thread that carries the Hollow. Unlike FACET, ``ThreadWeavingUnlock.unlock_track``
    is a required non-null FK (per-kind CheckConstraint), so this function also
    resolves the "Devotion" ``RelationshipTrack`` to hang the unlock off of —
    both rows are content-repo-owned (#2973) and looked up via
    ``authored_or_sample``, never lazy-created against a real deploy. This is
    the minimum authored content needed for the Rite of the Soul Tether to be
    purchasable/reachable at all; a richer multi-track catalog (Trust/Respect/
    Rivalry/Fear, etc.) is separate content-authoring work, not framework work.

    Idempotent: the track and the unlock (keyed on the
    ``unique_threadweaving_unlock_track`` constraint's natural key:
    ``target_kind`` + ``unlock_track``) are each looked up rather than
    unconditionally created.

    Both the track and the unlock are content-repo-owned (#2698) — looked up
    rather than invented unless ``SEED_SAMPLE_CONTENT`` is on.
    ``ThreadWeavingUnlock.unlock_track`` is a required FK for this kind, so a
    missing "Devotion" track means there is nothing to hang the unlock off
    of; this returns a result with both fields ``None`` in that case.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.weaving import ThreadWeavingUnlock  # noqa: PLC0415
    from world.relationships.constants import TrackSign  # noqa: PLC0415
    from world.relationships.models import RelationshipTrack  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    track = authored_or_sample(
        RelationshipTrack,
        {
            "slug": "devotion",
            "description": (
                "Depth of bond between two souls — the axis Soul Tether capstones anchor to."
            ),
            "sign": TrackSign.POSITIVE,
        },
        name="Devotion",
    )
    if track is None:
        return RelationshipTrackThreadUnlockResult(track=None, unlock=None)
    unlock = authored_or_sample(
        ThreadWeavingUnlock,
        {"xp_cost": 50},  # baseline cost; staff may tune
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
    )
    return RelationshipTrackThreadUnlockResult(track=track, unlock=unlock)


def seed_starter_magic_story() -> None:
    """Seed the entire magic-story pipeline slice content set.

    Composes the per-phase helpers in dependency order:

      1. seed_canonical_affinities() — the 3 magic Affinities
     RC1. _seed_affinity_interactions() — 9 directed AffinityInteraction rows (needs affinities)
     RC1. _seed_resonance_environment_config() — ResonanceEnvironmentConfig singleton
      A. _seed_endure_hallowed_ground_check() — CheckType + resolution spine
                                                (via seed_check_resolution_tables)
     T12. _seed_resonance_environment_consequence_pools() — OPPOSED backfire pools;
                                                resolves the 5 reaction ConditionTemplate
                                                rows by name (content-repo-owned, #2973)
     T13. _seed_resonance_alignment_boons() — ALIGNED boon tiers + named buffs

    #2973: four former phases no longer run here — B (reaction conditions,
    ``_seed_hallowed_reaction_conditions()``), C (achievement bridge,
    ``_seed_hallowed_achievement_bridge()``), RC4 (cascade rooms,
    ``_seed_resonance_environment_rooms()``), and F (the Hallowed Threshold
    story, ``_seed_hallowed_threshold_story()`` — Story + Chapter + Episodes +
    Beats + Transitions + TROs). B/C/RC4 authored content-repo-owned rows the
    seeder shouldn't own; F is scaffolding for one suite with no non-test
    consumer, so it moved to a test fixture rather than lore content. All four
    survive as importable test-fixture builders (the story-pipeline suite
    calls them directly in its own setup) but no longer run as part of this
    orchestrator or ``seed_magic_dev()``. Production content for B/C/RC4
    comes from the lore repo; F has no production destination — it never
    ships.

    All remaining sub-helpers are idempotent (get_or_create at every layer),
    so the orchestrator itself is idempotent. Re-running on an edited DB
    preserves edits (per project seed rule: never update_or_create).
    """
    seed_canonical_affinities()
    _seed_affinity_interactions()
    _seed_resonance_environment_config()
    _seed_endure_hallowed_ground_check()
    _seed_resonance_environment_consequence_pools()  # T12: OPPOSED backfire pools
    _seed_resonance_alignment_boons()  # T13: ALIGNED boon tiers + named buffs


def seed_magic_dev() -> MagicDevSeedResult:
    """Seed the entire magic cluster in one idempotent call.

    Composes all Phase 1 seed helpers:

    1. ``seed_magic_config()`` — AnimaConfig, SoulfrayConfig, ResonanceGainConfig,
       CorruptionConfig, AudereThreshold, IntensityTier × 3, MishapPoolTier
    2. ``seed_canonical_rituals()`` — Rite of Imbuing, Rite of Atonement, Ritual
       of the Durance (#2121)
    3. ``seed_thread_pull_catalog()`` — ThreadPullCost × 3, ThreadPullEffect × 4,
       reference TRAIT rows on the first authored resonance; then
       ``seed_thread_survivability_tuning()`` —
       ThreadSurvivabilityTuning × 2 (DR + MAX_HEALTH baseline tuning rows, #1175)
    4. ``seed_facet_thread_unlock()`` — single global FACET ThreadWeavingUnlock
    5. ``seed_starter_magic_story()`` — magic-story pipeline slice (Affinities,
       AffinityInteractions, OPPOSED backfire pools resolving the 5 reaction
       conditions by name, ALIGNED boon tiers; #2973 — the cascade rooms +
       "Hallowed Rejection", the achievement bridge, and the Hallowed
       Threshold story no longer seed here — the first two are lore-repo
       content, the story is a test fixture with no production destination)
    6. ``seed_penetration_contest()`` — penetration CheckType + factor ladder +
       check-scoped ModifierTarget (#767)
    7. ``seed_flee_check()`` — flee CheckType + ModifierTarget + FleeConfig
       singleton + tier modifiers + starter consequence pool (#878)
    8. ``seed_relationship_track_thread_unlock()`` — RELATIONSHIP_TRACK
       ThreadWeavingUnlock + its backing "Devotion" RelationshipTrack, both
       resolved via ``authored_or_sample`` (content-repo-owned, #2698/#2973) (#2027)
    9. ``wire_soul_tether_content()`` — Soul Tether Rituals (accept_soul_tether,
       soul_tether_rescue), Tether Strain / Soul Tether Active ConditionTemplates,
       and the two reactive TriggerDefinitions (#2027). Previously created only
       in tests/factories — Soul Tether was unreachable in a live game.
    10. ``wire_covenant_lifecycle_rituals()`` — Covenant/org lifecycle Rituals
        (Covenant Formation, Covenant Induction, Call the Banners, Mentor's Vow,
        Renew the Oath, Organization Induction) + the MentorBondConfig singleton
        (#2114). Previously created only in tests/factories — the fully-built
        covenant session machinery was unreachable in a live game.
    11. ``ensure_dramatic_entrance_content()`` — "Grand Entrance" DramaticMomentType,
        flagged ``suggest_on_technique_entrance=True`` (#2183). Without this, the
        technique-entrance suggestion bridge has nothing authored to surface.
    12. ``ensure_portal_travel_content()`` — starter Mirror ``PortalAnchor`` rows
        in seeded public rooms, on the content-authored "Mirror"
        ``PortalAnchorKind`` (#2222). The gift + technique it used to invent were
        removed in #2967; a real travel technique is lore-repo content.

    The starter Gift/Technique/PathGiftGrant/Tradition catalog formerly seeded
    here at this point (Task 7, #2426) is retired (#2474) — real starter-catalog
    content is lore-repo content loaded via ``load_world_content()`` ahead of
    this orchestrator in the dev-seed flow (``seed_dev_database()``); this
    function no longer authors a synthetic one. Nor does ``MagicContent.create_all()``
    — its "Social Arts" Gift + 6 Techniques + 6 ActionEnhancements + variants left
    the production seeder (#2973); ``MagicContent`` survives as a test-fixture
    builder only. Nor does ``author_reference_corruption_content()`` — its 2
    Corruption ConditionTemplates + 12 CORRUPTION_TWIST entries left the
    production seeder too (#2973); it survives as a test-fixture builder the
    ``test_reference_corruption_content.py`` suite calls directly.

    All writes are idempotent (get_or_create throughout). Re-running on a
    populated database is a no-op; staff edits to existing rows are preserved
    (the MentorBondConfig singleton is the one exception — it is reset to its
    authored defaults on every run, same as other pre-launch tuning knobs).

    Returns:
        MagicDevSeedResult composing all sub-results.
    """
    from world.magic.factories import (  # noqa: PLC0415
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
    # #2973: MagicContent.create_all() no longer runs here. Its Gift "Social
    # Arts" + 6 Techniques + 6 ActionEnhancements + variants are content-repo
    # rows the seeder shouldn't author (formerly gated behind
    # sample_content_enabled(), #2698 — now removed outright, not merely
    # ungated). MagicContent survives as a test-fixture builder: the two
    # pipeline suites that need this content (test_social_magic_pipeline.py,
    # test_challenge_pipeline.py) call create_all() directly in their own
    # setUpTestData. Nor does author_reference_corruption_content() — its
    # Corruption ConditionTemplates + CORRUPTION_TWIST entries are content-repo
    # rows too (#2973); test_reference_corruption_content.py calls it directly.
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

    from world.magic.factories import (  # noqa: PLC0415
        ensure_thread_surge_content,
        wire_fall_redemption_content,
    )

    ensure_thread_surge_content()
    wire_fall_redemption_content()

    from world.magic.factories import wire_ghost_tutor_content  # noqa: PLC0415

    wire_ghost_tutor_content()

    from world.mechanics.factories import ensure_team_damage_percent_target  # noqa: PLC0415

    # #2643 — mechanics config (not authored content, see the factory docstring),
    # so it's seeded directly here rather than deferred to lore-repo content.
    ensure_team_damage_percent_target()

    ensure_technique_training_content()

    return MagicDevSeedResult(
        config=config,
        rituals=rituals,
        thread_pull_catalog=thread_pull_catalog,
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
