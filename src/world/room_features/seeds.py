"""Idempotent seed helpers for the room_features system.

Per repo discipline (#683): seeds live in code, called via
``get_or_create``. NOT a committed fixture.

Plan 4 seeds:
- ``ensure_sanctum_kind`` — the one ``RoomFeatureKind`` row Plan 4 ships,
  plus its allowed owner-type rows (Persona OR Covenant organization).
  Other kinds (Library, Training Room, Lab, …) land via #675 content
  authoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)
from world.room_features.models import RoomFeatureKind, RoomFeatureKindOwnerType

if TYPE_CHECKING:
    from world.npc_services.models import NPCRole

SANCTUM_KIND_NAME = "Sanctum"
SANCTUM_MAX_LEVEL = 5


def ensure_sanctum_kind() -> RoomFeatureKind:
    """Get-or-create the Sanctum ``RoomFeatureKind`` row + owner-type rules.

    Idempotent. Two ``RoomFeatureKindOwnerType`` rows are seeded —
    ``PERSONA`` and ``ORG_COVENANT`` — enforcing the spec's
    ``required_building_owner_types`` constraint for Sanctum.

    Sanctum installs via Ritual (Plan 4 §F revised 2026-06-03). The
    Personal + Covenant install ritual rows are linked from the magic
    side via ``world.magic.seeds_sanctum.ensure_sanctification_rituals``.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        defaults={
            "name": SANCTUM_KIND_NAME,
            "description": (
                "PLACEHOLDER — Sanctum kind: consecrated room (Personal home "
                "or Covenant sacred ground) that generates passive resonance "
                "income via the Ritual of Homecoming."
            ),
            "max_level": SANCTUM_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.RITUAL,
        },
    )
    # Idempotently sync install_mechanism in case the row pre-existed from an
    # older seed when the field defaulted to PROJECT.
    if kind.install_mechanism != RoomFeatureInstallMechanism.RITUAL:
        kind.install_mechanism = RoomFeatureInstallMechanism.RITUAL
        kind.save(update_fields=["install_mechanism"])
    for owner_type in (
        RoomFeatureOwnerType.PERSONA,
        RoomFeatureOwnerType.ORGANIZATION_COVENANT,
    ):
        RoomFeatureKindOwnerType.objects.get_or_create(
            feature_kind=kind,
            owner_type=owner_type,
        )
    return kind


def ensure_plan_4_seeds() -> None:
    """Convenience: seed everything Plan 4 needs at the framework layer.

    Safe to call multiple times (each component is idempotent). Sanctum-
    specific seeds (``Ritual`` rows for Homecoming + Purging) live in
    ``world.magic`` and are seeded by its own seed module.
    """
    ensure_sanctum_kind()
    ensure_library_kind()
    ensure_training_room_kind()
    ensure_siege_deck_kind()
    ensure_captains_quarters_kind()


COMMAND_CENTER_KIND_NAME = "Command Center"


def ensure_command_center_kind() -> RoomFeatureKind:
    """Get-or-create the Command Center ``RoomFeatureKind`` (#930).

    The estate's nerve center: where the family books are kept (#675's
    Command Center gets its content — the org-books management screen is
    reachable here IC). PLACEHOLDER prose for the content pass.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.COMMAND_CENTER,
        defaults={
            "name": COMMAND_CENTER_KIND_NAME,
            "max_level": 3,  # PLACEHOLDER ladder pending the content pass
            "description": (
                "PLACEHOLDER — Command Center kind: the estate's nerve center; "
                "the household's books and summons are managed from here."
            ),
        },
    )
    return kind


LAB_KIND_NAME = "Lab"
LAB_MAX_LEVEL = 5


def ensure_lab_kind() -> RoomFeatureKind:
    """Get-or-create the Lab ``RoomFeatureKind`` (#1234).

    The crafting-station kind: installs/upgrades via the plain
    ROOM_FEATURE_PROGRESSION project (install_mechanism defaults to PROJECT),
    mirroring Command Center. Per-kind state (durability) lives in
    ``world.items.crafting.models.LabStationDetails``, keyed OneToOne to the
    resulting RoomFeatureInstance.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.LAB,
        defaults={
            "name": LAB_KIND_NAME,
            "max_level": LAB_MAX_LEVEL,
            "description": (
                "A crafting workspace — required to attach facets/styles. Wears "
                "down with use; pay coppers to repair it. Fancier Labs hold more "
                "durability but cost more per point to restore."
            ),
        },
    )
    return kind


NOTICE_BOARD_KIND_NAME = "Notice Board"
TOWN_CRIER_KIND_NAME = "Town Crier"
TOWN_CRIER_ROLE_NAME = "Town Crier"


def ensure_notice_board_kind() -> RoomFeatureKind:
    """Get-or-create the Notice Board ``RoomFeatureKind`` (#1450).

    The pull half of the civic-hub reader: an examinable fixture carrying the
    local slice of tidings (``tidings local``); wanted posters (#1826) render
    here later. PLACEHOLDER prose for the content pass.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.NOTICE_BOARD,
        defaults={
            "name": NOTICE_BOARD_KIND_NAME,
            "max_level": 1,
            "description": (
                "PLACEHOLDER — Notice Board kind: postings of the deeds and "
                "scandals the local societies speak of."
            ),
        },
    )
    return kind


def ensure_town_crier_kind() -> RoomFeatureKind:
    """Get-or-create the Town Crier ``RoomFeatureKind`` + its NPCRole (#1450).

    The push half: installing it places a crier Functionary in the room (the
    install handler wires this); arrivals hear the freshest tidings called.
    PLACEHOLDER prose for the content pass.
    """
    ensure_town_crier_role()
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.TOWN_CRIER,
        defaults={
            "name": TOWN_CRIER_KIND_NAME,
            "max_level": 1,
            "description": (
                "PLACEHOLDER — Town Crier kind: a crier calls the news of the day to all who pass."
            ),
        },
    )
    return kind


def ensure_town_crier_role() -> NPCRole:
    """The crier's NPCRole (a class-1 Functionary anchor). PLACEHOLDER flavor."""
    from world.npc_services.models import NPCRole  # noqa: PLC0415

    role, _ = NPCRole.objects.get_or_create(
        name=TOWN_CRIER_ROLE_NAME,
        defaults={
            "description": "PLACEHOLDER: calls the news of the day in the square.",
            "default_description_template": (
                "PLACEHOLDER: A crier stands on a worn crate, voice carrying over the crowd."
            ),
            "default_rapport_starting_value": 0,
        },
    )
    return role


# ---------------------------------------------------------------------------
# #675 feature kinds — Library, Training Room, Siege Deck, Captain's Quarters.
# ---------------------------------------------------------------------------

LIBRARY_KIND_NAME = "Library"
LIBRARY_MAX_LEVEL = 10


def ensure_library_kind() -> RoomFeatureKind:
    """Get-or-create the Library ``RoomFeatureKind`` (#675).

    A study hall: discounts codex-learning AP cost for learners in the room
    (read-time via ``active_library_in`` at ``CodexTeachingOffer.accept``).
    No per-kind details model — the bonus is derived from ``instance.level``.
    No owner-type restriction (any building owner may install).
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.LIBRARY,
        defaults={
            "name": LIBRARY_KIND_NAME,
            "max_level": LIBRARY_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Library kind: a study hall where codex learning "
                "costs less AP. The discount scales with the Library's level."
            ),
        },
    )
    return kind


TRAINING_ROOM_KIND_NAME = "Training Room"
TRAINING_ROOM_MAX_LEVEL = 3


def ensure_training_room_kind() -> RoomFeatureKind:
    """Get-or-create the Training Room ``RoomFeatureKind`` (#675).

    A practice hall: discounts technique-learning AP cost for learners in
    the room (read-time via ``active_training_room_in`` at
    ``learn_technique``). No per-kind details model — the bonus is derived
    from ``instance.level``.
    """
    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.TRAINING_ROOM,
        defaults={
            "name": TRAINING_ROOM_KIND_NAME,
            "max_level": TRAINING_ROOM_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Training Room kind: a practice hall where "
                "technique learning costs less AP. The discount scales with "
                "the Training Room's level."
            ),
        },
    )
    return kind


SIEGE_DECK_KIND_NAME = "Siege Deck"
SIEGE_DECK_MAX_LEVEL = 5


def ensure_siege_deck_kind() -> RoomFeatureKind:
    """Get-or-create the Siege Deck ``RoomFeatureKind`` (#675).

    A weapon-platform deck on a maritime building: adds to the ship's
    effective armament in battle (read-time via ``active_siege_deck_in`` at
    the battle bridge). Pre-gunpowder framing — mounts ballistae, catapults,
    scorpions. Restricted to maritime building kinds (ships today; airship
    kinds added as a content edit when airships arrive).
    """
    from world.ships.seeds import ensure_ship_kind  # noqa: PLC0415

    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.SIEGE_DECK,
        defaults={
            "name": SIEGE_DECK_KIND_NAME,
            "max_level": SIEGE_DECK_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Siege Deck kind: a weapon-platform deck mounting "
                "ballistae, catapults, and scorpions. Adds to the ship's "
                "effective armament in naval battle."
            ),
        },
    )
    ship_kind = ensure_ship_kind()
    kind.allowed_building_kinds.add(ship_kind)
    return kind


CAPTAINS_QUARTERS_KIND_NAME = "Captain's Quarters"
CAPTAINS_QUARTERS_MAX_LEVEL = 1


def ensure_captains_quarters_kind() -> RoomFeatureKind:
    """Get-or-create the Captain's Quarters ``RoomFeatureKind`` (#675).

    A maritime-gated reachability feature (like Command Center): its
    'content' is that certain surfaces are reachable where a Captain's
    Quarters stands. No numeric bonus. Restricted to maritime building kinds.
    """
    from world.ships.seeds import ensure_ship_kind  # noqa: PLC0415

    kind, _ = RoomFeatureKind.objects.get_or_create(
        service_strategy=RoomFeatureServiceStrategy.CAPTAINS_QUARTERS,
        defaults={
            "name": CAPTAINS_QUARTERS_KIND_NAME,
            "max_level": CAPTAINS_QUARTERS_MAX_LEVEL,
            "install_mechanism": RoomFeatureInstallMechanism.PROJECT,
            "description": (
                "PLACEHOLDER — Captain's Quarters kind: the IC center of "
                "command on a ship. Reachability-only; no numeric bonus."
            ),
        },
    )
    ship_kind = ensure_ship_kind()
    kind.allowed_building_kinds.add(ship_kind)
    return kind
