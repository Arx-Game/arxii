"""Constants and TextChoices for the items app."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.mechanics.models import ModifierTarget


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
    INHERITED = "inherited", "Inherited"  # estate settlement moved it to an heir (#1985)
    ACTIVATED = "activated", "Activated"  # consumable used (e.g. permit redeemed)
    CONSUMED = "consumed", "Consumed"  # item destroyed by use (e.g. permit absorbed into project)
    RECOVERED = "recovered", "Recovered"  # reclamation returned it to the wronged (#2368)


# Ownership events that represent the item changing hands — the lore-relevant
# provenance the soft-delete cleanup must never destroy (#1025). Deliberately
# excludes CREATED (origin) and ACTIVATED/CONSUMED (every consumed item has
# these, so counting them would make the purge a no-op).
PROVENANCE_EVENT_TYPES = frozenset(
    {
        OwnershipEventType.GIVEN,
        OwnershipEventType.STOLEN,
        OwnershipEventType.TRANSFERRED,
        OwnershipEventType.INHERITED,
        OwnershipEventType.RECOVERED,
    }
)


class ContainerAccessPolicy(models.TextChoices):
    """Who may take items out of a container (#1909). Steal bypasses with consequences."""

    OPEN = "open", "Open"
    FRIENDS = "friends", "Friends"
    OWNER_ONLY = "owner_only", "Owner Only"


class StyleAudacity(models.IntegerChoices):
    """How daring a ``Style`` vocabulary word reads (#2029).

    Ordinal tier — not a display-only label. ``AudacityTuning.multiplier_for``
    (``world/items/services/styles.py``) reads the ordinal to look up a
    staff-tunable reward multiplier consumed by both the passive motif-coherence
    bonus (``_compute_motif_coherence_bonus``) and peer style-presentation
    endorsements (``create_style_presentation_endorsement``) — daring styles are
    mechanically, not just narratively, rewarded.
    """

    UNDERSTATED = 1, "Understated"
    EXPRESSIVE = 2, "Expressive"
    BOLD = 3, "Bold"
    OUTRAGEOUS = 4, "Outrageous"


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
    LANCE = "lance", "Lance"
    JEWELRY = "jewelry", "Jewelry"
    CLOTHING = "clothing", "Clothing"
    OTHER = "other", "Other"


# Archetype groupings for combat-stat gating (issue #508). SHIELD appears in
# both: a shield can soak and (rarely) bash. LANCE (#1843) is a mounted-combat
# weapon archetype — off-mount attacks take LANCE_UNMOUNTED_PENALTY.
WEAPON_ARCHETYPES = frozenset(
    {
        GearArchetype.MELEE_ONE_HAND,
        GearArchetype.MELEE_TWO_HAND,
        GearArchetype.RANGED,
        GearArchetype.THROWN,
        GearArchetype.SHIELD,
        GearArchetype.LANCE,
    }
)
ARMOR_ARCHETYPES = frozenset(
    {
        GearArchetype.LIGHT_ARMOR,
        GearArchetype.MEDIUM_ARMOR,
        GearArchetype.HEAVY_ARMOR,
        GearArchetype.ROBE,
        GearArchetype.SHIELD,
    }
)


# Base points contributed per worn in-vogue facet match, before quality and
# the FashionStyleBonus.weight multiplier are applied (Outfits Phase B, #513).
FASHION_MATCH_BASE = 1


# Fashion presentation (#514). The CheckType and ModifierTarget are authored
# rows fetched by name (no slug fields, no data migration); tests author them
# via factories. The endorsement weight is deliberately large so peer judging
# dominates the graded check floor.
# Combat stat ModifierTarget names (#985). Used by item_mundane_stat_for_target
# to identify which stat an equipped item contributes to.
WEAPON_DAMAGE_TARGET_NAME = "weapon_damage"
ARMOR_SOAK_TARGET_NAME = "armor_soak"

FASHION_PRESENTATION_CHECK_TYPE_NAME = "Fashion Presentation"
FASHION_PRESENTATION_MODIFIER_TARGET_NAME = "Fashion Presentation"
FASHION_PRESENTATION_ENDORSEMENT_WEIGHT = 5  # peer endorsements dominate acclaim
FASHION_PRESENTATION_BASE_DIFFICULTY = 10


# Vogue momentum (#514)
FASHION_VOGUE_MOMENTUM_STEP = 1  # momentum added to each worn facet per peer judgment
FASHION_VOGUE_DECAY_FLAT = 1  # flat momentum lost per decay tick
FASHION_VOGUE_DECAY_RATE = 0.05  # proportional momentum lost per decay tick (floored at 0)


# Seasonal trendsetter ceremony (#514)
FASHION_TREND_FACET_COUNT = 3  # how many top facets define the new vogue
FASHION_LIVING_STYLE_NAME_TEMPLATE = "{society} — Current Vogue"
FASHION_SEASON_INTERVAL = timedelta(days=30)  # seasonal ceremony cadence (real time)
FASHION_VOGUE_DECAY_INTERVAL = timedelta(hours=8)  # momentum decay cadence (matches renown decay)


def get_fashion_modifier_target() -> ModifierTarget:
    """Return the authored ``ModifierTarget`` for fashion presentation.

    Fetched by name from the mechanics registry. Raises
    ``ModifierTarget.DoesNotExist`` if the row has not been authored — that is
    a loud configuration error, not a silent fallback.
    """
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    return ModifierTarget.objects.get(name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME)


# --- Theft reclamation (#2368) — PLACEHOLDER magnitudes ---
TRACE_CHECK_TYPE_NAME = "Provenance Tracing"
TRACE_BOTCH_LEVEL = -2
TRACE_CHILL_HOURS = 24
RECEIVING_STOLEN_CRIME_SLUG = "receiving-stolen-goods"
RECEIVING_STOLEN_CRIME_SCALE = 2


class ClaimOrigin(models.TextChoices):
    VICTIM_REPORT = "victim_report", "Victim Report"
    ESTATE_SETTLEMENT = "estate_settlement", "Estate Settlement"


class ClaimStatus(models.TextChoices):
    OPEN = "open", "Open"
    RECOVERED_LAWFUL = "recovered_lawful", "Recovered (Lawful)"
    RECOVERED_TAKEN = "recovered_taken", "Recovered (Taken Back)"
    RELEASED = "released", "Released"


class OrgVaultEventKind(models.TextChoices):
    """Org-vault audit event kinds (#2540 Layer 4)."""

    DEPOSIT = "deposit", "Deposit"
    WITHDRAW = "withdraw", "Withdraw"
