"""FactoryBoy factories for covenant models."""

from typing import TYPE_CHECKING, NamedTuple

import factory
from factory import django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import (
    MENTOR_BOND_ADJACENCY_OFFSET,
    MENTOR_BOND_BAND_WIDTH,
    MENTOR_BOND_MAX_SIDEKICKS,
    CovenantType,
    DefenseStyle,
    MentorBondAdjusted,
)
from world.covenants.models import (
    CharacterCovenantRole,
    CourtPact,
    Covenant,
    CovenantLevelBonus,
    CovenantLevelThreshold,
    CovenantRank,
    CovenantRite,
    CovenantRiteRolePackage,
    CovenantRole,
    CovenantRoleActionScaling,
    CovenantRoleBonus,
    CovenantRoleDefenseProfile,
    CovenantRoleTechniqueSpecialty,
    GearArchetypeCompatibility,
    MentorBond,
    MentorBondConfig,
)
from world.items.constants import GearArchetype
from world.magic.constants import TechniqueFunction

CHARACTER_SHEET_FACTORY = "world.character_sheets.factories.CharacterSheetFactory"

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.conditions.models import CapabilityType
    from world.magic.models import Resonance, ThreadPullEffect


class CovenantRoleFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRole."""

    class Meta:
        model = CovenantRole
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Role {n}")
    slug = factory.Sequence(lambda n: f"role-{n}")
    covenant_type = CovenantType.DURANCE
    sword_weight = 0
    shield_weight = 0
    crown_weight = 1
    speed_rank = 5
    description = ""


class SubroleCovenantRoleFactory(CovenantRoleFactory):
    """Factory for sub-role CovenantRole instances.

    Generates a valid sub-role: parent_role and resonance are both set,
    and covenant_type is inherited from the parent. Blend weights stay at
    the CovenantRoleFactory default of 0 — sub-roles must not set them
    (#2529; the blend lives on the parent role, see ``blend_weight_for``).

    Optional keyword arguments:
        discovery_achievement: Achievement instance (or None).
        codex_entry: CodexEntry instance (or None).

    When these are omitted the fields remain NULL on the created row
    (both fields are nullable on the model). Pass an explicit instance —
    e.g. from AchievementFactory() / CodexEntryFactory() — to wire them up.
    """

    parent_role = factory.SubFactory(CovenantRoleFactory)
    resonance = factory.SubFactory("world.magic.factories.ResonanceFactory")
    unlock_thread_level = 3
    discovery_achievement = None
    codex_entry = None
    sword_weight = 0
    shield_weight = 0
    crown_weight = 0

    @factory.lazy_attribute
    def covenant_type(self) -> str:
        return self.parent_role.covenant_type


class GearArchetypeCompatibilityFactory(factory_django.DjangoModelFactory):
    """Factory for GearArchetypeCompatibility."""

    class Meta:
        model = GearArchetypeCompatibility
        django_get_or_create = ("covenant_role", "gear_archetype")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    gear_archetype = GearArchetype.HEAVY_ARMOR


class CovenantRoleActionScalingFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRoleActionScaling (#2529, replaces ArchetypeActionScalingFactory)."""

    class Meta:
        model = CovenantRoleActionScaling
        django_get_or_create = ("covenant_role", "action_key")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    action_key = "combat_interpose"
    thread_level_multiplier = 0


class CovenantRoleTechniqueSpecialtyFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRoleTechniqueSpecialty (#2443)."""

    class Meta:
        model = CovenantRoleTechniqueSpecialty
        django_get_or_create = ("covenant_role", "function")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    function = TechniqueFunction.DAMAGE_BUFF_SELF
    multiplier_tenths = 10


class CovenantRoleDefenseProfileFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRoleDefenseProfile (#2533)."""

    class Meta:
        model = CovenantRoleDefenseProfile
        django_get_or_create = ("covenant_role",)

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    style = DefenseStyle.GEAR_SOAK
    gear_additive_tenths = 10


class CovenantFactory(factory_django.DjangoModelFactory):
    """Factory for Covenant."""

    class Meta:
        model = Covenant

    name = factory.Sequence(lambda n: f"Covenant {n}")
    covenant_type = CovenantType.DURANCE
    level = 1
    sworn_objective = "Sworn to test things."


class CovenantRankFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRank — a per-covenant administrative authority tier."""

    class Meta:
        model = CovenantRank

    covenant = factory.SubFactory(CovenantFactory)
    name = factory.Sequence(lambda n: f"Rank {n}")
    tier = factory.Sequence(lambda n: n + 1)
    description = ""
    can_invite = False
    can_kick = False
    can_manage_ranks = False
    can_lead_rituals = False
    can_request_gm = False


class CovenantManagerRankFactory(CovenantRankFactory):
    """A CovenantRank with full administrative capabilities."""

    name = factory.Sequence(lambda n: f"Manager Rank {n}")
    can_invite = True
    can_kick = True
    can_manage_ranks = True
    can_lead_rituals = True
    can_request_gm = True


class CharacterCovenantRoleFactory(factory_django.DjangoModelFactory):
    """Factory for CharacterCovenantRole.

    Note: covenant.covenant_type and covenant_role.covenant_type both
    default to DURANCE. If a test wants BATTLE, both kwargs must be
    set explicitly.

    No django_get_or_create — the model's unique constraint is partial
    (only enforced when left_at IS NULL), so get_or_create on
    (character_sheet, covenant) would silently return an existing
    *ended* assignment when a test wants a fresh active one. Tests that
    need lookup-or-create semantics should query directly.

    ``rank`` is wired to the same covenant as the membership via a
    LazyAttribute so the rank/covenant-match invariant is always satisfied.
    """

    class Meta:
        model = CharacterCovenantRole

    character_sheet = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    covenant = factory.SubFactory(CovenantFactory)
    covenant_role = factory.SubFactory(CovenantRoleFactory)
    rank = factory.LazyAttribute(lambda o: CovenantRankFactory(covenant=o.covenant))
    engaged = False


class CovenantLevelThresholdFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantLevelThreshold."""

    class Meta:
        model = CovenantLevelThreshold
        django_get_or_create = ("level",)

    level = factory.Sequence(lambda n: n + 1)
    required_legend = factory.LazyAttribute(lambda o: (o.level - 1) * 100)


class CovenantRoleBonusFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRoleBonus."""

    class Meta:
        model = CovenantRoleBonus
        django_get_or_create = ("covenant_role", "modifier_target")

    covenant_role = factory.SubFactory(CovenantRoleFactory)
    modifier_target = factory.SubFactory("world.mechanics.factories.ModifierTargetFactory")
    bonus_per_level = 1


class CovenantRiteFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRite — the 'Renew the Oath' reference rite.

    Doubles as integration-test setUp AND staff seed data (per factories-as-seed-data
    convention). The backing Ritual is created via RenewTheOathRitualFactory
    (django_get_or_create on name) so repeated calls in the same test DB never
    produce duplicate Ritual rows. The granted_condition uses UNTIL_END_OF_COMBAT
    duration so the buff expires naturally at encounter end.

    Gate defaults mirror the reference spec:
        min_covenant_level=2, min_members_present=2, base_severity=2,
        severity_per_extra_participant=1, max_severity=None.
    """

    class Meta:
        model = CovenantRite

    ritual = factory.SubFactory("world.magic.factories.RenewTheOathRitualFactory")
    granted_condition = factory.SubFactory(
        "world.conditions.factories.OathboundResolveConditionFactory"
    )
    covenant_type = CovenantType.DURANCE
    min_covenant_level = 2
    min_members_present = 2
    base_severity = 2
    severity_per_extra_participant = 1
    max_severity = None
    duration_rounds = None


class CovenantRiteRolePackageFactory(factory_django.DjangoModelFactory):
    """Factory for CovenantRiteRolePackage — a role/level-gated stat package on a rite.

    No django_get_or_create — the unique constraint is (rite, covenant_role,
    min_covenant_level); callers that need the same band should query directly
    rather than relying on silent get-or-create merges.
    """

    class Meta:
        model = CovenantRiteRolePackage

    rite = factory.SubFactory(CovenantRiteFactory)
    covenant_role = factory.SubFactory(CovenantRoleFactory)
    min_covenant_level = 1
    condition_template = factory.SubFactory("world.conditions.factories.ConditionTemplateFactory")


class MentorBondFactory(factory_django.DjangoModelFactory):
    """Factory for MentorBond — a Mentor's Vow bond between mentor and sidekick (#1165).

    No django_get_or_create — the unique constraint is partial (only enforced when
    dissolved_at IS NULL), so get_or_create on (covenant, sidekick_sheet) would
    silently return an existing dissolved bond. Tests that need lookup-or-create
    semantics should query directly.
    """

    class Meta:
        model = MentorBond

    covenant = factory.SubFactory(CovenantFactory)
    mentor_sheet = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    sidekick_sheet = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    adjusted_party = MentorBondAdjusted.SIDEKICK
    dissolved_at = None


class CourtPactFactory(factory_django.DjangoModelFactory):
    """Factory for CourtPact — a sworn-fealty bond between a Court and a servant (#1589).

    Builds a *valid* active pact: the covenant defaults to a COURT type with its
    own leader (Court covenants require a leader), and the servant is a distinct
    sheet from that leader. ``granted_pull_cap`` defaults to 2 — a servant the
    master HAS empowered to pull (the ergonomic default); a grant of 0 would mean
    the master granted nothing, so the servant could not pull their Court-role
    thread at all. Override per-test when a specific cap is under test.

    No django_get_or_create — the model's unique constraint is partial (active
    only), so get_or_create would silently return a released pact. Tests needing
    lookup-or-create semantics should query directly.
    """

    class Meta:
        model = CourtPact

    covenant = factory.SubFactory(
        CovenantFactory,
        covenant_type=CovenantType.COURT,
        leader=factory.SubFactory(CHARACTER_SHEET_FACTORY),
    )
    servant_sheet = factory.SubFactory(CHARACTER_SHEET_FACTORY)
    granted_pull_cap = 2
    released_at = None


def seed_resonance_subrole_slice(
    parent_role: CovenantRole | None = None,
) -> list[CovenantRole]:
    """Seed ONE base role's resonance sub-role variants as a proof slice.

    Creates a small set of sub-roles (one per authored resonance) beneath
    *parent_role*, each with:

    - A distinct ``resonance`` (unique constraint on parent+resonance+level
      is satisfied by giving each sub-role a freshly sequenced resonance).
    - A ``discovery_achievement`` (AchievementFactory row).
    - A ``codex_entry`` (CodexEntryFactory row).
    - At least one ``CovenantRoleBonus`` row (mechanically real specialization).

    Uses ``get_or_create`` semantics via the factory ``django_get_or_create``
    keys where available so the helper is idempotent: calling it twice with the
    same parent produces the same rows (no duplicate-constraint violations).

    Safe as both integration-test setUp **and** staff/new-player seed data (per
    the factories-as-seed-data convention in MEMORY.md).

    Args:
        parent_role: The primary CovenantRole to attach sub-roles to.
            If None a new CovenantRoleFactory() is created automatically.

    Returns:
        List of CovenantRole sub-role instances (at least 2).
    """
    from world.achievements.factories import AchievementFactory
    from world.codex.factories import CodexEntryFactory
    from world.magic.factories import ResonanceFactory
    from world.mechanics.factories import ModifierTargetFactory

    if parent_role is None:
        parent_role = CovenantRoleFactory()

    # Two authored resonances — names are stable so get_or_create on the
    # ResonanceFactory's django_get_or_create ("name") makes this idempotent.
    resonance_names = [
        f"Ember Wrath ({parent_role.slug})",
        f"Keening Edge ({parent_role.slug})",
    ]

    subroles: list[CovenantRole] = []
    for idx, res_name in enumerate(resonance_names):
        resonance: Resonance = ResonanceFactory(name=res_name)
        achievement = AchievementFactory(
            slug=f"subrole-discovery-{parent_role.slug}-{idx}",
            name=f"Subrole Discovery: {res_name}",
        )
        entry = CodexEntryFactory(
            name=f"Subrole Lore: {res_name}",
        )

        subrole, _ = CovenantRole.objects.get_or_create(
            parent_role=parent_role,
            resonance=resonance,
            unlock_thread_level=3,
            defaults={
                "name": f"{parent_role.name} ({res_name})",
                "slug": f"{parent_role.slug}-res-{idx}",
                "covenant_type": parent_role.covenant_type,
                "speed_rank": parent_role.speed_rank,
                "description": f"Resonance sub-role for {res_name}.",
                "discovery_achievement": achievement,
                "codex_entry": entry,
            },
        )

        # Ensure discovery_achievement + codex_entry are populated even when
        # the row pre-existed (idempotent back-fill via update_fields).
        needs_update = []
        if subrole.discovery_achievement_id is None:
            subrole.discovery_achievement = achievement
            needs_update.append("discovery_achievement")
        if subrole.codex_entry_id is None:
            subrole.codex_entry = entry
            needs_update.append("codex_entry")
        if needs_update:
            subrole.save(update_fields=needs_update)

        # At least one CovenantRoleBonus row per sub-role (idempotent via
        # django_get_or_create on (covenant_role, modifier_target)).
        modifier_target = ModifierTargetFactory()
        CovenantRoleBonusFactory(covenant_role=subrole, modifier_target=modifier_target)

        subroles.append(subrole)

    return subroles


def wire_covenant_rite_content() -> CovenantRite:
    """Idempotent seed helper: create the Renew the Oath ritual + CovenantRite row.

    Also seeds the default and role/level-band stat packages (#753 Task 10):
    - Default package ("Oathbound Resolve"): willpower + composure + stability,
      each with value=5, scales_with_severity=True.
    - Sword (offense): "Oathbound Fury I" (strength, presence) at level 1+;
      "Oathbound Fury II" (strength, presence, wits) at level 4+.
    - Shield (defense): "Oathbound Bulwark" (stability, stamina) at level 1+.
    - Crown (support): "Oathbound Grace" (composure, charm) at level 1+.
    All effect rows use scales_with_severity=True.

    Safe to call as both integration-test setUp and staff/seed scripts — uses
    get_or_create semantics at each step so no duplicate rows are created.

    Returns the CovenantRite instance (whether newly created or already present).
    """
    from world.magic.constants import ParticipationRule, RitualExecutionKind
    from world.magic.models import Ritual

    ritual, _ = Ritual.objects.get_or_create(
        name="Renew the Oath",
        defaults={
            "description": (
                "A covenant rite performed by engaged members in the heat of battle. "
                "By reaffirming their sacred oath together, participants renew the bond "
                "that grants them supernatural resolve."
            ),
            "narrative_prose": (
                "The members of the covenant gather, voices joined in the words they swore at "
                "formation. The oath-magic stirs between them, recognising the bond that was "
                "forged in blood and will. As the last word falls, a wave of clarity and "
                "purpose settles over each participant — Oathbound Resolve, the covenant's gift "
                "to those who honour its demands."
            ),
            "execution_kind": RitualExecutionKind.SERVICE,
            "service_function_path": "world.covenants.services.perform_covenant_rite",
            "flow": None,
            "participation_rule": ParticipationRule.FORMATION,
        },
    )

    from world.conditions.factories import (
        OathboundBulwarkConditionFactory,
        OathboundFuryIConditionFactory,
        OathboundFuryIIConditionFactory,
        OathboundGraceConditionFactory,
        OathboundResolveConditionFactory,
    )
    from world.conditions.models import ConditionModifierEffect
    from world.mechanics.models import ModifierCategory, ModifierTarget

    # ------------------------------------------------------------------
    # Ensure the 'stat' ModifierCategory and the named stat targets exist.
    # All pattern: get_or_create keyed on (category, name) so repeated
    # calls never produce duplicates.
    # ------------------------------------------------------------------
    stat_cat, _ = ModifierCategory.objects.get_or_create(
        name="stat",
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )

    from world.traits.models import Trait

    def _stat(name: str) -> ModifierTarget:
        trait = Trait.get_by_name(name)
        target, _ = ModifierTarget.objects.get_or_create(
            category=stat_cat,
            name=name,
            defaults={
                "description": f"{name.capitalize()} stat modifier target.",
                "is_active": True,
                "target_trait": trait,
            },
        )
        # Backfill linkage on a pre-existing orphan row (get_or_create only
        # sets defaults on create).
        if target.target_trait_id is None and trait is not None:
            target.target_trait = trait
            target.save(update_fields=["target_trait"])
        return target

    # ------------------------------------------------------------------
    # Default condition ("Oathbound Resolve") + its modifier effects.
    # ------------------------------------------------------------------
    default_condition = OathboundResolveConditionFactory()

    for stat_name in ("willpower", "composure", "stability"):
        target = _stat(stat_name)
        ConditionModifierEffect.objects.get_or_create(
            condition=default_condition,
            modifier_target=target,
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # ------------------------------------------------------------------
    # CovenantRite row (keyed on ritual; idempotent).
    # ------------------------------------------------------------------
    rite, _ = CovenantRite.objects.get_or_create(
        ritual=ritual,
        defaults={
            "granted_condition": default_condition,
            "covenant_type": CovenantType.DURANCE,
            "min_covenant_level": 2,
            "min_members_present": 2,
            "base_severity": 2,
            "severity_per_extra_participant": 1,
            "max_severity": None,
            "duration_rounds": None,
        },
    )

    # ------------------------------------------------------------------
    # Canonical DURANCE roles (get_or_create on slug, mirroring the
    # pattern in world/seeds/game_content/items.py).
    # ------------------------------------------------------------------
    sword_role, _ = CovenantRole.objects.get_or_create(
        slug="sword-vanguard",
        defaults={
            "name": "Vanguard",
            "covenant_type": CovenantType.DURANCE,
            "sword_weight": 1,
            "speed_rank": 2,
        },
    )
    shield_role, _ = CovenantRole.objects.get_or_create(
        slug="shield-bulwark",
        defaults={
            "name": "Bulwark",
            "covenant_type": CovenantType.DURANCE,
            "shield_weight": 1,
            "speed_rank": 3,
        },
    )
    crown_role, _ = CovenantRole.objects.get_or_create(
        slug="crown-luminary",
        defaults={
            "name": "Luminary",
            "covenant_type": CovenantType.DURANCE,
            "crown_weight": 1,
            "speed_rank": 1,
        },
    )

    # ------------------------------------------------------------------
    # Role-package conditions + modifier effects.
    # ------------------------------------------------------------------

    # Sword level-1 band: strength, presence
    fury_i = OathboundFuryIConditionFactory()
    for stat_name in ("strength", "presence"):
        ConditionModifierEffect.objects.get_or_create(
            condition=fury_i,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # Sword level-4 band: strength, presence, wits
    fury_ii = OathboundFuryIIConditionFactory()
    for stat_name in ("strength", "presence", "wits"):
        ConditionModifierEffect.objects.get_or_create(
            condition=fury_ii,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 7, "scales_with_severity": True},
        )

    # Shield level-1 band: stability, stamina
    bulwark = OathboundBulwarkConditionFactory()
    for stat_name in ("stability", "stamina"):
        ConditionModifierEffect.objects.get_or_create(
            condition=bulwark,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # Crown level-1 band: composure, charm
    grace = OathboundGraceConditionFactory()
    for stat_name in ("composure", "charm"):
        ConditionModifierEffect.objects.get_or_create(
            condition=grace,
            modifier_target=_stat(stat_name),
            stage=None,
            defaults={"value": 5, "scales_with_severity": True},
        )

    # ------------------------------------------------------------------
    # CovenantRiteRolePackage rows (get_or_create on the unique triple).
    # ------------------------------------------------------------------
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=sword_role,
        min_covenant_level=1,
        defaults={"condition_template": fury_i},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=sword_role,
        min_covenant_level=4,
        defaults={"condition_template": fury_ii},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=shield_role,
        min_covenant_level=1,
        defaults={"condition_template": bulwark},
    )
    CovenantRiteRolePackage.objects.get_or_create(
        rite=rite,
        covenant_role=crown_role,
        min_covenant_level=1,
        defaults={"condition_template": grace},
    )

    return rite


def wire_covenant_level_bonus_catalog() -> CovenantLevelBonus:
    """Idempotent seed: the authored covenant-level passive bonus catalog (#762).

    Ensures the 'stat' ModifierCategory and the canonical willpower stat target
    exist (linked to the willpower Trait), then authors a CovenantLevelBonus
    granting engaged members +1 willpower per covenant level. Derive-on-read —
    no CharacterModifier rows are persisted.

    Safe as both integration-test setUp and staff/seed scripts (get_or_create at
    each step). Returns the CovenantLevelBonus instance.
    """
    from world.mechanics.models import ModifierCategory, ModifierTarget
    from world.traits.models import Trait

    stat_cat, _ = ModifierCategory.objects.get_or_create(
        name="stat",
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )
    trait = Trait.get_by_name("willpower")
    target, _ = ModifierTarget.objects.get_or_create(
        category=stat_cat,
        name="willpower",
        defaults={
            "description": "Willpower stat modifier target.",
            "is_active": True,
            "target_trait": trait,
        },
    )
    # Backfill linkage on a pre-existing orphan row.
    if target.target_trait_id is None and trait is not None:
        target.target_trait = trait
        target.save(update_fields=["target_trait"])

    config, _ = CovenantLevelBonus.objects.get_or_create(
        modifier_target=target,
        defaults={"bonus_per_level": 1},
    )
    return config


def wire_covenant_role_powers_catalog() -> "tuple[CovenantRole, list[CapabilityType]]":
    """Idempotent seed: an authored per-(role, resonance) role-powers catalog.

    Authors ONE Sword (offense) archetype CovenantRole for the Covenant of Battle
    and, for each of two distinct authored resonances channelling that role, the
    pair of pull effects that make the role mechanically real:

    - A **tier-0 CAPABILITY_GRANT** — the covenant's always-on *gift* to an engaged
      holder who has woven their role-thread on that resonance. Two holders of the
      same role anchoring DIFFERENT resonances thereby unlock DIFFERENT capabilities
      (the #751 individualization lever — identity is across characters, not within
      one).
    - A **tier-1 active pull** — a paid in-the-moment surge (FLAT_BONUS for the first
      resonance, INTENSITY_BUMP for the second) showing the active-pull half of the
      catalog alongside the passive gift.

    Doubles as integration-test setUp AND staff/new-player seed data (per the
    factories-as-seed-data convention). Every create is a ``get_or_create`` keyed on
    its natural/unique key, so a second call is a no-op — no data migration.

    Returns ``(role, [cap_for_res_a, cap_for_res_b])``.
    """
    from world.conditions.models import CapabilityType
    from world.magic.constants import EffectKind, TargetKind
    from world.magic.models import Affinity, Resonance, ThreadPullEffect

    # ------------------------------------------------------------------
    # The Sword (offense) role — PRIMARY (no parent_role/resonance, level 0).
    # ------------------------------------------------------------------
    role, _ = CovenantRole.objects.get_or_create(
        slug="battle-warblade",
        defaults={
            "name": "Warblade",
            "covenant_type": CovenantType.BATTLE,
            "sword_weight": 1,
            "speed_rank": 2,
            "description": (
                "The covenant's drawn edge — those who carry the oath into the killing "
                "press and answer threat with threat."
            ),
        },
    )

    # ------------------------------------------------------------------
    # Two authored resonances (each needs an Affinity FK).
    # ------------------------------------------------------------------
    affinity, _ = Affinity.objects.get_or_create(
        name="Primal",
        defaults={"description": "The wild, untamed source of magical power."},
    )
    res_ember, _ = Resonance.objects.get_or_create(
        name="Ember Wrath",
        defaults={
            "description": (
                "A resonance of blazing, forward fury — the war-fire that does not retreat."
            ),
            "affinity": affinity,
        },
    )
    res_keening, _ = Resonance.objects.get_or_create(
        name="Keening Edge",
        defaults={
            "description": (
                "A resonance of honed, singing precision — the blade that finds the seam."
            ),
            "affinity": affinity,
        },
    )

    # ------------------------------------------------------------------
    # One distinct capability per resonance (the gift each unlocks).
    # ------------------------------------------------------------------
    cap_ember, _ = CapabilityType.objects.get_or_create(
        name="Warblade: Sundering Strike",
        defaults={
            "description": "Channel the covenant's war-fire to shatter a foe's guard.",
            "innate_baseline": 0,
        },
    )
    cap_keening, _ = CapabilityType.objects.get_or_create(
        name="Warblade: Seam-Finder",
        defaults={
            "description": "Read the singing edge to strike unerringly through any gap.",
            "innate_baseline": 0,
        },
    )

    # ------------------------------------------------------------------
    # Per resonance: tier-0 passive CAPABILITY_GRANT + a tier-1 active pull.
    # Keyed (target_kind, resonance, tier, min_thread_level) — the unique lookup.
    #
    # FLAT_BONUS/INTENSITY_BUMP amounts use 10 (not 3/1) per #1845:
    # thread_level_multiplier(1) == 0.1 (#1718's corrected ramp) and
    # scaled_value = round(authored * multiplier); amounts below 6 round to 0
    # at low thread levels, silently defeating the pull. 10 clears the floor
    # with margin — same rationale as the Court catalog below.
    # ------------------------------------------------------------------
    ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.COVENANT_ROLE,
        resonance=res_ember,
        tier=0,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.CAPABILITY_GRANT,
            "capability_grant": cap_ember,
            "narrative_snippet": (
                "The Ember Wrath you carry for the covenant kindles in your grip; the "
                "oath answers, and your strikes learn to shatter what stands against them."
            ),
        },
    )
    ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.COVENANT_ROLE,
        resonance=res_ember,
        tier=1,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.FLAT_BONUS,
            "flat_bonus_amount": 10,
            "narrative_snippet": (
                "You pull harder on the war-fire and it surges — a blaze of borrowed "
                "fury behind the blow."
            ),
        },
    )

    ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.COVENANT_ROLE,
        resonance=res_keening,
        tier=0,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.CAPABILITY_GRANT,
            "capability_grant": cap_keening,
            "narrative_snippet": (
                "The Keening Edge you bear for the covenant sings low in the bones of "
                "your hand; the oath answers, and your eye finds the seam before the cut."
            ),
        },
    )
    ThreadPullEffect.objects.get_or_create(
        target_kind=TargetKind.COVENANT_ROLE,
        resonance=res_keening,
        tier=1,
        min_thread_level=0,
        defaults={
            "effect_kind": EffectKind.INTENSITY_BUMP,
            "intensity_bump_amount": 10,
            "narrative_snippet": (
                "You draw the singing edge taut and it answers — every line of the "
                "strike sharpened a degree past mortal keenness."
            ),
        },
    )

    return role, [cap_ember, cap_keening]


def wire_court_role_powers_catalog() -> "tuple[CovenantRole, list[ThreadPullEffect]]":
    """Idempotent seed: a themed COURT role-powers catalog (#1589 Task 8).

    The COURT analog of :func:`wire_covenant_role_powers_catalog`. Authors ONE
    COURT-scoped Sword (offense) ``CovenantRole`` — the Court's drawn blade —
    plus the rows that make the role mechanically real for a servant who has
    woven their Court-role thread:

    - A **``CovenantRoleBonus``** scaling on the *holder's own* level (so a
      higher-level servant draws a larger passive bonus from the role).
    - Per authored resonance, a **tier-1 ``FLAT_BONUS`` ``ThreadPullEffect``**
      (target_kind=COVENANT_ROLE) — the paid in-the-moment surge a servant pulls
      from their Court-role thread for a combat bonus.

    Mirrors the Battle catalog's structure but stays minimal: just the passive
    bonus + the active FLAT_BONUS pull (no tier-0 capability leg). Doubles as
    integration-test setUp AND staff/seed data — every create is a
    ``get_or_create`` keyed on its natural key, so a second call is a no-op.

    Returns ``(role, [flat_for_res_a, flat_for_res_b])`` — the FLAT_BONUS pull
    rows, so the E2E can drive a pull through the seeded resonances.
    """
    from world.magic.constants import EffectKind, TargetKind
    from world.magic.models import Affinity, Resonance, ThreadPullEffect
    from world.mechanics.models import ModifierCategory, ModifierTarget

    # ------------------------------------------------------------------
    # The Court's Sword (offense) role — PRIMARY (no parent_role/resonance).
    # ------------------------------------------------------------------
    role, _ = CovenantRole.objects.get_or_create(
        slug="court-shadowblade",
        defaults={
            "name": "Shadowblade",
            "covenant_type": CovenantType.COURT,
            "sword_weight": 1,
            "speed_rank": 2,
            "description": (
                "The Court's drawn blade — the servant who answers the master's "
                "business in the killing dark."
            ),
        },
    )

    # ------------------------------------------------------------------
    # A CovenantRoleBonus scaling on the holder's own level.
    # ------------------------------------------------------------------
    stat_cat, _ = ModifierCategory.objects.get_or_create(
        name="stat",
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )
    bonus_target, _ = ModifierTarget.objects.get_or_create(
        category=stat_cat,
        name="presence",
        defaults={
            "description": "Presence stat modifier target.",
            "is_active": True,
        },
    )
    CovenantRoleBonus.objects.get_or_create(
        covenant_role=role,
        modifier_target=bonus_target,
        defaults={"bonus_per_level": 1},
    )

    # ------------------------------------------------------------------
    # Two authored court-themed resonances (each needs an Affinity FK).
    # ------------------------------------------------------------------
    affinity, _ = Affinity.objects.get_or_create(
        name="Abyssal",
        defaults={"description": "The deep, hidden source of magical power."},
    )
    res_whisper, _ = Resonance.objects.get_or_create(
        name="Whispered Malice",
        defaults={
            "description": (
                "A resonance of patient, poisoned intent — the knife that smiles before it turns."
            ),
            "affinity": affinity,
        },
    )
    res_garrote, _ = Resonance.objects.get_or_create(
        name="Velvet Garrote",
        defaults={
            "description": (
                "A resonance of silken, sudden ending — the embrace that does not let go."
            ),
            "affinity": affinity,
        },
    )

    # ------------------------------------------------------------------
    # Per resonance: a tier-1 FLAT_BONUS pull, authored at min_thread_level=1
    # so the PACT is the real gate (#1589 final review). A servant with no
    # active pact gets granted cap 0 → their Court-role thread cannot imbue
    # above level 0 → this min-level-1 effect does NOT apply → the pull yields
    # no Court bonus. Keyed (target_kind, resonance, tier, min_thread_level) —
    # the unique lookup.
    #
    # FLAT_BONUS effects carry NO narrative_snippet: the combat-commit snapshot
    # (CombatPullResolvedEffect's flat_bonus_payload CheckConstraint) requires
    # narrative_snippet="" for FLAT_BONUS, so a snippet here would make the pull
    # un-committable in combat (IntegrityError in _persist_combat_pull). Pull
    # flavour belongs on NARRATIVE_ONLY effects, not the mechanical FLAT_BONUS.
    #
    # amount=10, not 3: thread_level_multiplier(1) == 0.1 (#1718's corrected
    # ramp — see thread.py) and scaled_value = round(authored * multiplier);
    # an authored amount below 6 rounds to 0 at the level-1 pact-gate boundary,
    # silently defeating the "a pact grants a real bonus" premise this catalog
    # exists to demonstrate. 10 clears that floor with margin.
    # ------------------------------------------------------------------
    flat_effects: list[ThreadPullEffect] = []
    pulls = (
        (res_whisper, 10),
        (res_garrote, 10),
    )
    for resonance, amount in pulls:
        effect, _ = ThreadPullEffect.objects.get_or_create(
            target_kind=TargetKind.COVENANT_ROLE,
            resonance=resonance,
            tier=1,
            min_thread_level=1,
            defaults={
                "effect_kind": EffectKind.FLAT_BONUS,
                "flat_bonus_amount": amount,
            },
        )
        flat_effects.append(effect)

    return role, flat_effects


def wire_court_grant_petition_content() -> "CheckType":
    """Idempotent seed: the shared check rolled for every Court grant petition (#1718).

    ONE CheckType across every Court master — the effect layer eases difficulty
    per-master via the servant's affection, so no per-master authoring is needed.
    Doubles as integration-test setUp AND staff/seed data (get_or_create keyed on
    the natural key), mirroring wire_court_role_powers_catalog.
    """
    from world.checks.models import CheckCategory, CheckType
    from world.covenants.services import get_court_grant_config

    category, _ = CheckCategory.objects.get_or_create(name="Social", defaults={"display_order": 20})
    check_type, _ = CheckType.objects.get_or_create(
        name="Court Grant Petition",
        category=category,
        defaults={"description": "Convincing a Court master to grant more strength."},
    )
    config = get_court_grant_config()
    if config.petition_check_type_id != check_type.pk:
        config.petition_check_type = check_type
        config.save(update_fields=["petition_check_type"])
    return check_type


def seed_mentor_bond_defaults() -> MentorBondConfig:
    """Seed the MentorBondConfig pk=1 singleton with authored defaults (#1165).

    Idempotent: uses update_or_create so re-running resets to the authored defaults,
    overwriting any staff edits. This is intentional for pre-launch seeding from
    authored constants; do not call it where staff tuning must survive.

    Returns the MentorBondConfig singleton.
    """
    config, _ = MentorBondConfig.objects.update_or_create(
        pk=1,
        defaults={
            "band_width": MENTOR_BOND_BAND_WIDTH,
            "adjacency_offset": MENTOR_BOND_ADJACENCY_OFFSET,
            "max_sidekicks_per_mentor": MENTOR_BOND_MAX_SIDEKICKS,
        },
    )
    return config


def make_engaged_member(
    *,
    character_sheet: object = None,
    covenant: object = None,
    covenant_role: object = None,
) -> CharacterCovenantRole:
    """Create a covenant + active CCR row + set engaged=True, atomically.

    Convenience for tests that exercise role-bonus or pull-eligibility paths.
    Uses the `set_engaged_membership` service so the invariant is enforced
    naturally.
    """
    from world.covenants.services import set_engaged_membership

    sheet = character_sheet or CharacterSheetFactory()
    cov = covenant or CovenantFactory()
    role = covenant_role or CovenantRoleFactory(covenant_type=cov.covenant_type)
    membership = CharacterCovenantRoleFactory(
        character_sheet=sheet,
        covenant=cov,
        covenant_role=role,
    )
    set_engaged_membership(membership=membership)
    return membership


class CourtSeed(NamedTuple):
    """Result of :func:`make_court_with_mission` — a complete themed Court.

    A NamedTuple so callers may unpack it positionally
    ``(covenant, master_sheet, servant_sheet, mission_instance)`` OR read the
    named fields. ``themed_role`` and ``service_offer`` are carried along for
    tests/E2E that want to drive a pull or a second mission off the same seed.
    """

    covenant: Covenant
    master_sheet: object
    servant_sheet: object
    mission_instance: object
    themed_role: CovenantRole
    service_offer: object


def make_court_with_mission(
    *,
    master_level: int = 11,
    servant_level: int = 1,
) -> CourtSeed:
    """Seed a complete themed Court with a servant on an active master-org mission.

    Builds, in one call, everything the #1589 engagement loop needs:

    - ``master_sheet`` — an account-less NPC ``CharacterSheet`` at ``master_level``
      (default 11 → tier 3), high enough that the servant (default level 1 → tier 1)
      sits ≥1 tier below (the fealty gulf).
    - ``covenant`` — a convened COURT covenant with the master as its ``leader`` and
      an ``is_leader`` founder; its backing Organization is auto-created in
      ``Covenant.save()`` and reachable via ``covenant.organization``.
    - The servant seated as a member holding the themed COURT role from
      :func:`wire_court_role_powers_catalog` (with its CovenantRoleBonus + tier-1
      FLAT_BONUS thread-pull rows).
    - An ``NPCRole`` fronting the Court's Organization, carrying a MISSION
      ``NPCServiceOffer``.
    - An **ACTIVE** ``MissionInstance`` whose ``source_offer`` is that offer, with
      the servant as a ``MissionParticipant`` — so
      ``has_active_court_mission(character_sheet=servant_sheet, covenant=covenant)``
      is True.

    Returns a :class:`CourtSeed`.
    """
    from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
    from world.covenants.services import create_covenant
    from world.covenants.types import CovenantFounder
    from world.missions.constants import MissionStatus
    from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
    from world.npc_services.constants import OfferKind
    from world.npc_services.factories import NPCRoleFactory, NPCServiceOfferFactory

    def _set_primary_level(sheet: object, level: int) -> None:
        CharacterClassLevelFactory(
            character=sheet.character,
            character_class=CharacterClassFactory(),
            level=level,
            is_primary=True,
        )
        sheet.invalidate_class_level_cache()

    themed_role, _ = wire_court_role_powers_catalog()

    master_sheet = CharacterSheetFactory()
    servant_sheet = CharacterSheetFactory()
    _set_primary_level(master_sheet, master_level)
    _set_primary_level(servant_sheet, servant_level)

    # The master is both the puissant the Court is sworn to (the `leader` FK) and
    # its founding member; the servant is a member holding the themed COURT role.
    # create_covenant convenes the rank ladder and auto-creates the backing org.
    master_role, _ = CovenantRole.objects.get_or_create(
        slug="court-sovereign",
        defaults={
            "name": "Sovereign",
            "covenant_type": CovenantType.COURT,
            "crown_weight": 1,
            "speed_rank": 1,
            "description": "The puissant master a Court is sworn to.",
        },
    )
    covenant = create_covenant(
        name=f"Court of Shadows {master_sheet.pk}",
        covenant_type=CovenantType.COURT,
        sworn_objective="Sworn to serve the master's hidden will.",
        leader=master_sheet,
        founders=[
            CovenantFounder(character_sheet=master_sheet, role=master_role, is_leader=True),
            CovenantFounder(character_sheet=servant_sheet, role=themed_role, is_leader=False),
        ],
    )

    # The master's NPCRole fronts the Court's Organization; a MISSION offer on it
    # is what makes a resulting MissionInstance a *Court* mission (the predicate
    # matches source_offer.role.faction_affiliation against covenant.organization).
    npc_role = NPCRoleFactory(
        name=f"Court Steward {covenant.pk}",
        faction_affiliation=covenant.organization,
    )
    offer = NPCServiceOfferFactory(role=npc_role, kind=OfferKind.MISSION)

    mission = MissionInstanceFactory(source_offer=offer, status=MissionStatus.ACTIVE)
    # MissionParticipant.character FKs to ObjectDB — use the servant's character.
    MissionParticipantFactory(
        instance=mission,
        character=servant_sheet.character,
        is_contract_holder=True,
    )

    return CourtSeed(
        covenant=covenant,
        master_sheet=master_sheet,
        servant_sheet=servant_sheet,
        mission_instance=mission,
        themed_role=themed_role,
        service_offer=offer,
    )
