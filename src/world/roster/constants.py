"""Constants for the roster app."""

from django.db import models


class RelationshipType(models.TextChoices):
    """Relationship types returned by FamilyMember.get_relationship_to()."""

    SELF = "self", "Self"
    PARENT = "parent", "Parent"
    CHILD = "child", "Child"
    SIBLING = "sibling", "Sibling"
    GRANDPARENT = "grandparent", "Grandparent"
    GRANDCHILD = "grandchild", "Grandchild"
    AUNT_UNCLE = "aunt/uncle", "Aunt/Uncle"
    NIECE_NEPHEW = "niece/nephew", "Niece/Nephew"
    COUSIN = "cousin", "Cousin"
