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


class CovenantScaledAction(models.TextChoices):
    """What a ``CovenantRoleActionScaling`` row scales (#4739).

    The maneuver members are the Action keys of the combat maneuvers they scale and
    stay as stored. ``SURGES_GIVEN`` scales the intensity a rallier's Rally surges
    the rallied ally by. Cover, Charge and Succor rows are authored in production but
    no code reads them yet; they are listed so staff can still save those rows.
    """

    INTERPOSE = "combat_interpose", "Interpose (partial block)"
    RALLY = "combat_rally", "Rally (morale restored)"
    COVER = "combat_cover", "Cover"
    CHARGE = "combat_charge", "Charge"
    SUCCOR = "combat_succor", "Succor"
    SURGES_GIVEN = "surges_given", "Surges given by Rally"


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

    GEAR_SOAK = "gear_soak", "Gear Soak"  # armor is the defense
    EVASION = "evasion", "Evasion"  # not being there is the defense
    BARRIER = "barrier", "Barrier"  # force/warding is the defense


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
