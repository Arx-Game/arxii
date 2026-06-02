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

    SANCTUM = "SANCTUM", "Sanctum"
    LIBRARY = "LIBRARY", "Library"
    TRAINING_ROOM = "TRAINING_ROOM", "Training Room"
    LAB = "LAB", "Lab"
    COMMAND_CENTER = "COMMAND_CENTER", "Command Center"
    GRANARY = "GRANARY", "Granary"
    CANNON_DECK = "CANNON_DECK", "Cannon Deck"


class RoomFeatureInstallMechanism(models.TextChoices):
    """How a feature kind's L1 install is triggered (Plan 4 §E, revised 2026-06-03).

    Magical features (Sanctum, future Wardstone, future Sigil-circle)
    install via a perform-time **ritual** — one actor, witchy, components
    consumed at performance. Physical features (Granary, Cannon Deck,
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
