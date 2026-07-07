"""Constants for the roster app."""

from django.db import models


class RelationshipType(models.TextChoices):
    """Relationship labels returned by the kinship derivation walk (#2062).

    Derived, never stored — see ``world.roster.services.kinship``.
    """

    SELF = "self", "Self"
    PARENT = "parent", "Parent"
    CHILD = "child", "Child"
    SIBLING = "sibling", "Sibling"
    HALF_SIBLING = "half-sibling", "Half-Sibling"
    STEP_PARENT = "step-parent", "Step-Parent"
    STEP_CHILD = "step-child", "Step-Child"
    FOSTER_PARENT = "foster-parent", "Foster-Parent"
    FOSTER_CHILD = "foster-child", "Foster-Child"
    FOSTER_SIBLING = "foster-sibling", "Foster-Sibling"
    SPOUSE = "spouse", "Spouse"
    IN_LAW = "in-law", "In-Law"
    GRANDPARENT = "grandparent", "Grandparent"
    GRANDCHILD = "grandchild", "Grandchild"
    AUNT_UNCLE = "aunt/uncle", "Aunt/Uncle"
    NIECE_NEPHEW = "niece/nephew", "Niece/Nephew"
    COUSIN = "cousin", "Cousin"
    PAST_INCARNATION = "past-incarnation", "Past Incarnation"
    LATER_INCARNATION = "later-incarnation", "Later Incarnation"


class DefinitionTier(models.TextChoices):
    """How defined a Kinsperson is — aligned with the real NPC ladder (#2062).

    Promotion only ever moves up-tier; staff promote when a node becomes
    load-bearing. PC means bound to a CharacterSheet with a roster entry;
    SHEETED is a staff/GM-piloted sheet (never roster-appable).
    """

    NAME_ONLY = "name_only", "Name Only"
    FUNCTIONARY = "functionary", "Functionary"
    STANDING = "standing", "Standing NPC"
    SHEETED = "sheeted", "Sheeted NPC"
    PC = "pc", "Player Character"


class ParentageKind(models.TextChoices):
    """Typed parent-child link kinds (#2062).

    Step-parents are DERIVED (parent's union partner with no parentage edge
    to the child), never stored. ADOPTIVE changes lineage in law; FOSTER is
    a care relationship carrying no name/inheritance claim by default.
    ACKNOWLEDGED is legitimation of an existing blood tie (the Umbral
    matrilineal option rides this).
    """

    BIOLOGICAL = "biological", "Biological"
    TREE_OF_SOULS = "tree_of_souls", "Tree of Souls"
    VAMPIRIC_EMBRACE = "vampiric_embrace", "Vampiric Embrace"
    ADOPTIVE = "adoptive", "Adoptive"
    FOSTER = "foster", "Foster"
    ACKNOWLEDGED = "acknowledged", "Acknowledged"


class MembershipBasis(models.TextChoices):
    """How a Kinsperson came to belong to a Family (#2062)."""

    BORN = "born", "Born Into"
    MARRIED_IN = "married_in", "Married In"
    ADOPTED = "adopted", "Adopted"
    LEGITIMIZED = "legitimized", "Legitimized"
    GRANTED = "granted", "Granted"
    FOUNDING = "founding", "Founding Member"


class MembershipEndReason(models.TextChoices):
    """Why a family membership ended (#2062)."""

    DISOWNED = "disowned", "Disowned"
    MARRIED_OUT = "married_out", "Married Out"
    RENOUNCED = "renounced", "Renounced"
    ANNULLED = "annulled", "Annulled"
