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


class Family(SharedMemoryModel):
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

    class Meta:
        verbose_name = "Family"
        verbose_name_plural = "Families"
        ordering = ["family_type", "name"]

    def __str__(self):
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
        ordering = ["family__name", "name"]

    def __str__(self):
        if self.character:
            return f"{self.character.key} ({self.family.name})"
        return f"{self.name or 'Unnamed'} ({self.family.name})"

    def get_display_name(self) -> str:
        """Get the display name for this family member."""
        if self.character:
            return self.character.key
        return self.name or "Unnamed"


class FamilyRelationship(models.Model):
    """
    Directed relationship between family members.

    Relationships are directed edges: A → PARENT → B means "A is parent of B".
    Inverse relationships should be created explicitly: B → CHILD → A.

    Examples:
    - Alice → PARENT → Bob (Alice is parent of Bob)
    - Bob → CHILD → Alice (Bob is child of Alice)
    - Bob → SIBLING → Carol (Bob is sibling of Carol)
    - Carol → SIBLING → Bob (Carol is sibling of Bob)
    """

    class RelationType(models.TextChoices):
        PARENT = "parent", "Parent"
        CHILD = "child", "Child"
        SIBLING = "sibling", "Sibling"
        SPOUSE = "spouse", "Spouse"
        AUNT_UNCLE = "aunt_uncle", "Aunt/Uncle"
        NIECE_NEPHEW = "niece_nephew", "Niece/Nephew"
        COUSIN = "cousin", "Cousin"
        GRANDPARENT = "grandparent", "Grandparent"
        GRANDCHILD = "grandchild", "Grandchild"

    from_member = models.ForeignKey(
        FamilyMember,
        on_delete=models.CASCADE,
        related_name="relationships_from",
        help_text="Source member of the relationship",
    )
    to_member = models.ForeignKey(
        FamilyMember,
        on_delete=models.CASCADE,
        related_name="relationships_to",
        help_text="Target member of the relationship",
    )
    relationship_type = models.CharField(
        max_length=20,
        choices=RelationType.choices,
        help_text="Type of relationship from source to target",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about this relationship",
    )

    class Meta:
        unique_together = [["from_member", "to_member", "relationship_type"]]
        verbose_name = "Family Relationship"
        verbose_name_plural = "Family Relationships"
        ordering = ["from_member__family__name", "from_member__name"]

    def __str__(self):
        from_name = self.from_member.get_display_name()
        to_name = self.to_member.get_display_name()
        return f"{from_name} → {self.get_relationship_type_display()} → {to_name}"
