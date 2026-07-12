"""Service layer for the VAULT RoomFeatureKind (#2179).

Vault access-list management, vault lookup, and the VAULT strategy
progression handler (registered in apps.py alongside the other generic
kinds).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.room_features.constants import (
    VAULT_MAX_ITEMS_PER_LEVEL,
    RoomFeatureServiceStrategy,
)
from world.room_features.services import _install_or_level_feature

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.checks.types import CheckOutcome
    from world.projects.models import Project
    from world.room_features.models import VaultAccessEntry, VaultDetails
    from world.scenes.models import Persona


def active_vault_in(room_profile: object) -> object | None:
    """The room's active Vault feature instance, or None."""
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    return (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.VAULT,
        )
        .select_related("feature_kind")
        .active()
        .first()
    )


def vault_for_room(room_profile: object) -> VaultDetails | None:
    """Resolve VaultDetails for the room's active vault, or None."""
    instance = active_vault_in(room_profile)
    if instance is None:
        return None
    from world.room_features.models import VaultDetails  # noqa: PLC0415

    return VaultDetails.objects.filter(feature_instance=instance).first()


def vault_for_location(location: DefaultObject) -> VaultDetails | None:
    """Resolve VaultDetails for an Evennia location, or None.

    Convenience for inventory code that has a location, not a RoomProfile.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    profile = RoomProfile.objects.filter(objectdb=location).first()
    if profile is None:
        return None
    return vault_for_room(profile)


def has_vault_access(persona: Persona, vault_details: VaultDetails) -> bool:
    """True when persona has vault access (founder, direct, or via org).

    Mirrors ``is_tenant``'s org-membership composition: an organization
    entry grants access to all current members (any rank).
    """
    if persona.pk == vault_details.founder_persona_id:
        return True
    from world.room_features.models import VaultAccessEntry  # noqa: PLC0415

    if VaultAccessEntry.objects.filter(
        vault_details=vault_details, holder_persona=persona
    ).exists():
        return True
    # Org entries: check if persona is a member of any org on the list.
    from world.locations.services import _persona_organization_ids  # noqa: PLC0415

    org_ids = _persona_organization_ids(persona)
    if org_ids:
        return VaultAccessEntry.objects.filter(
            vault_details=vault_details,
            holder_organization_id__in=org_ids,
        ).exists()
    return False


def add_vault_access(
    vault_details: VaultDetails,
    *,
    holder_persona: Persona | None = None,
    holder_organization: object | None = None,
    added_by: Persona,
) -> VaultAccessEntry:
    """Create a VaultAccessEntry. Exactly one of persona/org must be set."""
    from world.locations.constants import HolderType  # noqa: PLC0415
    from world.room_features.models import VaultAccessEntry  # noqa: PLC0415

    _msg_both = "Specify either holder_persona or holder_organization, not both."
    _msg_neither = "Specify either holder_persona or holder_organization."
    if holder_persona is not None and holder_organization is not None:
        raise ValueError(_msg_both)
    if holder_persona is None and holder_organization is None:
        raise ValueError(_msg_neither)
    if holder_persona is not None:
        return VaultAccessEntry.objects.create(
            vault_details=vault_details,
            holder_type=HolderType.PERSONA,
            holder_persona=holder_persona,
            added_by=added_by,
        )
    return VaultAccessEntry.objects.create(
        vault_details=vault_details,
        holder_type=HolderType.ORGANIZATION,
        holder_organization=holder_organization,
        added_by=added_by,
    )


def remove_vault_access(
    vault_details: VaultDetails,
    *,
    holder_persona: Persona | None = None,
    holder_organization: object | None = None,
) -> int:
    """Delete the matching VaultAccessEntry. Returns count deleted. No-op if not found."""
    from world.locations.constants import HolderType  # noqa: PLC0415
    from world.room_features.models import VaultAccessEntry  # noqa: PLC0415

    if holder_persona is not None:
        qs = VaultAccessEntry.objects.filter(
            vault_details=vault_details,
            holder_type=HolderType.PERSONA,
            holder_persona=holder_persona,
        )
    elif holder_organization is not None:
        qs = VaultAccessEntry.objects.filter(
            vault_details=vault_details,
            holder_type=HolderType.ORGANIZATION,
            holder_organization=holder_organization,
        )
    else:
        return 0
    return qs.delete()[0]


def list_vault_access(vault_details: VaultDetails) -> object:
    """Return all VaultAccessEntry rows ordered by added_at."""
    from world.room_features.models import VaultAccessEntry  # noqa: PLC0415

    return VaultAccessEntry.objects.filter(vault_details=vault_details).order_by("added_at")


def vault_capacity_remaining(vault_details: VaultDetails) -> int:
    """Max items minus current unheld item count in the vault's room."""
    from world.items.models import ItemInstance  # noqa: PLC0415

    room_profile = vault_details.feature_instance.room_profile
    location = room_profile.objectdb
    current = ItemInstance.objects.filter(
        game_object__location=location,
        holder_character_sheet__isnull=True,
    ).count()
    return vault_details.max_items - current


def handle_vault_progression(
    project: Project,
    target_level: int,
    outcome_tier: CheckOutcome | None = None,  # noqa: ARG001
) -> None:
    """VAULT strategy (#2179): install/level the feature + create VaultDetails.

    At L1: creates RoomFeatureInstance via ``_install_or_level_feature``,
    then creates VaultDetails with founder_persona=project.owner_persona
    and max_items=target_level * VAULT_MAX_ITEMS_PER_LEVEL.
    At L2+: bumps instance level and updates max_items.
    """
    from world.room_features.models import VaultDetails  # noqa: PLC0415

    details = _install_or_level_feature(project, target_level)
    instance = details.target_room_profile.feature_instance
    vault, created = VaultDetails.objects.get_or_create(
        feature_instance=instance,
        defaults={
            "founder_persona": project.owner_persona,
            "max_items": target_level * VAULT_MAX_ITEMS_PER_LEVEL,
        },
    )
    if not created:
        vault.max_items = instance.level * VAULT_MAX_ITEMS_PER_LEVEL
        vault.save(update_fields=["max_items"])
