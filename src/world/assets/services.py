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

if TYPE_CHECKING:
    from world.distinctions.models import CharacterDistinction


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
