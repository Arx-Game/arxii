"""Kinship graph (#2062): Family container + person-nodes with typed edges.

The person-centric inversion of Arx 1's parentage-line derivation. Facts are
explicit and typed; every relationship readout (sibling, cousin, step-parent,
in-law) is DERIVED by walking edges — nothing like "cousin" is ever stored.

Truth vs public record: edges/unions/incarnations carry ``is_public_record``
and ``is_true``. A public-but-false edge is what the world believes; the
hidden-true edge behind it anchors a ``secrets.Secret`` (consumer→primitive,
ADR-0010) so who-knows/discovery/clues ride the existing secrets machinery.
A hidden fact with NO secret is staff-only. Viewer-aware reads live in
``world.roster.services.kinship``.

Node definition tiers align with the real NPC ladder (name-only →
functionary → standing → sheeted → PC); nodes are promoted up-tier when a
story makes them load-bearing. Reincarnation is modeled as souls with
ordered incarnations, so chains (PC ← Monique ← Covet) are transitively
consistent by construction and knowledge is per-life.
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.roster.constants import (
    DefinitionTier,
    MembershipBasis,
    MembershipEndReason,
    ParentageKind,
)

_SHEET_FK = "character_sheets.CharacterSheet"
_SECRET_FK = "secrets.Secret"  # noqa: S105 — model path, not a credential
_GENDER_FK = "character_sheets.Gender"


class Family(NaturalKeyMixin, SharedMemoryModel):
    """A family/house surname container that Kinsperson nodes claim membership in.

    Kept from the pre-#2062 model (CG drafts and ``Profile.family`` point
    here). Nodes are NOT owned by a family — membership is a claim
    (``FamilyMembership``); ``Kinsperson.family`` denormalizes the current
    primary surname. #1884 attaches house Organizations from the org side.
    """

    class FamilyType(models.TextChoices):
        COMMONER = "commoner", "Commoner"
        NOBLE = "noble", "Noble"
        CRIME = "crime", "Crime"

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Family/house name",
    )
    family_type = models.CharField(
        max_length=20,
        choices=FamilyType.choices,
        default=FamilyType.COMMONER,
        help_text="Whether this is a noble house, commoner family, or crime family",
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the family",
    )
    is_playable = models.BooleanField(
        default=True,
        help_text="Whether players can select this family in character creation",
    )
    created_by_cg = models.BooleanField(
        default=False,
        help_text="True if created during character generation (commoner only)",
    )
    created_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_families",
        help_text="Account that created this family (staff or player-created commoner)",
    )
    origin_realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="families",
        help_text=(
            "Canonical realm this family is associated with; used to filter in character "
            "creation and (#1884) to resolve the nobiliary particle"
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Family"
        verbose_name_plural = "Families"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Kinsperson(SharedMemoryModel):
    """A person-node in the kinship graph (#2062).

    Exists at one of five definition tiers (see ``DefinitionTier``): from a
    bare name that will never be referenced again, up to a PC's sheet.
    Anchors are tier-appropriate and optional; ``name`` is the display
    fallback whenever no sheet is bound. Nodes are never family-owned —
    ``family`` is the denormalized current primary surname, maintained by
    the membership services.
    """

    definition_tier = models.CharField(
        max_length=20,
        choices=DefinitionTier.choices,
        default=DefinitionTier.NAME_ONLY,
        help_text="How defined this person is; services promote up-tier only.",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display name for unbound nodes (sheet-bound nodes read the sheet).",
    )
    description = models.TextField(
        blank=True,
        help_text="Blurb for described/NPC tiers.",
    )
    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Approximate age, when it matters for slot constraints or flavor.",
    )
    gender = models.ForeignKey(
        _GENDER_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kinspeople",
        help_text="Gender for unbound nodes (sheet-bound nodes read the sheet).",
    )
    sheet = models.OneToOneField(
        _SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kinsperson",
        help_text="Bound CharacterSheet (SHEETED / PC tiers).",
    )
    functionary = models.ForeignKey(
        "npc_services.Functionary",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kinspeople",
        help_text="Functionary anchor (FUNCTIONARY tier): a named, room-referenced NPC.",
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        help_text=(
            "Current primary surname family — a denorm maintained by the membership "
            "services; FamilyMembership rows carry the history and basis."
        ),
    )
    is_deceased = models.BooleanField(default=False)

    # --- Appable-slot fields (#2062 slot mountain) ---------------------------
    is_appable = models.BooleanField(
        default=False,
        help_text="Whether an OC in CG may claim this node (binds their new sheet).",
    )
    name_locked = models.BooleanField(
        default=False,
        help_text="Whether a claimant must keep the pre-authored name.",
    )
    age_min = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Slot constraint: minimum age for a claimant.",
    )
    age_max = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Slot constraint: maximum age for a claimant.",
    )
    allowed_genders = models.ManyToManyField(
        _GENDER_FK,
        blank=True,
        related_name="+",
        help_text="Slot constraint: allowed claimant genders. Empty = unconstrained.",
    )
    deferred_definer = models.ForeignKey(
        _SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deferred_kin",
        help_text=(
            "The sheet allowed to define this deliberately-blank position later "
            "(CG deferral). Post-CG definition is review-gated."
        ),
    )

    # --- Provenance -----------------------------------------------------------
    created_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_kinspeople",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kinsperson"
        verbose_name_plural = "Kinspeople"
        ordering = ["pk"]
        indexes = [
            models.Index(fields=["family", "is_appable"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.definition_tier})"

    @property
    def display_name(self) -> str:
        if self.sheet is not None:
            return str(self.sheet)
        return self.name or "Unnamed"


class FamilyMembership(SharedMemoryModel):
    """A Kinsperson's claim of belonging to a Family, with basis and dates (#2062).

    The history + law input succession queries read (#1884). The node's
    ``family`` denorm mirrors the single active membership marked primary.
    """

    kinsperson = models.ForeignKey(
        Kinsperson,
        on_delete=models.CASCADE,
        related_name="family_memberships",
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    basis = models.CharField(
        max_length=20,
        choices=MembershipBasis.choices,
        help_text="How this person came to belong (born/married-in/adopted/...).",
    )
    is_primary = models.BooleanField(
        default=True,
        help_text="Whether this is the surname-carrying membership.",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(
        max_length=20,
        choices=MembershipEndReason.choices,
        blank=True,
        help_text="Why it ended (disowned/married-out/...). Blank while active.",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["family", "ended_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kinsperson_id} in {self.family_id} ({self.basis})"


class UnionKind(NaturalKeyMixin, SharedMemoryModel):
    """Authorable union vocabulary (marriage, consortium, concubinage...) (#2062).

    Rows, not an enum — realms name their unions differently and the law
    reads ``confers_wedlock`` for legitimacy questions.
    """

    name = models.CharField(max_length=80, unique=True)
    realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="union_kinds",
        help_text="Realm whose law names this union kind. Null = universal.",
    )
    confers_wedlock = models.BooleanField(
        default=True,
        help_text="Whether births within this union count as in-wedlock for law.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Union(SharedMemoryModel):
    """A union (marriage/partnership) between two or more Kinspeople (#2062).

    Makes in-laws and step-parents derivable and stamps in-wedlock onto
    births. Secret unions exist: same truth/record trio as edges.
    """

    kind = models.ForeignKey(
        UnionKind,
        on_delete=models.PROTECT,
        related_name="unions",
    )
    members = models.ManyToManyField(
        Kinsperson,
        related_name="unions",
        help_text="Two or more members, any composition.",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_public_record = models.BooleanField(
        default=True,
        help_text="Whether the world knows this union exists.",
    )
    is_true = models.BooleanField(
        default=True,
        help_text="False = a believed-but-sham union (the record lies).",
    )
    secret = models.ForeignKey(
        _SECRET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Secret gating a hidden union. Hidden with no secret = staff-only.",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"Union<{self.kind.name}>(#{self.pk})"


class ParentageEdge(SharedMemoryModel):
    """A typed parent→child link (#2062). N parents per child, any composition.

    ``born_within_union`` stamps wedlock at birth-recording for the law
    layer (#1884). Public-false + hidden-true pairs model "what everyone
    believes is wrong"; the hidden edge's ``secret`` is who-knows.
    """

    child = models.ForeignKey(
        Kinsperson,
        on_delete=models.CASCADE,
        related_name="parentage_up",
        help_text="The child end of the edge.",
    )
    parent = models.ForeignKey(
        Kinsperson,
        on_delete=models.CASCADE,
        related_name="parentage_down",
        help_text="The parent end of the edge.",
    )
    kind = models.CharField(
        max_length=20,
        choices=ParentageKind.choices,
        default=ParentageKind.BIOLOGICAL,
    )
    is_public_record = models.BooleanField(
        default=True,
        help_text="Whether the world believes this edge.",
    )
    is_true = models.BooleanField(
        default=True,
        help_text="False = the official story, contradicted by a hidden-true edge.",
    )
    born_within_union = models.ForeignKey(
        Union,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="births",
        help_text="The union this birth occurred within, if any (legitimacy input).",
    )
    secret = models.ForeignKey(
        _SECRET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Secret gating a hidden edge. Hidden with no secret = staff-only.",
    )

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["child", "parent", "kind"],
                name="roster_parentage_unique_per_kind",
            ),
            models.CheckConstraint(
                check=~models.Q(child=models.F("parent")),
                name="roster_parentage_no_self_loop",
            ),
        ]
        indexes = [
            models.Index(fields=["child", "is_public_record"]),
            models.Index(fields=["parent", "is_public_record"]),
        ]

    def __str__(self) -> str:
        return f"{self.parent_id} -{self.kind}-> {self.child_id}"


class Soul(SharedMemoryModel):
    """A soul with an ordered chain of incarnations (#2062).

    First-class so reincarnation chains are transitively consistent by
    construction, and so the Tree of Souls / future soul-magic have a real
    anchor. Usually unnamed — staff notes only.
    """

    notes = models.TextField(
        blank=True,
        help_text="Staff notes (never player-facing).",
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"Soul(#{self.pk})"


class SoulIncarnation(SharedMemoryModel):
    """One life of a soul (#2062). Knowledge is per-membership.

    Learning your own membership makes you the famous ancestor's
    reincarnation the moment THEIR membership is public — while an
    intermediate life stays its own undiscovered fact. ``is_true=False``
    models falsely-believed reincarnations.
    """

    soul = models.ForeignKey(
        Soul,
        on_delete=models.CASCADE,
        related_name="incarnations",
    )
    kinsperson = models.ForeignKey(
        Kinsperson,
        on_delete=models.CASCADE,
        related_name="incarnations",
    )
    sequence = models.PositiveIntegerField(
        help_text="Order within the soul's chain (1 = earliest known life).",
    )
    is_public_record = models.BooleanField(default=False)
    is_true = models.BooleanField(default=True)
    secret = models.ForeignKey(
        _SECRET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Secret gating a hidden membership. Hidden with no secret = staff-only.",
    )

    class Meta:
        ordering = ["soul", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["soul", "kinsperson"],
                name="roster_soul_incarnation_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"Soul {self.soul_id} life {self.sequence}: {self.kinsperson_id}"


class KinSlotPool(SharedMemoryModel):
    """Fuzzy appable capacity: "N children available among these parents" (#2062).

    Claiming from the pool mints a Kinsperson with pre-authored parentage
    edges to the pool's parents, then binds the claimant's sheet at CG
    finalization. Explicit appable nodes cover defined positions; pools
    cover the loose remainder staff don't want to pre-place.
    """

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="kin_slot_pools",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text='Player-facing pool blurb, e.g. "children of the current nobles".',
    )
    parents = models.ManyToManyField(
        Kinsperson,
        related_name="kin_slot_pools",
        help_text="The parent-set minted children link to.",
    )
    count_remaining = models.PositiveIntegerField(
        help_text="Slots left in this pool; claiming decrements.",
    )
    allowed_genders = models.ManyToManyField(
        _GENDER_FK,
        blank=True,
        related_name="+",
        help_text="Constraint on minted claimants. Empty = unconstrained.",
    )
    age_min = models.PositiveIntegerField(null=True, blank=True)
    age_max = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["family", "pk"]

    def __str__(self) -> str:
        return f"{self.family.name} pool: {self.description or 'kin'} ({self.count_remaining})"
