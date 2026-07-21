"""Models for the covenants system.

Covenants are magically-empowered oaths — blood rituals that bind participants
to shared roles and goals. This app owns role definitions and their mechanical
properties (like combat speed rank). The full covenant lifecycle (formation,
membership, progression) is future work.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.battles.constants import BattleActionKind
from world.covenants.constants import (
    MENTOR_BOND_ADJACENCY_OFFSET,
    MENTOR_BOND_BAND_WIDTH,
    MENTOR_BOND_MAX_SIDEKICKS,
    BattleBinding,
    CommandTier,
    CovenantType,
    DefenseStyle,
    MentorBondAdjusted,
    RoleArchetype,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.items.constants import GearArchetype
from world.magic.constants import TechniqueFunction
from world.magic.specialization.models import AbstractSpecializedVariant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.conditions.models import ConditionTemplate
    from world.covenants.handlers import CovenantMembershipHandler
    from world.magic.models.affinity import Resonance

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
ACCOUNT_DB_MODEL = "accounts.AccountDB"
COVENANT_MODEL = "covenants.Covenant"
COVENANT_ROLE_MODEL = "covenants.CovenantRole"
CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"
CONDITION_TEMPLATE_MODEL = "conditions.ConditionTemplate"


class Covenant(SharedMemoryModel):
    """The foundational social/magical structure that binds members under a sworn oath.

    Per-kind extension of Organization for kind=COVENANT. Each Covenant has a
    backing Organization auto-created in save() if not provided. Covenant.pk
    equals organization.pk.

    Slice A scope: identity, type, level (placeholder until Slice D), formed/dissolved
    timestamps, free-text sworn objective.

    Deferred fields (future slices):
    - durance_focus_FK / battle_encounter_FK — Slice E (type-specific data)
    - structured sworn_objective_FK → SwornObjective — Slice C (replaces TextField)
    - xp, milestone progression fields — Slice D
    - description, crest, motto, cosmetic fields — post-MVP polish
    - dissolution_reason, dissolution_kind — Slice B
    """

    organization = models.OneToOneField(
        "societies.Organization",
        on_delete=models.CASCADE,
        related_name="covenant",
        # NOT NULL at the DB level — the auto-create in save() always populates it
        # BEFORE super().save() runs, so the DB never sees a null. bulk_create()
        # is therefore unsafe for Covenant; always use single .save() calls.
        # NOT primary_key=True — Covenant keeps its own auto-id pk so views,
        # serializers, and FKs from CovenantLegendCredit continue to work.
    )
    name = models.CharField(max_length=120, unique=True)
    covenant_type = models.CharField(
        max_length=20,
        choices=CovenantType.choices,
        default=CovenantType.DURANCE,
    )
    level = models.PositiveIntegerField(
        default=1,
        help_text="Group progression tier (Slice D will drive growth).",
    )
    sworn_objective = models.TextField(
        blank=False,
        help_text="Free text in Slice A; structured in Slice C.",
    )
    formed_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)
    battle_binding = models.CharField(
        max_length=20,
        choices=BattleBinding.choices,
        blank=True,
        default="",
        help_text=(
            "Battle covenants only (Slice E). STANDING can rise again; CAMPAIGN "
            "dissolves when its objective concludes. Empty for DURANCE covenants."
        ),
    )
    is_dormant = models.BooleanField(
        default=False,
        help_text=(
            "Battle covenants only: True when a STANDING covenant has stood down "
            "and awaits a 'call the banners' rise ritual. A dormant covenant "
            "cannot be engaged. Never True for DURANCE or CAMPAIGN covenants."
        ),
    )
    campaign_story = models.ForeignKey(
        "stories.Story",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ended_campaigns",
        help_text=(
            "CAMPAIGN battle covenants only: the defining story whose completion "
            "dissolves this campaign. SET_NULL so deleting the story does not "
            "cascade-delete the covenant. Empty for STANDING/DURANCE covenants."
        ),
    )
    leader = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="led_courts",
        help_text=(
            "Court covenants only: the puissant this Court is sworn to. Empty for other types."
        ),
    )
    court_grant_role = models.ForeignKey(
        "npc_services.NPCRole",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Court covenants only (#1718): the auto-provisioned NPCRole carrying "
            "this Court's OfferKind.COURT_GRANT petition offer. Null until the "
            "servant's first petition attempt lazily provisions it via "
            "ensure_court_grant_role()."
        ),
    )
    provisioning_ratio = models.FloatField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Army food provisioning ratio at mobilization (0.0-1.0). "
            "Null when not provisioned or stood down. Set by provision_army(), "
            "cleared by stand_down_battle_covenant(). (#2375)"
        ),
    )

    def save(self, *args: object, **kwargs: object) -> None:
        if self.organization_id is None:
            # Lazy import to avoid circular dependency.
            from django.db import transaction  # noqa: PLC0415

            from world.covenants.constants import COVENANT_ORG_TYPE_NAME  # noqa: PLC0415
            from world.societies.models import Organization, OrganizationType  # noqa: PLC0415

            # Wrap the auto-create + save in atomic so a failure in either
            # rolls back BOTH. Without this, a Covenant validation error
            # leaves an orphaned Organization row.
            with transaction.atomic():
                # get_or_create so tests work without loading the fixture and
                # production-fresh DBs auto-bootstrap with sane defaults. Staff
                # can still customize rank titles via admin.
                covenant_org_type, _ = OrganizationType.objects.get_or_create(
                    name=COVENANT_ORG_TYPE_NAME,
                    defaults={
                        "rank_1_title": "Coven Mother",
                        "rank_2_title": "Adept",
                        "rank_3_title": "Initiate",
                        "rank_4_title": "Novice",
                        "rank_5_title": "Aspirant",
                    },
                )
                self.organization = Organization.objects.create(
                    name=self.name,
                    society=None,
                    org_type=covenant_org_type,
                )
                super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        if self.covenant_type == CovenantType.BATTLE:
            if not self.battle_binding:
                raise ValidationError(
                    {"battle_binding": "Battle covenants require a battle_binding."}
                )
        else:
            if self.battle_binding:
                raise ValidationError(
                    {"battle_binding": "Only Battle covenants may set battle_binding."}
                )
            if self.is_dormant:
                raise ValidationError({"is_dormant": "Only Battle covenants may be dormant."})
        if self.is_dormant and self.battle_binding != BattleBinding.STANDING:
            raise ValidationError({"is_dormant": "Only STANDING battle covenants may be dormant."})
        if self.campaign_story_id and self.battle_binding != BattleBinding.CAMPAIGN:
            raise ValidationError(
                {"campaign_story": "Only CAMPAIGN battle covenants may set campaign_story."}
            )
        if self.covenant_type == CovenantType.COURT:
            if self.leader_id is None:
                raise ValidationError({"leader": "Court covenants require a leader."})
        elif self.leader_id is not None:
            raise ValidationError({"leader": "Only Court covenants may set a leader."})

    @cached_property
    def member_roster(self) -> CovenantMembershipHandler:
        from world.covenants.handlers import CovenantMembershipHandler  # noqa: PLC0415

        return CovenantMembershipHandler(self)

    def __str__(self) -> str:
        state = "active" if self.dissolved_at is None else "dissolved"
        return f"{self.name} ({self.get_covenant_type_display()}, {state})"


class CovenantRoleManager(NaturalKeyManager):
    """Manager for CovenantRole with natural key support."""


class CovenantRole(NaturalKeyMixin, AbstractSpecializedVariant, SharedMemoryModel):
    """A role that a character can hold within a covenant.

    Lookup table — staff-authored, cached via SharedMemoryModel.
    Different covenant types may have different role sets; the
    covenant_type field scopes which roles are available.

    Combat reads ``speed_rank`` directly from this model during resolution
    order calculation.

    Inherits the four specialization columns (``resonance``,
    ``unlock_thread_level``, ``discovery_achievement``, ``codex_entry``)
    from ``AbstractSpecializedVariant`` (#1578, ADR-0055) — the same base
    ``TechniqueVariant`` uses. That base supersedes main's #1623
    ``DiscoverableContent`` mixin here (it provides the same
    ``discovery_achievement`` field), so ``CovenantRole`` does NOT also
    inherit ``DiscoverableContent``; ``Technique`` keeps it. Schema no-op:
    the columns matched the base verbatim, so this refactor changes only the
    Python class graph (and the ``resonance`` reverse ``related_name``,
    which no live code reads).
    """

    name = models.CharField(max_length=60, help_text="Display name, e.g. 'Vanguard'.")
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text="Stable identifier for code references, e.g. 'vanguard'.",
    )
    covenant_type = models.CharField(
        max_length=20,
        choices=CovenantType.choices,
        default=CovenantType.DURANCE,
        help_text="Which covenant type this role belongs to.",
    )
    sword_weight = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=0,
        help_text=(
            "SWORD axis of the combat-identity blend (0-1). Weights are stored on "
            "primary roles only; sub-roles read the parent's blend (#2529)."
        ),
    )
    shield_weight = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=0,
        help_text="SHIELD axis of the combat-identity blend (0-1).",
    )
    crown_weight = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=0,
        help_text="CROWN axis of the combat-identity blend (0-1).",
    )
    speed_rank = models.PositiveIntegerField(
        help_text="Combat resolution order. Lower is faster (1 = fastest).",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of the role's identity and combat style.",
    )
    parent_role = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sub_roles",
        help_text="Null for primary roles. Set for sub-roles.",
    )
    command_tier = models.CharField(
        max_length=20,
        choices=CommandTier.choices,
        default=CommandTier.NONE,
        help_text=(
            "Battle-command hierarchy tier (#1710). Only settable on "
            "CovenantType.BATTLE roles — see clean()."
        ),
    )
    is_champion_role = models.BooleanField(
        default=False,
        help_text=(
            "True if holding this role lets a character issue/answer a single-combat "
            "duel for the covenant (#1710). Only settable on CovenantType.BATTLE roles."
        ),
    )
    granted_gifts = models.ManyToManyField(
        "magic.Gift",
        through="CovenantRoleGiftGrant",
        blank=True,
        related_name="granted_by_roles",
        help_text=(
            "#2022: Gifts granted by this role while engaged. The role's gift "
            "techniques are auto-granted on engage and auto-revoked on disengage "
            "(the #2051 vow-dim path). Techniques are primarily enhancements that "
            "boost overlapping techniques from the character's existing gifts."
        ),
    )
    granted_capabilities = models.ManyToManyField(
        "conditions.CapabilityType",
        blank=True,
        related_name="granted_by_roles",
        help_text=(
            "#2022: Capabilities granted by this role while engaged. Written to "
            "the character's capability ledger on engage; revoked on disengage."
        ),
    )

    objects = CovenantRoleManager()

    @cached_property
    def cached_sub_roles(self) -> list:
        """Sub-roles for this role. Supports Prefetch(to_attr=).

        To invalidate: ``del instance.cached_sub_roles``.
        """
        return list(self.sub_roles.all())

    def blend_weight_for(self, axis: str) -> Decimal:
        """Return this role's blend weight for a SWORD/SHIELD/CROWN axis (#2529).

        Sub-roles carry no weights of their own — the blend always reads from
        the primary (parent) role, so specialization can never drift the
        combat-identity blend (ADR-0055: sub-roles specialize by resonance).
        """
        source = self.parent_role if self.parent_role_id is not None else self
        if axis == RoleArchetype.SWORD:
            return source.sword_weight
        if axis == RoleArchetype.SHIELD:
            return source.shield_weight
        if axis == RoleArchetype.CROWN:
            return source.crown_weight
        return Decimal(0)

    @classmethod
    def _variant_queryset(
        cls,
        parent: AbstractSpecializedVariant,
        *,
        resonance: Resonance | None = None,
        resonance_id: int | None = None,
    ) -> list[CovenantRole]:
        """CovenantRole binds the parent self-FK ``parent_role`` -> reverse
        ``sub_roles``. Override so the shared classmethods read the parent's
        ``cached_sub_roles`` list (the convention in techniques.py / gifts.py)
        and filter by resonance via a list-comp — no ``.filter()`` query per
        project cached-property rule.
        """
        rid = resonance.pk if resonance is not None else resonance_id
        return [r for r in parent.cached_sub_roles if r.resonance_id == rid]

    def discovery_narrative(
        self,
        *,
        is_first: bool,
    ) -> tuple[Sequence[CharacterSheet], str]:
        """Sub-role manifestation copy (mirrors covenants/discovery._notify).

        ``is_first=True`` -> gamewide recipients (all active player sheets) +
        "first time in recorded history" prose. ``is_first=False`` -> empty
        recipients ``[]`` (the ceremony caller appends ``[thread.owner]``) +
        "covenant path has deepened" prose.
        """
        if is_first:
            from world.roster.selectors import (  # noqa: PLC0415
                active_player_character_sheets,
            )

            recipients = active_player_character_sheets()
            body = (
                f"For the first time in recorded history, a character has "
                f"manifested the {self.name} sub-role — a convergence of "
                f"{self.resonance.name} and covenant purpose no one has "
                f"achieved before."
            )
        else:
            # Personal: the discovering sheet is supplied by the ceremony
            # caller (fire_variant_discoveries), which has thread.owner in
            # scope; it appends [thread.owner] when this returns [].
            recipients: list[CharacterSheet] = []
            body = (
                f"Your covenant path has deepened. You have manifested the "
                f"{self.name} sub-role, channelled through {self.resonance.name}."
            )
        return recipients, body

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_type", "name"],
                name="unique_role_name_per_covenant_type",
            ),
            models.UniqueConstraint(
                fields=["parent_role", "resonance", "unlock_thread_level"],
                condition=models.Q(parent_role__isnull=False),
                name="covenant_subrole_unique_per_parent_resonance_level",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["slug"]

    def _clean_subrole(self) -> None:
        if self.unlock_thread_level == 0:
            raise ValidationError(
                {"unlock_thread_level": "Sub-roles must have unlock_thread_level > 0."}
            )
        parent = self.parent_role
        if parent.covenant_type != self.covenant_type:
            raise ValidationError(
                {"covenant_type": "Sub-role covenant_type must match parent_role.covenant_type."}
            )
        if self.sword_weight or self.shield_weight or self.crown_weight:
            raise ValidationError(
                {
                    "sword_weight": (
                        "Sub-roles must not set blend weights — the blend lives on "
                        "the parent role (#2529)."
                    )
                }
            )
        if parent.parent_role_id is not None:
            raise ValidationError(
                {"parent_role": "Sub-sub-roles are not allowed (single-depth only)."}
            )

    def _clean_primary_role(self) -> None:
        if self.discovery_achievement_id is not None or self.codex_entry_id is not None:
            raise ValidationError(
                {
                    "discovery_achievement": (
                        "Only sub-roles may set discovery_achievement / codex_entry."
                    )
                }
            )
        if self.unlock_thread_level != 0:
            raise ValidationError(
                {
                    "unlock_thread_level": (
                        "Primary roles (no parent_role/resonance) must have unlock_thread_level=0."
                    )
                }
            )
        for field in ("sword_weight", "shield_weight", "crown_weight"):
            value = getattr(self, field)
            if value < 0 or value > 1:
                raise ValidationError({field: "Blend weights must be between 0 and 1."})
        total = self.sword_weight + self.shield_weight + self.crown_weight
        if abs(total - Decimal(1)) > Decimal("0.01"):
            raise ValidationError(
                {
                    "sword_weight": (
                        f"Blend weights must sum to 1.0 (got {total}). "
                        "Adjust sword/shield/crown weights."
                    )
                }
            )

    def clean(self) -> None:
        super().clean()
        if self.covenant_type != CovenantType.BATTLE:
            if self.command_tier != CommandTier.NONE:
                raise ValidationError(
                    {"command_tier": "command_tier is only settable on Battle covenant roles."}
                )
            if self.is_champion_role:
                raise ValidationError(
                    {
                        "is_champion_role": (
                            "is_champion_role is only settable on Battle covenant roles."
                        )
                    }
                )

        has_parent = self.parent_role_id is not None
        has_resonance = self.resonance_id is not None

        # XOR rule: both must be set (sub-role) or both must be null (primary role)
        if has_parent != has_resonance:
            msg = (
                "parent_role and resonance must both be set (sub-role) or both be null "
                "(primary role)."
            )
            raise ValidationError({"parent_role": msg, "resonance": msg})

        if has_parent and has_resonance:
            self._clean_subrole()
        else:
            self._clean_primary_role()

    def __str__(self) -> str:
        return f"{self.name} ({self.get_covenant_type_display()})"


class GearArchetypeCompatibilityManager(NaturalKeyManager):
    """Manager for GearArchetypeCompatibility with natural key support."""


class GearArchetypeCompatibility(NaturalKeyMixin, SharedMemoryModel):
    """Existence-only join: which roles are compatible with which archetypes.

    Spec D §4.4. Row present = role bonuses add to mundane gear stats on
    that archetype. Row absent = incompatible (max(role, gear) per slot).
    """

    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.CASCADE,
        related_name="gear_compatibilities",
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
    )

    objects = GearArchetypeCompatibilityManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "gear_archetype"],
                name="covenants_unique_role_archetype_compat",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "gear_archetype"]
        dependencies = [COVENANT_ROLE_MODEL]

    def __str__(self) -> str:
        return f"{self.covenant_role.name} compatible with {self.get_gear_archetype_display()}"


class CovenantRank(SharedMemoryModel):
    """A per-covenant administrative authority tier (the rank ladder).

    Orthogonal to CovenantRole (combat power). Lower ``tier`` = higher
    authority (1 = top). Capability flags gate invite/kick/manage. See #1027.
    """

    covenant = models.ForeignKey(
        COVENANT_MODEL,
        on_delete=models.CASCADE,
        related_name="ranks",
    )
    name = models.CharField(max_length=60, help_text="Player-chosen tier name, e.g. 'Magister'.")
    tier = models.PositiveIntegerField(help_text="Precedence; lower = higher authority (1 = top).")
    description = models.TextField(blank=True, help_text="Optional flavor/ceremony text.")
    can_invite = models.BooleanField(default=False)
    can_kick = models.BooleanField(
        default=False, help_text="May remove members of a strictly lower tier."
    )
    can_manage_ranks = models.BooleanField(
        default=False, help_text="May edit the ladder and assign members."
    )
    can_lead_rituals = models.BooleanField(
        default=False,
        help_text="May lead this covenant's group rituals (e.g. Covenant Sanctification).",
    )
    can_request_gm = models.BooleanField(
        default=False,
        help_text=(
            "May post an open ask for a GM to run a story for this covenant "
            "(GroupStoryRequest, #2119). Distinct from can_invite — petitioning "
            "an outside GM commits the covenant to outside oversight."
        ),
    )

    class Meta:
        ordering = ["covenant", "tier"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant", "tier"], name="covenants_unique_rank_tier_per_covenant"
            ),
            models.UniqueConstraint(
                fields=["covenant", "name"], name="covenants_unique_rank_name_per_covenant"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} (tier {self.tier}) — {self.covenant.name}"


class CharacterCovenantRole(SharedMemoryModel):
    """Per-character record of a covenant role assignment.

    Slice A §3.3, §3.6. A character may hold the same CovenantRole across
    multiple covenants (memberships are non-exclusive), so the active-
    uniqueness key is (character_sheet, covenant) — not (character_sheet,
    covenant_role).

    Lifecycle:
    - active row: left_at IS NULL
    - historical row: left_at IS NOT NULL
    - engaged row: engaged=True, active (left_at IS NULL)

    The ``engaged`` flag marks runtime context — the covenant whose role
    bonuses are currently active and which is eligible for COVENANT_ROLE
    Thread pulls. At most one engaged active row per (character_sheet,
    covenant.covenant_type) is enforced by clean() and the service layer
    (a partial-index WHERE on a joined column is not expressible in Postgres).

    Covenant-scoped exclusivity (BATTLE only): at most one engaged active row
    per covenant may hold a SUPREME-tier ``covenant_role.command_tier``, and
    at most one may hold ``covenant_role.is_champion_role=True``. Also
    enforced by clean() and the service layer (set_engaged_membership) for
    the same reason.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="covenant_role_assignments",
    )
    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.PROTECT,
        related_name="character_assignments",
    )
    covenant = models.ForeignKey(
        COVENANT_MODEL,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    engaged = models.BooleanField(
        default=False,
        help_text=(
            "True when the character is currently 'fulfilling' this role for this "
            "covenant. At most one engaged active row per (character_sheet, "
            "covenant.covenant_type) — service-enforced + clean()-enforced. "
            "Drives role bonuses (modifier pipeline) and COVENANT_ROLE Thread pull "
            "eligibility. See spec 2026-05-09 §3.6."
        ),
    )
    rank = models.ForeignKey(
        "covenants.CovenantRank",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "covenant"],
                condition=models.Q(left_at__isnull=True),
                name="covenants_one_active_role_per_covenant",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.rank_id and self.rank.covenant_id != self.covenant_id:
            raise ValidationError(
                {"rank": "Rank must belong to the same covenant as the membership."}
            )
        if self.engaged and self.left_at is not None:
            raise ValidationError({"engaged": "Engaged row cannot have left_at set."})
        if self.engaged:
            self._validate_engaged_exclusivity()

    def _validate_engaged_exclusivity(self) -> None:
        """At most one engaged active role per covenant type + per special role.

        Guards against a second engaged active membership of the same covenant
        type, a second engaged Supreme Commander, and a second engaged Champion.
        """
        if self._another_same_type_engaged_exists():
            raise ValidationError(
                {
                    "engaged": (
                        "Another engaged active membership of the same covenant type "
                        "exists for this character."
                    ),
                }
            )
        if self.covenant_role.command_tier == CommandTier.SUPREME:
            if self._another_engaged_supreme_exists():
                raise ValidationError(
                    {
                        "engaged": (
                            "Another engaged Supreme Commander already exists for this covenant."
                        ),
                    }
                )
        if self.covenant_role.is_champion_role:
            if self._another_engaged_champion_exists():
                raise ValidationError(
                    {
                        "engaged": ("Another engaged Champion already exists for this covenant."),
                    }
                )

    def _another_same_type_engaged_exists(self) -> bool:
        """True if another active engaged membership of the same covenant type exists."""
        return (
            CharacterCovenantRole.objects.filter(
                character_sheet=self.character_sheet,
                covenant__covenant_type=self.covenant.covenant_type,
                engaged=True,
                left_at__isnull=True,
            )
            .exclude(pk=self.pk)
            .exists()
        )

    def _another_engaged_supreme_exists(self) -> bool:
        """True if another engaged Supreme Commander exists for this covenant."""
        return (
            CharacterCovenantRole.objects.filter(
                covenant=self.covenant,
                covenant_role__command_tier=CommandTier.SUPREME,
                engaged=True,
                left_at__isnull=True,
            )
            .exclude(pk=self.pk)
            .exists()
        )

    def _another_engaged_champion_exists(self) -> bool:
        """True if another engaged Champion exists for this covenant."""
        return (
            CharacterCovenantRole.objects.filter(
                covenant=self.covenant,
                covenant_role__is_champion_role=True,
                engaged=True,
                left_at__isnull=True,
            )
            .exclude(pk=self.pk)
            .exists()
        )

    def __str__(self) -> str:
        state = "active" if self.left_at is None else "ended"
        return f"{self.character_sheet}: {self.covenant_role.name} ({state})"


class CovenantLevelThreshold(SharedMemoryModel):
    """Legend total required to reach each covenant level. Authored content."""

    level = models.PositiveIntegerField(unique=True)
    required_legend = models.PositiveIntegerField()

    class Meta:
        ordering = ["level"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(level__gte=1),
                name="covenant_level_threshold_level_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"Level {self.level} (≥ {self.required_legend} legend)"


class CovenantLevelBonus(SharedMemoryModel):
    """Authored config: a permanent, engagement-gated member buff that scales with
    covenant level (#762).

    One row per ModifierTarget. An engaged member of a covenant receives a
    derive-on-read modifier of ``covenant.level * bonus_per_level`` for the
    target. Bonuses stack additively across a character's engaged covenants
    (mirrors covenant_role_bonus, spec 2026-05-09 §3.6). No CharacterModifier
    rows are persisted — the value is computed on read in
    ``world.mechanics.services.covenant_level_bonus``.
    """

    modifier_target = models.ForeignKey(
        "mechanics.ModifierTarget",
        on_delete=models.CASCADE,
        related_name="covenant_level_bonuses",
    )
    bonus_per_level = models.SmallIntegerField(
        help_text=(
            "Per-level coefficient. Final bonus for an engaged member = "
            "covenant.level * bonus_per_level, summed across engaged covenants."
        ),
    )

    class Meta:
        ordering = ["modifier_target"]
        constraints = [
            models.UniqueConstraint(
                fields=["modifier_target"],
                name="covenant_level_bonus_unique_target",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.modifier_target.name}: +{self.bonus_per_level}/level"


class VowStatScalingManager(NaturalKeyManager):
    """Manager for VowStatScaling with natural key support."""


class VowStatScaling(NaturalKeyMixin, SharedMemoryModel):
    """Authored vow-driven stat scaling keyed by (covenant_role, modifier_target) (#2022).

    Unlike ``CovenantRoleBonus`` (which scales by character level), this model
    scales by the character's **COVENANT_ROLE thread level** — so a deepened
    vow is a substantially stronger character. The scaling is authored data
    (coefficients per stat per role), not hardcoded.

    An engaged member holding the role receives a derive-on-read modifier of
    ``thread_level * bonus_per_level`` for the target. When the vow dims
    (#2051), the stat scaling drops — the character's stats collapse toward
    their base. No CharacterModifier rows are persisted.

    The mechanical heart of "solo darkness": without the vow, a character is
    a shadow of their roled self.
    """

    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.CASCADE,
        related_name="vow_stat_scalings",
    )
    modifier_target = models.ForeignKey(
        "mechanics.ModifierTarget",
        on_delete=models.CASCADE,
        related_name="vow_stat_scalings",
    )
    bonus_per_level = models.SmallIntegerField(
        help_text=(
            "Per-thread-level coefficient. Bonus for an engaged role holder = "
            "covenant_role_thread_level * bonus_per_level."
        ),
    )

    objects = VowStatScalingManager()

    class Meta:
        ordering = ["covenant_role", "modifier_target"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "modifier_target"],
                name="vow_stat_scaling_unique_role_target",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "modifier_target"]
        dependencies = [COVENANT_ROLE_MODEL, "mechanics.ModifierTarget"]

    def __str__(self) -> str:
        return (
            f"{self.covenant_role.name} / {self.modifier_target.name}: "
            f"+{self.bonus_per_level}/thread-level"
        )


class CovenantRoleActionScalingManager(NaturalKeyManager):
    """Manager for CovenantRoleActionScaling with natural key support."""


class CovenantRoleActionScaling(NaturalKeyMixin, SharedMemoryModel):
    """Authored per-role scaling for universal combat actions (#2529, was #2022).

    Keyed by ``(covenant_role, action_key)``. A Bulwark's interpose scales by
    the COVENANT_ROLE thread level; a Luminary's rally scales. Roles without a
    row contribute 0 (the action works at base). Replaced the archetype-keyed
    ``ArchetypeActionScaling`` when the single-archetype enum became the
    SWORD/SHIELD/CROWN blend; ``cast_technique`` scaling moved to the blend
    power term (``covenant_role_blend_power_term``).
    """

    covenant_role = models.ForeignKey(
        CovenantRole,
        on_delete=models.CASCADE,
        related_name="action_scalings",
    )
    action_key = models.CharField(
        max_length=50,
        help_text=(
            "The Action.key this scaling applies to (e.g. 'combat_interpose', 'combat_rally')."
        ),
    )
    thread_level_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=0,
        help_text=(
            "How much each COVENANT_ROLE thread level adds to the action's "
            "effect. 0 = no scaling (action works at base)."
        ),
    )

    objects = CovenantRoleActionScalingManager()

    class Meta:
        ordering = ["action_key", "covenant_role__slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "action_key"],
                name="covenant_role_action_scaling_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "action_key"]
        dependencies = [COVENANT_ROLE_MODEL]

    def __str__(self) -> str:
        return (
            f"{self.action_key} + {self.covenant_role.name}: ×{self.thread_level_multiplier}/level"
        )


class CovenantRoleTechniqueSpecialtyManager(NaturalKeyManager):
    """Manager for CovenantRoleTechniqueSpecialty with natural key support."""


class CovenantRoleTechniqueSpecialty(NaturalKeyMixin, SharedMemoryModel):
    """Per-vow finer-technique specialty: a role rewards a specific technique function.

    #2443, Layer 2 of the vow-power model. Keyed by ``(covenant_role, function)``.
    ``multiplier_tenths`` (integer-tenths, default 10 = ×1.0) scales the specialty's
    effect for that function label when the role is engaged; the consumer that reads
    this table is future wiring.

    Rows are valid on BOTH primary roles and sub-roles — unlike the SWORD/SHIELD/CROWN
    blend weights (which sub-roles must leave at zero), a sub-role may carry its own
    technique specialty rows that ADD on top of anything inherited from the parent
    role. No clean() restriction ties this table to primary-vs-sub-role shape.
    """

    covenant_role = models.ForeignKey(
        CovenantRole,
        on_delete=models.CASCADE,
        related_name="technique_specialties",
    )
    function = models.CharField(max_length=32, choices=TechniqueFunction.choices)
    multiplier_tenths = models.PositiveIntegerField(
        default=10,
        help_text="Integer-tenths scaling factor for this function (10 = ×1.0).",
    )

    objects = CovenantRoleTechniqueSpecialtyManager()

    class Meta:
        ordering = ["function", "covenant_role__slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "function"],
                name="covenant_role_technique_specialty_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "function"]
        dependencies = [COVENANT_ROLE_MODEL]

    def __str__(self) -> str:
        return (
            f"{self.covenant_role.name} + {self.get_function_display()}: "
            f"×{self.multiplier_tenths / 10}"
        )


class CovenantRoleDefenseProfileManager(NaturalKeyManager):
    """Manager for CovenantRoleDefenseProfile with natural key support."""


class CovenantRoleDefenseProfile(NaturalKeyMixin, SharedMemoryModel):
    """Per-role defense style + gear-substitution tuning (#2533, Layer 3).

    One row per ``CovenantRole`` — including sub-roles. This model imposes no
    parent/sub-role constraint: whether a sub-role's row replaces or extends
    its parent's defense profile is a resolution-time decision (Task 3's
    resolution helper), not a model-level restriction.

    ``style`` is the vow's ``DefenseStyle`` (how it defends). Combat resolution
    reads ``gear_additive_tenths`` when blending the vow's own defense with the
    character's COMPATIBLE armor soak: 10 (the default) keeps the legacy
    fully-additive behavior; lower values dial gear soak down for roles whose
    defense style is meant to substitute for gear rather than stack with it.
    """

    covenant_role = models.OneToOneField(
        CovenantRole,
        on_delete=models.CASCADE,
        related_name="defense_profile",
    )
    style = models.CharField(
        max_length=20,
        choices=DefenseStyle.choices,
        help_text="How this role's vow defends (#2533).",
    )
    gear_additive_tenths = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Fraction of COMPATIBLE armor soak that stays additive with the vow's "
            "own defense; 10 = fully additive (legacy behavior)."
        ),
    )

    objects = CovenantRoleDefenseProfileManager()

    class Meta:
        ordering = ["covenant_role__slug"]

    class NaturalKeyConfig:
        fields = ["covenant_role"]
        dependencies = [COVENANT_ROLE_MODEL]

    def __str__(self) -> str:
        return f"{self.covenant_role.name}: {self.get_style_display()}"


class CovenantRoleGiftGrant(SharedMemoryModel):
    """Through model for CovenantRole.granted_gifts (#2022).

    Carries ``unlock_thread_level`` — the COVENANT_ROLE thread level at which
    the gift's techniques become available while engaged. 0 = always available
    while engaged.
    """

    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.CASCADE,
        related_name="gift_grants",
    )
    gift = models.ForeignKey(
        "magic.Gift",
        on_delete=models.CASCADE,
        related_name="role_grants",
    )
    unlock_thread_level = models.PositiveIntegerField(
        default=0,
        help_text=(
            "The COVENANT_ROLE thread level at which this gift's techniques "
            "become available while engaged. 0 = always available."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "gift"],
                name="covenant_role_gift_grant_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.covenant_role.name} → {self.gift.name} (≥L{self.unlock_thread_level})"


class CovenantRoleBonusManager(NaturalKeyManager):
    """Manager for CovenantRoleBonus with natural key support."""


class CovenantRoleBonus(NaturalKeyMixin, SharedMemoryModel):
    """Authored config: per-(role, target) covenant role bonus scaling with the
    holder's character level (#985, Spec D §5.6).

    One row per (CovenantRole, ModifierTarget). An engaged member holding the role
    receives a derive-on-read modifier of ``character_level * bonus_per_level`` for
    the target, blended per equipped slot against mundane gear stats in
    ``world.mechanics.services.covenant_role_bonus`` (compatible → additive on top of
    the gear combat already counts; incompatible → ``max(0, role_bonus - gear_stat)``).
    No CharacterModifier rows are persisted.
    """

    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.CASCADE,
        related_name="role_bonuses",
    )
    modifier_target = models.ForeignKey(
        "mechanics.ModifierTarget",
        on_delete=models.CASCADE,
        related_name="covenant_role_bonuses",
    )
    bonus_per_level = models.SmallIntegerField(
        help_text=(
            "Per-level coefficient. Bonus for an engaged role holder = "
            "character_level * bonus_per_level."
        ),
    )

    objects = CovenantRoleBonusManager()

    class Meta:
        ordering = ["covenant_role", "modifier_target"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "modifier_target"],
                name="covenant_role_bonus_unique_role_target",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "modifier_target"]
        dependencies = [COVENANT_ROLE_MODEL, "mechanics.ModifierTarget"]

    def __str__(self) -> str:
        return (
            f"{self.covenant_role.name} / {self.modifier_target.name}: "
            f"+{self.bonus_per_level}/level"
        )


class CovenantRite(SharedMemoryModel):
    """Authored definition: a covenant-scoped group ritual ('rite') with an
    activation gate and a turnout-scaled shared buff. Sidecar on a Ritual so the
    generic Ritual table stays gate-free."""

    ritual = models.OneToOneField(
        "magic.Ritual",
        on_delete=models.CASCADE,
        related_name="covenant_rite",
    )
    covenant_type = models.CharField(
        max_length=32,
        choices=CovenantType.choices,
        blank=True,
        help_text="Restrict to this covenant type; blank = any.",
    )
    min_covenant_level = models.PositiveSmallIntegerField(default=1)
    min_members_present = models.PositiveSmallIntegerField(default=2)
    granted_condition = models.ForeignKey(
        CONDITION_TEMPLATE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    base_severity = models.PositiveSmallIntegerField(default=1)
    severity_per_extra_participant = models.PositiveSmallIntegerField(default=0)
    max_severity = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_rounds = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Override; blank uses the condition's UNTIL_END_OF_COMBAT default.",
    )

    def severity_for(self, *, present_count: int) -> int:
        extras = max(0, present_count - self.min_members_present)
        value = self.base_severity + self.severity_per_extra_participant * extras
        return min(value, self.max_severity) if self.max_severity is not None else value

    def package_for(self, role: CovenantRole | None, covenant_level: int) -> ConditionTemplate:
        """Return the ConditionTemplate for *role* at *covenant_level*.

        Selects the highest ``min_covenant_level`` band whose threshold does not
        exceed *covenant_level*. Falls back to ``self.granted_condition`` when no
        matching band exists (role unmapped or level below all authored bands).
        """
        match: CovenantRiteRolePackage | None = (
            self.role_packages.filter(
                covenant_role=role,
                min_covenant_level__lte=covenant_level,
            )
            .order_by("-min_covenant_level")
            .first()
        )
        return match.condition_template if match is not None else self.granted_condition

    class Meta:
        verbose_name = "Covenant Rite"
        verbose_name_plural = "Covenant Rites"


class CovenantRiteRolePackage(SharedMemoryModel):
    """Role- and level-gated stat package for a covenant rite.

    Staff can author a different ConditionTemplate for each (role, level-band)
    combination. ``CovenantRite.package_for`` selects the highest band whose
    ``min_covenant_level`` does not exceed the covenant's current level. If no
    matching band exists the rite falls back to ``CovenantRite.granted_condition``.

    Unique constraint: only one band per (rite, role, level) triple — prevents
    ambiguous selection.
    """

    rite = models.ForeignKey(
        "covenants.CovenantRite",
        on_delete=models.CASCADE,
        related_name="role_packages",
    )
    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    min_covenant_level = models.PositiveSmallIntegerField(default=1)
    condition_template = models.ForeignKey(
        CONDITION_TEMPLATE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rite", "covenant_role", "min_covenant_level"],
                name="covenant_rite_role_package_unique_band",
            )
        ]

    def __str__(self) -> str:
        return f"{self.rite} / {self.covenant_role.name} (level ≥ {self.min_covenant_level})"


class CovenantRiteInstance(SharedMemoryModel):
    """A live fired rite scoped to a combat encounter."""

    rite = models.ForeignKey(
        CovenantRite,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    covenant = models.ForeignKey(
        COVENANT_MODEL,
        on_delete=models.PROTECT,
        related_name="rite_instances",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="covenant_rite_instances",
    )
    combat_encounter = models.ForeignKey(
        "combat.CombatEncounter",
        on_delete=models.CASCADE,
        related_name="covenant_rite_instances",
        null=True,
        blank=True,
    )
    participants = models.ManyToManyField(
        CHARACTER_SHEET_MODEL,
        through="covenants.CovenantRiteParticipant",
        related_name="covenant_rite_instances",
    )
    fired_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class CovenantRiteParticipant(SharedMemoryModel):
    """Through model recording each participant's own granted condition in a rite instance.

    Each participant receives the ConditionTemplate chosen by their CovenantRole +
    the covenant's level (via CovenantRite.package_for). This record is used by the
    late-join rescale and combat-end sweep to act on each participant's OWN condition
    rather than a single shared granted_condition.
    """

    instance = models.ForeignKey(
        "covenants.CovenantRiteInstance",
        on_delete=models.CASCADE,
        related_name="participant_records",
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )
    granted_condition = models.ForeignKey(
        CONDITION_TEMPLATE_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "character_sheet"],
                name="covenant_rite_participant_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} in rite #{self.instance_id} ({self.granted_condition})"


# =============================================================================
# MentorBondConfig — singleton config for Mentor's Vow scaling (#1165)
# =============================================================================


class MentorBondConfig(SharedMemoryModel):
    """Singleton (pk=1): global parameters for Mentor's Vow bond scaling (#1165).

    Seeded by seed_mentor_bond_defaults() in factories.py. Services use
    cached_singleton() and let DoesNotExist propagate loudly. Updated via
    Django admin.

    Fields:
    - band_width: level-range half-width for eligible mentor/sidekick pairs.
    - adjacency_offset: additional level offset applied when computing adjacency.
    - max_sidekicks_per_mentor: cap on sidekick count; null means unlimited.
    """

    objects = ArxSharedMemoryManager()

    band_width = models.PositiveSmallIntegerField(
        default=MENTOR_BOND_BAND_WIDTH,
        help_text="Level-range half-width for eligible mentor/sidekick pairs.",
    )
    adjacency_offset = models.PositiveSmallIntegerField(
        default=MENTOR_BOND_ADJACENCY_OFFSET,
        help_text="Additional level offset applied when computing adjacency.",
    )
    max_sidekicks_per_mentor = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=MENTOR_BOND_MAX_SIDEKICKS,
        help_text="Cap on sidekick count per mentor; null means unlimited.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mentor_bond_config_updates",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"MentorBondConfig(pk={self.pk})"


# =============================================================================
# CourtGrantConfig — singleton config for Court grant negotiation (#1718)
# =============================================================================


class CourtGrantConfig(SharedMemoryModel):
    """Singleton (pk=1): tuning knobs for Court grant negotiation (#1718).

    Lazy get-or-created via get_court_grant_config() — unlike MentorBondConfig
    (strict .get(pk=1), authored content), this config has no per-instance
    authored content of its own; only petition_check_type/escalation_consequence_pool
    point at authored content (seeded by wire_court_grant_petition_content(),
    Task 5), and those two FKs are nullable so the config itself never needs a
    migration-time seed.
    """

    base_headroom = models.PositiveSmallIntegerField(
        default=1,
        help_text="Ceiling floor before any affection/mission credit is added.",
    )
    affection_divisor = models.PositiveSmallIntegerField(
        default=10,
        help_text="Master's NPCStanding.affection // this = ceiling bonus.",
    )
    mission_divisor = models.PositiveSmallIntegerField(
        default=2,
        help_text="Completed Court missions for the master's org // this = ceiling bonus.",
    )
    emergency_draw_max_bonus = models.PositiveSmallIntegerField(
        default=5,
        help_text="Max a single emergency thread-bond draw may exceed the ceiling by.",
    )
    debt_repay_affection_divisor = models.PositiveSmallIntegerField(
        default=10,
        help_text="Affection gained since debt was incurred // this = debt repaid.",
    )
    debt_repay_mission_divisor = models.PositiveSmallIntegerField(
        default=2,
        help_text="Missions completed since debt was incurred // this = debt repaid.",
    )
    petition_failure_escalation_threshold = models.PositiveSmallIntegerField(
        default=3,
        help_text="Consecutive failed petitions before the master's wrath fires.",
    )
    summons_refusal_escalation_threshold = models.PositiveSmallIntegerField(
        default=3,
        help_text=(
            "Consecutive refused summonses before the master's escalation pool "
            "fires (#2050). Mirrors `petition_failure_escalation_threshold`."
        ),
    )
    summons_refusal_escalation_pool = models.ForeignKey(
        "actions.ConsequencePool",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Fires when a servant's consecutive-refused-summons streak crosses "
            "the threshold. Defaults to `escalation_consequence_pool` when null."
        ),
    )
    petition_check_type = models.ForeignKey(
        "checks.CheckType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Shared check rolled for every Court grant petition/emergency draw.",
    )
    petition_base_difficulty = models.SmallIntegerField(
        default=0,
        help_text="Base target_difficulty for petition_check_type before affection easing.",
    )
    escalation_consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Fires when a servant's consecutive-failed-petition streak crosses the threshold."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"CourtGrantConfig(pk={self.pk})"


# =============================================================================
# MentorBond — per-pair bond record for Mentor's Vow (#1165)
# =============================================================================


class MentorBondQuerySet(models.QuerySet):
    """Custom queryset for MentorBond."""

    def active(self) -> MentorBondQuerySet:
        """Return only bonds where dissolved_at IS NULL (i.e. currently active)."""
        return self.filter(dissolved_at__isnull=True)


class MentorBond(SharedMemoryModel):
    """A single Mentor's Vow bond between a mentor and a sidekick within a covenant (#1165).

    Active = dissolved_at IS NULL. Dissolving sets dissolved_at to a timestamp.
    The partial unique constraint ``unique_active_sidekick_bond`` allows at most
    one active bond per (covenant, sidekick_sheet) pair; historical dissolved bonds
    are unconstrained and serve as an audit trail.

    adjusted_party records which party the encounter-scaling adjustment is applied
    to (MENTOR or SIDEKICK) for any given bond.
    """

    covenant = models.ForeignKey(
        COVENANT_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_bonds",
    )
    mentor_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_bonds_as_mentor",
    )
    sidekick_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="mentor_bonds_as_sidekick",
    )
    adjusted_party = models.CharField(
        max_length=20,
        choices=MentorBondAdjusted.choices,
        default=MentorBondAdjusted.SIDEKICK,
        help_text="Which party the encounter-scaling adjustment is applied to.",
    )
    formed_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the bond is dissolved; null means currently active.",
    )

    objects = MentorBondQuerySet.as_manager()

    class Meta:
        ordering = ["-formed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant", "sidekick_sheet"],
                condition=models.Q(dissolved_at__isnull=True),
                name="unique_active_sidekick_bond",
            ),
        ]

    def __str__(self) -> str:
        state = "active" if self.dissolved_at is None else "dissolved"
        return (
            f"MentorBond({self.mentor_sheet} → {self.sidekick_sheet} in {self.covenant}, {state})"
        )


# =============================================================================
# CourtPact — sworn-fealty bond between a Court covenant and a servant (#1589)
# =============================================================================


class CourtPactQuerySet(models.QuerySet):
    """Custom queryset for CourtPact."""

    def active(self) -> CourtPactQuerySet:
        """Return only pacts where released_at IS NULL (i.e. currently active)."""
        return self.filter(released_at__isnull=True)


class CourtPact(SharedMemoryModel):
    """A single sworn-fealty bond between a Court covenant and a servant character (#1589).

    Active = released_at IS NULL. Releasing sets released_at to a timestamp.
    The partial unique constraint ``uniq_court_pact_active`` allows at most
    one active pact per (covenant, servant_sheet) pair; historical released pacts
    are unconstrained and serve as an audit trail.

    granted_pull_cap is a master-set ceiling on the servant's Court-role thread level;
    0 means the master has granted nothing — the effective cap is 0, so the servant
    cannot pull their Court-role thread.
    """

    covenant = models.ForeignKey(
        COVENANT_MODEL,
        on_delete=models.PROTECT,
        related_name="court_pacts",
    )
    servant_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.PROTECT,
        related_name="court_pacts",
    )
    granted_pull_cap = models.PositiveSmallIntegerField(
        default=0,
        help_text="Master-set ceiling on the servant's Court-role thread level.",
    )
    sworn_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the pact is released; null means currently active.",
    )

    objects = CourtPactQuerySet.as_manager()

    class Meta:
        ordering = ["covenant", "servant_sheet"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant", "servant_sheet"],
                condition=models.Q(released_at__isnull=True),
                name="uniq_court_pact_active",
            ),
        ]

    def __str__(self) -> str:
        state = "active" if self.released_at is None else "released"
        return f"CourtPact({self.servant_sheet} → {self.covenant}, {state})"


# =============================================================================
# VowSituationalPerk — per-vow situational perks (#2536, Layer 4)
# =============================================================================


class VowSituationalPerkManager(NaturalKeyManager):
    """Manager for VowSituationalPerk with natural key support."""


class VowSituationalPerk(NaturalKeyMixin, SharedMemoryModel):
    """Authored per-vow situational perk: a conditional bonus that fires when
    its attached situations hold (#2536, Layer 4 of the vow-power model).

    Keyed by ``(covenant_role, name)``. Rows are valid on BOTH primary roles
    and sub-roles — like ``CovenantRoleTechniqueSpecialty``, a sub-role's
    perks ADD to whatever the anchor (parent) role's rows grant; there is no
    clean() restriction tying this table to primary-vs-sub-role shape.

    ``beneficiary`` decides who benefits when this perk fires at ANOTHER
    character's resolution moment (``perks.services.applicable_perks``, Task
    3): SELF perks fire only for the holder's own actions; COVENANT_ALLIES /
    WHOLE_GROUP perks fire for a co-present covenant-mate's action too
    (membership + co-presence — the mate's OWN engaged flag is irrelevant,
    Tehom's 2026-07-20 reversal; the ACTING character still needs their own
    engaged vow) (WHOLE_GROUP includes the holder, COVENANT_ALLIES excludes
    them).

    ``magnitude_tenths`` is the base numeric contribution (integer-tenths,
    10 = ×1.0), scaled by the acting character's thread level at resolution
    time. No negative magnitudes anywhere in this table — ``PositiveIntegerField``
    makes the no-negative-perks ruling (#2536 decision 2: a vow's weakness is
    the absence of a perk, never a malus) structural, not just a convention.

    ``check_type`` scopes ``CHECK_BONUS`` perks to a single ``checks.CheckType``;
    null means "any check" (mirrors ``CheckTypeCapabilityModifier``'s optional
    scoping precedent, ``checks/models.py:119``). Only meaningful when
    ``effect_kind=CHECK_BONUS`` — now that CHECK_BONUS is live (#2536, Task 5),
    ``clean()`` rejects a ``check_type`` authored on a non-CHECK_BONUS row as a
    content-authoring guard (a stray scope on a POWER_BONUS/TIER_FLOOR/
    BOTCH_IMMUNITY perk can never be read by any resolution service, so it is
    caught at author time rather than silently ignored).

    ``floor_success_level`` is the authored outcome-guarantee floor (canonical
    -10..+10 scale) for a ``TIER_FLOOR`` perk — the resolved outcome cannot
    land below this ``success_level``. Absolute, never thread-scaled (spec §6).
    Only meaningful when ``effect_kind=TIER_FLOOR``; the same authoring-guard
    symmetry as ``check_type`` applies both directions — ``clean()`` requires
    it on a TIER_FLOOR row and rejects it on any other ``effect_kind`` (#2536
    slice 2).

    Three scope columns narrow WHEN a fired perk actually applies — Court and
    Battle scoping (#2536 slice 3). Every NON-empty scope on a row must match
    the resolving ``SituationContext`` (AND semantics — see
    ``perks.services.perk_scope_matches``, the single seam both
    ``checks.services._situational_perk_check_bonus`` and
    ``magic.services.power_terms.vow_situational_power_term`` filter through)
    for the firing to survive; an empty scope always matches. ``mission_category``
    and ``mission_template`` are only meaningful when ``effect_kind=CHECK_BONUS``
    (mission checks are CHECK_BONUS-only) — ``clean()`` rejects either authored
    on any other ``effect_kind``. ``battle_action_kind`` is meaningful on
    ``CHECK_BONUS`` **or** ``POWER_BONUS`` (spec §4: a Battle warfare roll scopes
    both the check AND the technique cast it may carry) — ``clean()`` rejects it
    authored on ``TIER_FLOOR``/``BOTCH_IMMUNITY``.
    """

    covenant_role = models.ForeignKey(
        COVENANT_ROLE_MODEL,
        on_delete=models.CASCADE,
        related_name="situational_perks",
    )
    name = models.CharField(
        max_length=80,
        help_text="Announced label, e.g. 'Scout's Instinct'.",
    )
    beneficiary = models.CharField(max_length=20, choices=PerkBeneficiary.choices)
    effect_kind = models.CharField(max_length=20, choices=PerkEffectKind.choices)
    magnitude_tenths = models.PositiveIntegerField(
        default=10,
        help_text="Integer-tenths base magnitude (10 = ×1.0) before thread-level scaling.",
    )
    announce_template = models.CharField(
        max_length=200,
        help_text="Player-facing announce line; {holder}/{subject} placeholders.",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="situational_perks",
        help_text="CHECK_BONUS scope; null = any check.",
    )
    floor_success_level = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "TIER_FLOOR only: the resolved outcome cannot land below this "
            "success_level (canonical -10..+10 scale). Absolute — outcome "
            "guarantees never thread-scale."
        ),
    )
    mission_category = models.ForeignKey(
        "missions.MissionCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="situational_perks",
        help_text=(
            "CHECK_BONUS scope: fires only on a mission whose template carries this category."
        ),
    )
    mission_template = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="situational_perks",
        help_text="CHECK_BONUS scope: fires only on a check driven by this specific mission.",
    )
    battle_action_kind = models.CharField(
        max_length=20,
        choices=BattleActionKind.choices,
        blank=True,
        default="",
        help_text="CHECK_BONUS/POWER_BONUS scope: fires only on this declared warfare action kind.",
    )

    objects = VowSituationalPerkManager()

    class Meta:
        ordering = ["covenant_role__slug", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["covenant_role", "name"],
                name="vow_situational_perk_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["covenant_role", "name"]
        dependencies = [COVENANT_ROLE_MODEL]

    def clean(self) -> None:
        super().clean()
        if self.check_type_id is not None and self.effect_kind != PerkEffectKind.CHECK_BONUS:
            raise ValidationError(
                {"check_type": "check_type is only meaningful when effect_kind=CHECK_BONUS."}
            )
        if self.effect_kind == PerkEffectKind.TIER_FLOOR and self.floor_success_level is None:
            raise ValidationError(
                {"floor_success_level": "TIER_FLOOR perks must set floor_success_level."}
            )
        if self.floor_success_level is not None and self.effect_kind != PerkEffectKind.TIER_FLOOR:
            raise ValidationError(
                {
                    "floor_success_level": (
                        "floor_success_level is only meaningful when effect_kind=TIER_FLOOR."
                    )
                }
            )
        if self.mission_category_id is not None and self.effect_kind != PerkEffectKind.CHECK_BONUS:
            raise ValidationError(
                {
                    "mission_category": (
                        "mission_category is only meaningful when effect_kind=CHECK_BONUS."
                    )
                }
            )
        if self.mission_template_id is not None and self.effect_kind != PerkEffectKind.CHECK_BONUS:
            raise ValidationError(
                {
                    "mission_template": (
                        "mission_template is only meaningful when effect_kind=CHECK_BONUS."
                    )
                }
            )
        if self.battle_action_kind and self.effect_kind not in (
            PerkEffectKind.CHECK_BONUS,
            PerkEffectKind.POWER_BONUS,
        ):
            raise ValidationError(
                {
                    "battle_action_kind": (
                        "battle_action_kind is only meaningful when effect_kind=CHECK_BONUS "
                        "or effect_kind=POWER_BONUS."
                    )
                }
            )

    def __str__(self) -> str:
        return f"{self.covenant_role.name}: {self.name}"


class VowSituationalPerkSituationManager(NaturalKeyManager):
    """Manager for VowSituationalPerkSituation with natural key support."""


class VowSituationalPerkSituation(NaturalKeyMixin, SharedMemoryModel):
    """One AND-composed situation attached to a ``VowSituationalPerk`` (#2536).

    ALL situations attached to a perk must hold simultaneously for the perk's
    base magnitude to apply (AND semantics — see
    ``perks.services.applicable_perks``, Task 3). Keyed by ``(perk, situation)``.
    """

    perk = models.ForeignKey(
        "covenants.VowSituationalPerk",
        on_delete=models.CASCADE,
        related_name="situations",
    )
    situation = models.CharField(max_length=32, choices=Situation.choices)

    objects = VowSituationalPerkSituationManager()

    class Meta:
        ordering = ["perk", "situation"]
        constraints = [
            models.UniqueConstraint(
                fields=["perk", "situation"],
                name="vow_situational_perk_situation_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["perk", "situation"]
        dependencies = ["covenants.VowSituationalPerk"]

    def __str__(self) -> str:
        return f"{self.perk.name}: {self.get_situation_display()}"


class VowSituationalPerkRungManager(NaturalKeyManager):
    """Manager for VowSituationalPerkRung with natural key support."""


class VowSituationalPerkRung(NaturalKeyMixin, SharedMemoryModel):
    """An escalation rung on a ``VowSituationalPerk`` (#2536, worked-example
    implication #2 — "perks can escalate in tiers").

    Resolution rule (formalized in the spec, §2): rung N's required
    situations = the perk's base situations UNION the extra situations of
    rungs 1..N — strictly cumulative; a higher rung can never fire without
    every lower rung's ``extra_situation`` also holding. The highest
    qualifying rung's magnitude REPLACES the base magnitude (never sums with
    it). Keyed by ``(perk, rung_number)``.

    ``rung_number`` must be >= 1 (enforced in ``clean()`` — ``PositiveIntegerField``
    alone permits 0). Contiguity is NOT enforced: rung numbers may have gaps —
    the resolution service walks whatever rungs exist in ``rung_number`` order.
    """

    perk = models.ForeignKey(
        "covenants.VowSituationalPerk",
        on_delete=models.CASCADE,
        related_name="rungs",
    )
    rung_number = models.PositiveIntegerField(help_text="Escalation order; must be >= 1.")
    extra_situation = models.CharField(max_length=32, choices=Situation.choices)
    magnitude_tenths = models.PositiveIntegerField(
        default=10,
        help_text="Integer-tenths magnitude for this rung; replaces the base when it fires.",
    )

    objects = VowSituationalPerkRungManager()

    class Meta:
        ordering = ["perk", "rung_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["perk", "rung_number"],
                name="vow_situational_perk_rung_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["perk", "rung_number"]
        dependencies = ["covenants.VowSituationalPerk"]

    def clean(self) -> None:
        super().clean()
        if self.rung_number is not None and self.rung_number < 1:
            raise ValidationError({"rung_number": "rung_number must be >= 1."})

    def __str__(self) -> str:
        return f"{self.perk.name} rung {self.rung_number}: {self.get_extra_situation_display()}"
