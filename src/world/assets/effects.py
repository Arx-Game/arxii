"""Promotion effect handlers for the NPCAsset informant/contact mechanic (#1872).

Registered against OfferKind.INFORMANT/.CONTACT/.PERSONAL_FAVOR by
AssetsConfig.ready() (mirrors world.missions.apps.MissionsConfig.ready) —
not inline in world.npc_services.effects, since this is a first-class new
subsystem rather than a one-off tweak to an existing app's offer kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.assets.constants import AssetRoleContext
from world.npc_services.effects import EffectResult

if TYPE_CHECKING:
    from world.npc_services.models import NPCServiceOffer
    from world.scenes.models import Persona

_FUNCTIONARY_GONE_MESSAGE = "They're no longer here."


@transaction.atomic
def _promote_functionary(
    offer: NPCServiceOffer, persona: Persona, *, role_context: str
) -> EffectResult:
    """Shared implementation for the three role-context promotion handlers.

    Resolves the Functionary from the PC's current location + the offer's
    role (place_functionary guarantees at most one active Functionary per
    (role, room), so this lookup is deterministic — see
    world.npc_services.functionaries.place_functionary). The lookup is NOT
    filtered on is_active: a successful promotion deactivates its own source
    Functionary (see below), so a stale is_active=True filter would make a
    repeat attempt on the same functionary indistinguishable from one that
    was never here — the dedup guard needs to see the (now-inactive) row to
    tell those two cases apart. Rolls offer.check_type/check_difficulty
    directly (final-action offers don't auto-roll checks — "the effect IS
    the payoff", per NPCServiceOffer.check_type's own help_text). On
    success: spawns a Character+CharacterSheet+PRIMARY Persona via
    create_character_with_sheet, places it in the Functionary's room,
    creates the NPCAsset row, and deactivates the source Functionary.
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.character_sheets.services import create_character_with_sheet  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.npc_services.functionaries import remove_functionary  # noqa: PLC0415
    from world.npc_services.models import Functionary  # noqa: PLC0415

    character = persona.character_sheet.character
    room_profile = get_room_profile(character.location)
    functionary = Functionary.objects.filter(role=offer.role, room=room_profile).first()
    if functionary is None:
        return EffectResult(kind=offer.kind, message=_FUNCTIONARY_GONE_MESSAGE)

    if NPCAsset.objects.filter(promoter_persona=persona, source_functionary=functionary).exists():
        return EffectResult(kind=offer.kind, message="You've already cultivated this one.")

    # Re-check active status via a fresh .exists() predicate rather than
    # functionary.is_active: remove_functionary() bulk-updates via
    # .filter().update(), which bypasses the SharedMemoryModel identity map,
    # so an in-process-cached `functionary` instance's attribute can be
    # stale. .exists() never instantiates a model object, so it always
    # reflects the true DB row (see world/npc_services/tests/test_functionaries.py's
    # own use of .exists() for the same reason).
    if not Functionary.objects.filter(pk=functionary.pk, is_active=True).exists():
        # Inactive for some other reason (staff removal, role disabled, ...) —
        # not because this promoter already cultivated it (checked above).
        return EffectResult(kind=offer.kind, message=_FUNCTIONARY_GONE_MESSAGE)

    if offer.check_type_id is None:
        return EffectResult(
            kind=offer.kind,
            message="This offer has no capability check configured. (Authoring error.)",
        )

    check_result = perform_check(
        character, offer.check_type, target_difficulty=offer.check_difficulty
    )
    if check_result.success_level <= 0:
        return EffectResult(kind=offer.kind, message="They're not ready to commit to you yet.")

    name = functionary.display_name
    _character, _sheet, asset_persona = create_character_with_sheet(
        character_key=name,
        primary_persona_name=name,
        home=functionary.room.objectdb,
    )
    _character.location = functionary.room.objectdb
    _character.save()

    asset = NPCAsset.objects.create(
        promoter_persona=persona,
        asset_persona=asset_persona,
        role_context=role_context,
        source_functionary=functionary,
    )
    remove_functionary(role=functionary.role, room=functionary.room)

    return EffectResult(
        kind=offer.kind,
        object_pk=asset.pk,
        object_label=asset_persona.name,
        message=f"{name} agrees to work for you.",
        payload={"asset_pk": asset.pk, "asset_persona_pk": asset_persona.pk},
    )


def promote_as_informant(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.INFORMANT)


def promote_as_contact(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.CONTACT)


def promote_as_personal_favor(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.PERSONAL_FAVOR)


def promote_as_guard(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.GUARD)


def promote_as_fan(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.FAN)


def promote_as_minor_ally(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    return _promote_functionary(offer, persona, role_context=AssetRoleContext.MINOR_ALLY)
