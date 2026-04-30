"""Constants and TextChoices for the items app."""

from django.db import models


class BodyRegion(models.TextChoices):
    """Body regions where equipment can be worn."""

    HEAD = "head", "Head"
    FACE = "face", "Face"
    NECK = "neck", "Neck"
    SHOULDERS = "shoulders", "Shoulders"
    TORSO = "torso", "Torso"
    BACK = "back", "Back"
    WAIST = "waist", "Waist"
    LEFT_ARM = "left_arm", "Left Arm"
    RIGHT_ARM = "right_arm", "Right Arm"
    LEFT_HAND = "left_hand", "Left Hand"
    RIGHT_HAND = "right_hand", "Right Hand"
    LEFT_LEG = "left_leg", "Left Leg"
    RIGHT_LEG = "right_leg", "Right Leg"
    FEET = "feet", "Feet"
    LEFT_FINGER = "left_finger", "Left Finger"
    RIGHT_FINGER = "right_finger", "Right Finger"
    LEFT_EAR = "left_ear", "Left Ear"
    RIGHT_EAR = "right_ear", "Right Ear"


class EquipmentLayer(models.TextChoices):
    """Depth layers for equipment at a body region (low to high)."""

    SKIN = "skin", "Skin"
    UNDER = "under", "Under"
    BASE = "base", "Base"
    OVER = "over", "Over"
    OUTER = "outer", "Outer"
    ACCESSORY = "accessory", "Accessory"


class OwnershipEventType(models.TextChoices):
    """Types of ownership transitions tracked in the ledger."""

    CREATED = "created", "Created"
    GIVEN = "given", "Given"
    STOLEN = "stolen", "Stolen"
    TRANSFERRED = "transferred", "Transferred"


class GearArchetype(models.TextChoices):
    """Gear categorization for covenant role compatibility.

    Final list TBD via playtest; this is the starting set per Spec D §4.1.
    """

    LIGHT_ARMOR = "light_armor", "Light Armor"
    MEDIUM_ARMOR = "medium_armor", "Medium Armor"
    HEAVY_ARMOR = "heavy_armor", "Heavy Armor"
    ROBE = "robe", "Robe"
    MELEE_ONE_HAND = "melee_one_hand", "One-Handed Melee"
    MELEE_TWO_HAND = "melee_two_hand", "Two-Handed Melee"
    RANGED = "ranged", "Ranged"
    THROWN = "thrown", "Thrown"
    SHIELD = "shield", "Shield"
    JEWELRY = "jewelry", "Jewelry"
    CLOTHING = "clothing", "Clothing"
    OTHER = "other", "Other"
