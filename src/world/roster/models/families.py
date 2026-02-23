"""
Family model for character lineage.

Simple model to track which characters belong to which family.
Staff can change a character's family at any time (e.g., for secret heritage reveals).

TODO: Add relationship tracking between family members
TODO: Add domain/wargame mechanics for noble houses
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class Family(NaturalKeyMixin, SharedMemoryModel):
    """
    A family/house that characters can belong to.

    Uses SharedMemoryModel for performance since families are accessed
    frequently but changed rarely.
    """

    class FamilyType(models.TextChoices):
        COMMONER = "commoner", "Commoner"
        NOBLE = "noble", "Noble"

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Family/house name",
    )
    family_type = models.CharField(
        max_length=20,
        choices=FamilyType.choices,
        default=FamilyType.COMMONER,
        help_text="Whether this is a noble house or commoner family",
    )
    description = models.TextField(
        blank=True,
        help_text="Brief description of the family",
    )
    is_playable = models.BooleanField(
        default=True,
        help_text="Whether players can select this family in character creation",
    )
    # True if created during character generation (commoner only)
    created_by_cg = models.BooleanField(
        default=False,
        help_text="True if created during character generation (commoner only)",
    )

    # Record the account who created this family (helpful for provenance/contact)
    created_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_families",
        help_text="Account that created this family (staff or player-created commoner)",
    )

    # Canonical origin realm (realms.Realm) rather than pointing at character_creation
    origin_realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="families",
        help_text=(
            "Canonical realm this family is associated with; used to filter in character creation"
        ),
    )

    # TODO: domain = models.ForeignKey('domains.Domain', ...) - for noble house mechanics
    # TODO: prestige = models.IntegerField(default=0) - for wargame mechanics

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Family"
        verbose_name_plural = "Families"

    def __str__(self) -> str:
        return self.name


class FamilyMember(models.Model):
    """
    Individual member of a family tree.

    Members can be:
    - CHARACTER: Finalized player character
    - PLACEHOLDER: Open position for another player to app into
    - NPC: Non-playable family member (background only)

    Family trees are created during character creation and can be expanded
    post-approval by players or staff.
    """

    class MemberType(models.TextChoices):
        CHARACTER = "character", "Character"
        PLACEHOLDER = "placeholder", "Placeholder"
        NPC = "npc", "NPC"

    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="tree_members",
        help_text="Family this member belongs to",
    )
    member_type = models.CharField(
        max_length=20,
        choices=MemberType.choices,
        help_text="Type of family member",
    )
    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_member",
        help_text="Character object if member_type is CHARACTER",
    )

    # Placeholder/NPC data
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name for placeholder or NPC members",
    )
    description = models.TextField(
        blank=True,
        help_text="Description for placeholder positions or NPC background",
    )
    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Age of member (optional)",
    )

    # Parent references for deriving relationships
    mother = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children_as_mother",
        help_text="Mother of this family member",
    )
    father = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children_as_father",
        help_text="Father of this family member",
    )

    # Provenance
    created_by = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_family_members",
        help_text="Account that created this family member",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this family member was created",
    )

    class Meta:
        verbose_name = "Family Member"
        verbose_name_plural = "Family Members"

    def __str__(self) -> str:
        if self.character:
            return f"{self.character.key} ({self.family.name})"
        return f"{self.name or 'Unnamed'} ({self.family.name})"

    def get_display_name(self) -> str:
        """Get the display name for this family member."""
        if self.character:
            return self.character.key
        return self.name or "Unnamed"

    @property
    def parents(self) -> list["FamilyMember"]:
        """Return list of parents (mother and/or father)."""
        return [p for p in [self.mother, self.father] if p is not None]

    @property
    def children(self) -> list["FamilyMember"]:
        """Return list of children."""
        return list(self.children_as_mother.all()) + list(self.children_as_father.all())

    @property
    def siblings(self) -> list["FamilyMember"]:
        """Return list of siblings (share at least one parent)."""
        sibling_set: set[FamilyMember] = set()
        for parent in self.parents:
            for child in parent.children:
                if child.pk != self.pk:
                    sibling_set.add(child)
        return list(sibling_set)

    def get_ancestors(self, max_depth: int = 10) -> list["FamilyMember"]:
        """Return all ancestors up to max_depth generations."""
        ancestors: list[FamilyMember] = []
        to_visit = list(self.parents)
        depth = 0
        while to_visit and depth < max_depth:
            current = to_visit.pop(0)
            if current not in ancestors:
                ancestors.append(current)
                to_visit.extend(current.parents)
            depth += 1
        return ancestors

    def get_relationship_to(  # noqa: C901, PLR0911, PLR0912
        self, other: "FamilyMember"
    ) -> str | None:
        """
        Derive the relationship from self to another family member.

        Returns a relationship string like "parent", "child", "sibling",
        "grandparent", "aunt/uncle", "cousin", etc. or None if unrelated.
        """
        if self.pk == other.pk:
            return "self"

        # Direct parent
        if other in self.parents:
            return "parent"

        # Direct child
        if other in self.children:
            return "child"

        # Sibling
        if other in self.siblings:
            return "sibling"

        # Grandparent (parent's parent)
        for parent in self.parents:
            if other in parent.parents:
                return "grandparent"

        # Grandchild (child's child)
        for child in self.children:
            if other in child.children:
                return "grandchild"

        # Aunt/Uncle (parent's sibling)
        for parent in self.parents:
            if other in parent.siblings:
                return "aunt/uncle"

        # Niece/Nephew (sibling's child)
        for sibling in self.siblings:
            if other in sibling.children:
                return "niece/nephew"

        # Cousin (parent's sibling's child)
        for parent in self.parents:
            for aunt_uncle in parent.siblings:
                if other in aunt_uncle.children:
                    return "cousin"

        # Could extend for more distant relationships using common ancestor
        return None
