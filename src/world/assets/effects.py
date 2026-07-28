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
    from world.assets.models import CluePool
    from world.clues.models import Clue
    from world.npc_services.models import NPCServiceOffer
    from world.roster.models import RosterEntry
    from world.scenes.models import Persona

_FUNCTIONARY_GONE_MESSAGE = "They're no longer here."


@transaction.atomic
def _promote_functionary(
    offer: NPCServiceOffer, persona: Persona, *, role_context: str
) -> EffectResult:
    """Shared implementation for the three role-context promotion handlers.

    Resolves the Functionary from the PC's current location + the offer's
    role (place_functionary guarantees at most one active Functionary per
    (role, room), so this lookup is deterministic). Rolls
    offer.check_type/check_difficulty directly (final-action offers don't
    auto-roll checks — "the effect IS the payoff").

    #2827 phase 3 — recruitment is **in-place by default**: success
    materializes the placement's identity (reusing an already-materialized
    persona — the sheet-spine, never a duplicate mint) and creates the
    NPCAsset relationship row. The NPC keeps working the venue; what you
    own is a claim on their loyalty. Pulling them out of the job is a
    separate, later choice (`extract_asset`) — "quit and come with me"
    versus "stay here, and listen".
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.npc_services.instantiation import materialize_functionary  # noqa: PLC0415
    from world.npc_services.models import Functionary  # noqa: PLC0415

    character = persona.character_sheet.character
    room_profile = get_room_profile(character.location)
    functionary = Functionary.objects.filter(role=offer.role, room=room_profile).first()
    if functionary is None:
        return EffectResult(kind=offer.kind, message=_FUNCTIONARY_GONE_MESSAGE)

    if NPCAsset.objects.filter(promoter_persona=persona, source_functionary=functionary).exists():
        return EffectResult(kind=offer.kind, message="You've already cultivated this one.")

    # .exists() rather than functionary.is_active: bulk .update() writers
    # bypass the identity map, so a cached instance's flag can be stale.
    # Inactive here means staff removal / extraction — the slot is empty.
    if not Functionary.objects.filter(pk=functionary.pk, is_active=True).exists():
        return EffectResult(kind=offer.kind, message=_FUNCTIONARY_GONE_MESSAGE)

    if offer.check_type_id is None:
        return EffectResult(
            kind=offer.kind,
            message="This offer has no capability check configured. (Authoring error.)",
        )

    # #2827 phase 4 — a materialized NPC's likes/dislikes ease or harden the
    # cultivation roll (0 for a still-faceless placement).
    from world.npc_services.personality import preference_modifier  # noqa: PLC0415

    check_result = perform_check_with_modifiers(
        character,
        offer.check_type,
        target_difficulty=offer.check_difficulty,
        extra_modifiers=preference_modifier(functionary.persona, offer.check_type),
    )
    if check_result.success_level <= 0:
        return EffectResult(kind=offer.kind, message="They're not ready to commit to you yet.")

    asset_persona = materialize_functionary(functionary)
    asset = NPCAsset.objects.create(
        promoter_persona=persona,
        asset_persona=asset_persona,
        role_context=role_context,
        source_functionary=functionary,
    )

    return EffectResult(
        kind=offer.kind,
        object_pk=asset.pk,
        object_label=asset_persona.name,
        message=f"{asset_persona.name} agrees to work for you.",
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


def _draw_clue_from_pool(pool: CluePool, roster_entry: RosterEntry) -> Clue | None:
    """Delegate to the shared draw (promoted to services for #2820 tasking)."""
    from world.assets.services import draw_clue_from_pool  # noqa: PLC0415

    return draw_clue_from_pool(pool, roster_entry)


@transaction.atomic
def run_asset_intel_task(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """ASSET_TASK_INTEL effect handler (#1905, #2293).

    Resolves the active NPCAsset owned by the interacting persona, rolls
    the offer's check, and on success draws a clue from the pool (excluding
    clues the promoter already holds) and grants a CharacterClue. The PC
    rolls the check (they're directing the task; the check models how well
    they've cultivated the asset's cooperation).

    Requires the offer to have an AssetTaskIntelDetails row pointing at the
    CluePool to draw from. Returns a failure EffectResult if the asset is
    not ACTIVE, the check fails, the details row is missing, or the pool
    is exhausted (all clues already held).
    """
    from world.assets.constants import AssetStatus  # noqa: PLC0415

    # Resolve the details row (the clue pool to draw from).
    from world.assets.models import (  # noqa: PLC0415
        AssetTaskIntelDetails,
        NPCAsset,
    )
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.clues.models import CharacterClue  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        details = offer.asset_task_intel_details
    except AssetTaskIntelDetails.DoesNotExist:
        return EffectResult(
            kind=offer.kind,
            message="This task has no intel target configured. (Authoring error.)",
        )

    # Resolve the promoter's active asset. The eligibility_rule predicate on
    # the offer gates which offers appear for which NPC, so any active asset
    # owned by this persona is valid for this task.
    asset = NPCAsset.objects.filter(
        promoter_persona=persona,
        status=AssetStatus.ACTIVE,
    ).first()
    if asset is None:
        return EffectResult(
            kind=offer.kind,
            message="This asset is not available for tasking.",
        )

    # Roll the check — the PC rolls (they're directing the task).
    character = persona.character_sheet.character
    if offer.check_type_id is not None:
        check_result = perform_check_with_modifiers(
            character, offer.check_type, target_difficulty=offer.check_difficulty
        )
        if check_result.success_level <= 0:
            return EffectResult(
                kind=offer.kind,
                message="Your asset has nothing useful to report this time.",
            )

    # Resolve the promoter's roster entry for the clue grant.
    roster_entry = RosterEntry.objects.filter(character_sheet=persona.character_sheet).first()
    if roster_entry is None:
        return EffectResult(
            kind=offer.kind,
            message="Your asset brings back word, but there's nowhere to record it.",
        )

    # Draw a clue from the pool, excluding clues the promoter already holds.
    drawn_clue = _draw_clue_from_pool(details.clue_pool, roster_entry)
    if drawn_clue is None:
        return EffectResult(
            kind=offer.kind,
            message="Your asset has nothing new to report. They've told you everything they know.",
        )

    CharacterClue.objects.get_or_create(
        roster_entry=roster_entry,
        clue=drawn_clue,
    )

    return EffectResult(
        kind=offer.kind,
        object_pk=drawn_clue.pk,
        object_label=drawn_clue.name,
        message=f"Your asset brings back word: {drawn_clue.name}.",
        payload={"clue_pk": drawn_clue.pk, "asset_pk": asset.pk},
    )


@transaction.atomic
def run_asset_collect_task(offer: NPCServiceOffer, persona: Persona) -> EffectResult:
    """ASSET_TASK_COLLECT effect handler (#2294).

    Resolves the active NPCAsset owned by the interacting persona, then
    collects its accumulated income via ``collect_asset_income``. The check
    outcome band decides how much of the pooled money arrives — catastrophe
    loses the entire pool. Money lands in the PC's CharacterPurse via
    ``transfer`` with a CurrencyTransfer audit row.

    Catches ``ValidationError`` from a zero-pool race (the eligibility gate
    checks ``uncollected_pool > 0`` at menu-display time, but a concurrent
    collection could zero it before dispatch) and returns a graceful
    failure EffectResult, mirroring the org ``run_collection`` handler.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415

    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.currency.services import collect_asset_income  # noqa: PLC0415

    asset = NPCAsset.objects.filter(
        promoter_persona=persona,
        status=AssetStatus.ACTIVE,
    ).first()
    if asset is None:
        return EffectResult(
            kind=offer.kind,
            message="This asset is not available for tasking.",
        )

    try:
        result = collect_asset_income(asset=asset, character_sheet=persona.character_sheet)
    except ValidationError:
        return EffectResult(
            kind=offer.kind,
            message="Your asset has nothing to collect right now.",
            payload={"asset_pk": asset.pk},
        )

    if result.catastrophe:
        message = (
            "Word comes back ugly: the collection was set upon and "
            f"the take is gone. {format_coppers(result.gathered)} lost."
        )
    elif result.stolen > 0:
        message = (
            f"Your asset returns light: {format_coppers(result.landed)} "
            f"banked of {format_coppers(result.gathered)} gathered; the rest went missing."
        )
    else:
        message = f"The collection went smoothly: {format_coppers(result.landed)} banked."
    return EffectResult(
        kind=offer.kind,
        message=message,
        payload={
            "asset_pk": asset.pk,
            "gathered": result.gathered,
            "landed": result.landed,
            "catastrophe": result.catastrophe,
        },
    )
