"""Constants for the room_features system."""

from django.db import models


class RoomFeatureServiceStrategy(models.TextChoices):
    """Identifies which service-strategy function handles a feature kind.

    Each value names a per-kind handler that runs at install/upgrade
    Project resolution. The strategy registry lives in
    :mod:`world.room_features.services`; each feature's home app
    registers its handler at app-ready time (Sanctum: ``world.magic``).
    Unregistered values raise at dispatch time.
    """

    FIELD = "FIELD", "Field"
    SANCTUM = "SANCTUM", "Sanctum"
    LIBRARY = "LIBRARY", "Library"
    TRAINING_ROOM = "TRAINING_ROOM", "Training Room"
    LAB = "LAB", "Lab"
    COMMAND_CENTER = "COMMAND_CENTER", "Command Center"
    GRANARY = "GRANARY", "Granary"
    SIEGE_DECK = "SIEGE_DECK", "Siege Deck"
    CAPTAINS_QUARTERS = "CAPTAINS_QUARTERS", "Captain's Quarters"
    # Civic-hub reader surfaces (#1450): one per room (the instance is a
    # OneToOne), so a room carries a board OR a crier — flavor variants of the
    # same local-tidings reader.
    NOTICE_BOARD = "NOTICE_BOARD", "Notice Board"
    TOWN_CRIER = "TOWN_CRIER", "Town Crier"
    # Bank access (#2540 Layer 4): the room-side gate for org-vault deposit/withdraw
    # actions — a bank room on grid or an owner-installed bank-access decor feature.
    # Reachability-only (COMMAND_CENTER's shape): custody lives in world.items'
    # OrganizationVault, never in the room.
    BANK = "BANK", "Bank Access"
    # Owner-upgradeable social hub (#1694): the amplifier layer on top of
    # ``RoomProfile.is_social_hub`` (#1572). Installing it marks the room a hub;
    # its ``level`` scales crowd draw + the fame/prestige earned for actions here.
    SOCIAL_HUB = "SOCIAL_HUB", "Social Hub"
    STABLES = "STABLES", "Stables"
    VAULT = "VAULT", "Vault"
    BRIG = "BRIG", "Brig"
    WORKSHOP_OF_INIQUITY = "WORKSHOP_OF_INIQUITY", "Workshop of Iniquity"


class RoomFeatureInstallMechanism(models.TextChoices):
    """How a feature kind's L1 install is triggered (Plan 4 §E, revised 2026-06-03).

    Magical features (Sanctum, future Wardstone, future Sigil-circle)
    install via a perform-time **ritual** — one actor, witchy, components
    consumed at performance. Physical features (Granary, Siege Deck,
    Forge, Barracks) install via a **project** — collaborative, accumulated,
    multi-contributor.

    Upgrades (L1 → L2+) are ALWAYS Project-driven regardless of install
    mechanism; this field only selects the L1 install path.
    """

    RITUAL = "RITUAL", "Ritual (magical, immediate)"
    PROJECT = "PROJECT", "Project (physical, collaborative)"


class RoomFeatureOwnerType(models.TextChoices):
    """Coarse owner-type constraint values for ``RoomFeatureKind``.

    A feature kind's ``required_building_owner_types`` rows enumerate
    which building owner kinds are allowed to install it. ``PERSONA``
    means a player-owned building; ``ORGANIZATION_*`` values gate by
    organization kind so a "Heraldic Hall" can require a Noble House,
    a Sanctum can require Persona-or-Covenant, etc.
    """

    PERSONA = "PERSONA", "Persona-owned"
    ORGANIZATION_NOBLE = "ORG_NOBLE", "Organization — Noble House"
    ORGANIZATION_TRADE = "ORG_TRADE", "Organization — Trade Guild"
    ORGANIZATION_CRIMINAL = "ORG_CRIMINAL", "Organization — Criminal Gang"
    ORGANIZATION_COVENANT = "ORG_COVENANT", "Organization — Covenant"
    ORGANIZATION_DEVOTIONAL = "ORG_DEVOTIONAL", "Organization — Devotional Order"


#: Per-level AP discount a Training Room grants to technique learning (#675).
#: PLACEHOLDER — pending content pass.
TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL = 1

#: Social-hub amplifier magnitudes (#1694), all derived from the feature's
#: ``level`` (Apostate ratified level→multiplier constants over a per-room knob
#: model). PLACEHOLDER — pending the content/tuning pass; do not treat as final.
#: Max level for the seeded Social Hub kind.
SOCIAL_HUB_MAX_LEVEL = 5
#: Additive crowd-draw bonus a hub contributes per level (feeds room traffic).
SOCIAL_HUB_CROWD_DRAW_PER_LEVEL = 1
#: Extra fame granted for a renown-earning action in a hub room, as a percent
#: bonus per level (e.g. level 3 → +30% at 10%/level). Applied on top of the
#: base award.
SOCIAL_HUB_FAME_BONUS_PCT_PER_LEVEL = 10
#: Extra prestige granted for a renown-earning action in a hub room, percent
#: bonus per level. Mirrors the fame bonus.
SOCIAL_HUB_PRESTIGE_BONUS_PCT_PER_LEVEL = 10
#: ``LocationValueModifier.source`` tag for a hub's crowd-draw TRAFFIC bonus.
#: One hub per room (RoomFeatureInstance is OneToOne), so this is unique per room.
SOCIAL_HUB_TRAFFIC_SOURCE = "social_hub"

#: Per-level max-items capacity for a Vault room feature (#2179).
#: ``max_items = instance.level * VAULT_MAX_ITEMS_PER_LEVEL``.
VAULT_MAX_ITEMS_PER_LEVEL = 20

#: Per-level prisoner capacity for a Brig room feature (#1862).
#: ``max_prisoners = instance.level * BRIG_CAPACITY_PER_LEVEL``.
BRIG_CAPACITY_PER_LEVEL = 2

#: Escape-check difficulty added per Brig level (#1862). PLACEHOLDER — pending
#: the mission-difficulty-injection design pass; MVP uses capacity-only gating.
BRIG_ESCAPE_DIFFICULTY_PER_LEVEL = 2

#: Max level for the seeded Brig kind (#1862).
BRIG_MAX_LEVEL = 3


class DefenseKind(models.TextChoices):
    """Discriminator for DefenseProgressionDetails and its dispatch (#2177).

    Fixed, code-owned mechanics -- not a GM-authored open catalog like
    RoomFeatureKind, so no catalog table backs this; complete_defense_
    installation's plain three-way branch is the only dispatcher (Decision 2).
    """

    EXIT_BARS = "EXIT_BARS", "Exit Bars"
    ROOM_WARD = "ROOM_WARD", "Room Ward"
    ROOM_ALARM = "ROOM_ALARM", "Room Alarm"


#: Fixed level caps for defense kinds (#2177) -- not GM-authored max_level
#: columns, since there's no catalog row backing these fixed mechanics.
EXIT_BARS_MAX_LEVEL = 5
ROOM_WARD_MAX_LEVEL = 5
ROOM_ALARM_MAX_LEVEL = 5
