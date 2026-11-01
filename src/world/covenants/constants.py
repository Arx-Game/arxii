"""Constants for the covenants system."""

from django.db import models

# Name of the OrganizationType row used for Covenant-backed Organizations.
# `Covenant.save()` uses `get_or_create` keyed on this name to bootstrap the
# row on first use, so no fixture loading is required.
COVENANT_ORG_TYPE_NAME = "covenant"


class CovenantType(models.TextChoices):
    """The type of magically-empowered oath."""

    DURANCE = "durance", "Covenant of the Durance"
    BATTLE = "battle", "Covenant of Battle"
    COURT = "court", "Covenant of the Court"


class MembershipStanding(models.TextChoices):
    """Durable membership tier (#2992).

    CORE is the sworn, full member — today's behavior. MINOR is a guest
    standing: the member rides the secondary-vow lane (#2641) only, at
    SecondaryVowConfig potency, and never occupies the primary engagement
    slot. DURANCE-only for now (CharacterCovenantRole.clean()).
    """

    CORE = "core", "Core Member"
    MINOR = "minor", "Minor Member"


class RoleArchetype(models.TextChoices):
    """Foundational combat archetype for covenant roles.

    At early levels players pick from these three. Specialized sub-roles
    unlock later within each archetype.
    """

    SWORD = "sword", "Sword"  # Offense
    SHIELD = "shield", "Shield"  # Defense
    CROWN = "crown", "Crown"  # Support


class CommandTier(models.TextChoices):
    """Battle-command hierarchy tier for a CovenantRole (#1710).

    Meaningful only for CovenantType.BATTLE roles — see CovenantRole.clean().
    """

    NONE = "none", "No command tier"
    SUBORDINATE = "subordinate", "Subordinate Commander"
    SUPREME = "supreme", "Supreme Commander"


class BattleBinding(models.TextChoices):
    """How a Battle covenant is bound to its cause (Slice E).

    STANDING covenants (a military unit or a state's banner-call) can rise
    again after standing down. CAMPAIGN covenants are bound to a single
    event and dissolve when it concludes.
    """

    STANDING = "standing", "Standing (unit or banner — can rise again)"
    CAMPAIGN = "campaign", "Campaign (one-time event — dissolves when done)"


# Default rank names created during covenant formation.
DEFAULT_FOUNDER_RANK_NAME = "Founder"
DEFAULT_MEMBER_RANK_NAME = "Member"


class MentorBondAdjusted(models.TextChoices):
    """Which party of a Mentor's Vow the bond reshapes."""

    MENTOR = "mentor", "Mentor"
    SIDEKICK = "sidekick", "Sidekick"


MENTOR_BOND_BAND_WIDTH = 2
MENTOR_BOND_ADJACENCY_OFFSET = 1
MENTOR_BOND_MAX_SIDEKICKS: int | None = None

# Secondary covenant vow potency dial (#2641) — ratified batch-2 F-2 seed:
# a secondary vow's Layer 2/4 contributions scale by potency_tenths / 10.
SECONDARY_VOW_POTENCY_TENTHS_DEFAULT = 6


# Vow focus picks (#4759). A pick's value is a placeholder point score until the
# simulator sets it; each pick level's budget defaults to one full-value pick.
VOW_FOCUS_PICK_VALUE_DEFAULT = 4
VOW_FOCUS_PICK_BUDGET_PER_LEVEL_DEFAULT = 4
VOW_FOCUS_PICK_MAX_LEVEL = 3
#: A limit met every time (10 tenths) leaves the price whole.
FOCUS_PICK_LIMIT_FREQUENCY_FULL = 10


class FocusPickLimitKind(models.TextChoices):
    """What kind of limit narrows a vow focus pick, and so lowers its price (#4759).

    SELF, TARGET, SETTING and TIMING limits are usage conditions: the price is
    multiplied by how often each is met (``frequency_tenths / 10``). EXPOSURE and
    COST limits cost something on every use, so each takes a flat ``reduction``
    off the price instead. COST is a component or a condition on yourself; it is
    not named PRICE so it does not collide with the magic ``RestrictionKind.PRICE``.
    """

    SELF = "self", "Self"
    TARGET = "target", "Target"
    SETTING = "setting", "Setting"
    TIMING = "timing", "Timing"
    EXPOSURE = "exposure", "Exposure"
    COST = "cost", "Cost"


#: Limit kinds whose ``frequency_tenths`` multiplies a pick's price (#4759).
FOCUS_PICK_FREQUENCY_LIMIT_KINDS: frozenset[str] = frozenset(
    {
        FocusPickLimitKind.SELF,
        FocusPickLimitKind.TARGET,
        FocusPickLimitKind.SETTING,
        FocusPickLimitKind.TIMING,
    }
)
#: Limit kinds whose flat ``reduction`` comes off a pick's price (#4759).
FOCUS_PICK_REDUCTION_LIMIT_KINDS: frozenset[str] = frozenset(
    {FocusPickLimitKind.EXPOSURE, FocusPickLimitKind.COST}
)


class VowEffectContext(models.TextChoices):
    """Where a cast must happen for a ``VowAddedEffect`` to fire (#4581).

    ANY fires in and out of combat. IN_COMBAT fires only on a cast resolved
    inside a combat round. OUT_OF_COMBAT fires only on a cast resolved outside
    one.
    """

    ANY = "any", "Any"
    IN_COMBAT = "in_combat", "In Combat"
    OUT_OF_COMBAT = "out_of_combat", "Out of Combat"


class VowEffectFrequency(models.TextChoices):
    """How often one holder's ``VowAddedEffect`` may fire (#4581).

    EVERY_CAST fires on each qualifying cast. ONCE_PER_ROUND and ONCE_PER_FIGHT
    are spent per combat participant through the ``VowAddedEffectFiring``
    ledger, so they are meaningful only on an IN_COMBAT row.
    """

    EVERY_CAST = "every_cast", "Every Cast"
    ONCE_PER_ROUND = "once_per_round", "Once per Round"
    ONCE_PER_FIGHT = "once_per_fight", "Once per Fight"


class InsightTargetKind(models.TextChoices):
    """Who an ``InsightTableEntry``'s condition lands on (#2645).

    SELF -> the Know caster. ALLY -> the cast's declared ally target, falling
    back to the caster when the cast declared none. TEAM -> every ACTIVE
    PC-side ``CombatParticipant`` in the encounter.
    """

    SELF = "self", "Self"
    ALLY = "ally", "Ally"
    TEAM = "team", "Team"


class DefenseStyle(models.TextChoices):
    """How a covenant vow defends (#2533, Layer 3).

    Code-defined per the shared-vocabulary ruling — #2536's situational perks
    key on these labels (each style MUST have distinct shine-situations there;
    a style with none is an authoring bug, per the 2026-07-20 niche ruling).
    """

    # Labelled "Mitigation" since #4759; the stored value stays gear_soak.
    GEAR_SOAK = "gear_soak", "Mitigation"  # armor is the defense
    EVASION = "evasion", "Evasion"  # not being there is the defense
    BARRIER = "barrier", "Barrier"  # force/warding is the defense


class StyleLapse(models.TextChoices):
    """Why a combat style's skill stopped counting on a roll (#4884).

    An attack roll lapses on the weapon or a held vow; a defense roll on worn armor or a
    held vow. The hit stat and the defense type still apply while lapsed.
    """

    WEAPON = "weapon", "Weapon"
    ARMOR = "armor", "Armor"
    VOW = "vow", "Vow"


#: How a lapsed roll names a gear kind the style does not list, with its verb (#4884):
#: "two-handed weapons are not this style's". Keyed by ``GearArchetype`` value.
STYLE_LAPSE_GEAR_WORDS: dict[str, str] = {
    "light_armor": "light armor is",
    "medium_armor": "medium armor is",
    "heavy_armor": "heavy armor is",
    "robe": "robes are",
    "melee_one_hand": "one-handed weapons are",
    "melee_two_hand": "two-handed weapons are",
    "ranged": "ranged weapons are",
    "thrown": "thrown weapons are",
    "shield": "shields are",
    "lance": "lances are",
    "unarmed": "unarmed strikes are",
    "other": "other weapons are",
}


class SphinxTier(models.TextChoices):
    """The Sphinx of Black Quartz's three-tier vow-suitability verdict (#2640).

    Never pass/fail — the Sphinx informs, it never gates (soft gate ratified;
    a character may swear a vow it warned about). Computed by
    ``world.covenants.sphinx.judge_vow`` from the kit∩role-demand join:

    - ``TAKES`` — every authored demand is covered by the kit (or the role has
      no authored demands at all — an unauthored vow cannot reject).
    - ``DORMANT`` — at least one demand is covered, at least one is not: "the
      vow would lie dormant in places."
    - ``NOT_YET`` — zero demands covered: "the vow will not take — yet,"
      paired with a shopping list of learnable techniques that would change
      the answer.
    """

    TAKES = "takes", "The vow will take"
    DORMANT = "dormant", "The vow would lie dormant in places"
    NOT_YET = "not_yet", "The vow will not take — yet"
