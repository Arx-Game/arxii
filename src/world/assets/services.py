"""Asset grant services.

``reconcile_distinction_asset_grants`` is the character-creation consumer
for ``DistinctionAssetGrant`` sidecar rows (#1906). Mirrors
``reconcile_distinction_resonance_grants`` (the resonance-currency sibling in
``world.magic.services.distinction_resonance``): called at CG finalization
for each ``CharacterDistinction``, it reads authored grant rows and creates
the corresponding ``NPCAsset`` + ``NPCStanding`` — no cultivation check, no
room placement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.assets.constants import AssetStatus, AssetTransitionReason

if TYPE_CHECKING:
    from world.assets.models import NPCAsset
    from world.distinctions.models import CharacterDistinction
    from world.scenes.models import Persona


@transaction.atomic
def reconcile_distinction_asset_grants(character_distinction: CharacterDistinction) -> None:
    """Reconcile a ``CharacterDistinction`` into starting NPCAssets.

    Intended to be called at grant time whenever a character gains a distinction
    at character creation (wired into ``_create_distinction_modifiers_bulk`` in
    ``world.character_creation.services``). For every ``DistinctionAssetGrant``
    authored on ``character_distinction.distinction``: create an ``NPCAsset``
    (with ``acquisition_source=DISTINCTION_GRANT``, ``source_functionary=None``)
    and seed an ``NPCStanding`` row with the authored starting affection.

    Idempotency is keyed on ``(promoter_persona, source_distinction_grant)``: a
    ``NPCAsset`` already exists for this promoter + grant → skip. Backed by the
    partial unique constraint ``unique_npcasset_promoter_distinction_grant`` at
    the DB level.

    Args:
        character_distinction: The CharacterDistinction being reconciled.
    """
    from world.assets.constants import AssetAcquisitionSource  # noqa: PLC0415
    from world.assets.models import DistinctionAssetGrant, NPCAsset  # noqa: PLC0415
    from world.character_sheets.services import create_character_with_sheet  # noqa: PLC0415
    from world.npc_services.models import NPCStanding  # noqa: PLC0415

    promoter_persona = character_distinction.character.sheet_data.primary_persona

    grants = DistinctionAssetGrant.objects.filter(distinction=character_distinction.distinction)
    for grant in grants:
        # Idempotency: skip if this promoter already has an asset from this grant.
        # Keyed on source_distinction_grant FK (not asset_persona → NPCRole,
        # since Persona has no FK to NPCRole). The partial unique constraint
        # unique_npcasset_promoter_distinction_grant backs this at the DB level.
        if NPCAsset.objects.filter(
            promoter_persona=promoter_persona,
            source_distinction_grant=grant,
        ).exists():
            continue

        _character, _sheet, asset_persona = create_character_with_sheet(
            character_key=grant.asset_display_name,
            primary_persona_name=grant.asset_display_name,
        )
        # NOTE: Evennia allows duplicate ObjectDB keys. Two PCs taking the
        # same Distinction will each spawn an NPC with the same character_key.
        # This is consistent with the runtime path (functionary.display_name
        # is not unique per promoter) and acceptable — lookups go through the
        # NPCAsset FK / persona, not by key. Persona display names remain as
        # authored for player-facing consistency.
        NPCAsset.objects.create(
            promoter_persona=promoter_persona,
            asset_persona=asset_persona,
            role_context=grant.role_context,
            source_functionary=None,
            acquisition_source=AssetAcquisitionSource.DISTINCTION_GRANT,
            source_distinction_grant=grant,
        )
        # Seed standing with the authored starting affection. Runtime-promoted
        # assets rely on default affection=0 (NPCStanding created on first
        # interaction); CG grants explicitly seed the authored value.
        NPCStanding.objects.update_or_create(
            persona=promoter_persona,
            npc_persona=asset_persona,
            defaults={"affection": grant.starting_affection},
        )


class CoercionError(Exception):
    """A leverage-coercion could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@transaction.atomic
def coerce_into_asset(
    *,
    coercer_persona: Persona,
    target_persona: Persona,
    role_context: str,
) -> NPCAsset:
    """Extract a blackmailed NPC as a COERCION ``NPCAsset`` (#1680).

    The blackmailer holds standing leverage over the target (a ``Secret`` about their
    sheet, minted by a successful Blackmail); calling it in makes the target the
    coercer's coerced asset of the chosen ``role_context`` (informant / contact /
    personal-favor — the "list of options"). No functionary, no rapport, no capability
    check — leverage is the guarantee. (An actively-piloted NPC's player-style resist is
    handled by the caller before it reaches here; this service is the auto-success mint.)
    Reuses the whole ``NPCAsset`` machinery with ``acquisition_source=COERCION`` and both
    source FKs null (like a CG grant, this is not a functionary promotion).

    Raises ``CoercionError`` if the coercer holds no leverage over the target, or the
    target is already under coercion (one COERCION NPCAsset per NPC — voluntary
    co-ownership via #2295 does not block coercion).
    """
    from world.assets.constants import AssetAcquisitionSource  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415
    from world.secrets.services import has_leverage  # noqa: PLC0415

    if not has_leverage(
        holder_sheet=coercer_persona.character_sheet,
        subject_sheet=target_persona.character_sheet,
    ):
        msg = "You hold no leverage over them."
        raise CoercionError(msg, user_message=msg)
    if NPCAsset.objects.filter(
        asset_persona=target_persona,
        acquisition_source=AssetAcquisitionSource.COERCION,
    ).exists():
        msg = "They already answer to someone under coercion."
        raise CoercionError(msg, user_message=msg)
    return NPCAsset.objects.create(
        promoter_persona=coercer_persona,
        asset_persona=target_persona,
        role_context=role_context,
        acquisition_source=AssetAcquisitionSource.COERCION,
    )


# ---------------------------------------------------------------------------
# Asset compromise/loss lifecycle (#1905)
# ---------------------------------------------------------------------------

# Legal transitions: (from_status, to_status).
# Only COMPROMISED is recoverable (back to ACTIVE); LOST and DISMISSED are terminal.
_LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (AssetStatus.ACTIVE, AssetStatus.ACTIVE),  # no-op
        (AssetStatus.ACTIVE, AssetStatus.COMPROMISED),
        (AssetStatus.ACTIVE, AssetStatus.LOST),
        (AssetStatus.ACTIVE, AssetStatus.DISMISSED),
        (AssetStatus.COMPROMISED, AssetStatus.COMPROMISED),  # no-op
        (AssetStatus.COMPROMISED, AssetStatus.ACTIVE),  # recovery
        (AssetStatus.COMPROMISED, AssetStatus.LOST),
        (AssetStatus.LOST, AssetStatus.LOST),  # no-op (terminal)
        (AssetStatus.DISMISSED, AssetStatus.DISMISSED),  # no-op (terminal)
    }
)

# Maps a target status to the EventName emitted on transition.
_EVENT_FOR_STATUS: dict[str, str] = {
    AssetStatus.COMPROMISED: "ASSET_COMPROMISED",
    AssetStatus.LOST: "ASSET_LOST",
    AssetStatus.DISMISSED: "ASSET_DISMISSED",
}


class IllegalAssetTransitionError(ValueError):
    """Raised when an asset status transition is not in the legal matrix."""


@transaction.atomic
def transition_asset_status(
    asset: NPCAsset,
    new_status: str,
    *,
    reason: str = AssetTransitionReason.CONSEQUENCE,
) -> None:
    """Transition an NPCAsset's status, enforcing the legal-transition matrix.

    Asset status transitions are never GM fiat — they flow exclusively through
    the consequence pool system (the ``ASSET_STATUS`` EffectType on
    ConsequenceEffect). This function is the single mutator of
    ``NPCAsset.status`` beyond the initial ACTIVE default.

    Only COMPROMISED is recoverable (back to ACTIVE); LOST and DISMISSED are
    terminal. A no-op transition (same status → same status) is allowed.

    After the status changes, the corresponding flow event
    (``ASSET_COMPROMISED`` / ``ASSET_LOST`` / ``ASSET_DISMISSED``) is emitted
    via ``emit_event()`` so designers can author reactive triggers.

    Args:
        asset: The NPCAsset to transition.
        new_status: The target AssetStatus value.
        reason: Structured reason (AssetTransitionReason) for trigger filtering.

    Raises:
        IllegalAssetTransitionError: If the (current, new) pair is not in
            the legal matrix (e.g., LOST → ACTIVE).
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415

    old_status = asset.status
    if (old_status, new_status) not in _LEGAL_TRANSITIONS:
        msg = (
            f"Illegal asset transition: {old_status!r} → {new_status!r} "
            f"(asset pk={asset.pk}). LOST and DISMISSED are terminal."
        )
        raise IllegalAssetTransitionError(msg)

    if old_status == new_status:
        return  # no-op — don't save or emit

    asset.status = new_status
    asset.save(update_fields=["status"])

    # Emit the corresponding flow event for reactive triggers.
    event_name_attr = _EVENT_FOR_STATUS.get(new_status)
    if event_name_attr is not None:
        from flows.events.payloads import AssetStatusPayload  # noqa: PLC0415

        event_name = getattr(EventName, event_name_attr)
        asset_character = asset.asset_persona.character_sheet.character
        payload = AssetStatusPayload(
            asset_pk=asset.pk,
            promoter_persona_pk=asset.promoter_persona_id,
            asset_persona_pk=asset.asset_persona_id,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
        )
        emit_event(
            event_name,
            payload,
            asset_character.location,
        )


def transition_assets_for_dead_character(dead_character) -> None:
    """Transition all ACTIVE assets belonging to a dead character to LOST.

    Called reactively when a ``CHARACTER_KILLED`` flow event fires on a
    character that is an asset's ``asset_persona``. The asset's underlying
    NPC died, so the asset is permanently lost.

    Args:
        dead_character: The ObjectDB of the character whose death triggered
            this call.
    """
    from world.assets.models import NPCAsset  # noqa: PLC0415

    active_assets = NPCAsset.objects.filter(
        asset_persona__character_sheet__character=dead_character,
        status=AssetStatus.ACTIVE,
    )
    for asset in active_assets:
        transition_asset_status(
            asset,
            AssetStatus.LOST,
            reason=AssetTransitionReason.CHARACTER_KILLED,
        )
