"""FactoryBoy factories for the assets app (#1872)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.assets.constants import AssetRoleContext
from world.assets.models import NPCAsset

_PERSONA_FACTORY = "world.scenes.factories.PersonaFactory"


class NPCAssetFactory(DjangoModelFactory):
    class Meta:
        model = NPCAsset

    promoter_persona = factory.SubFactory(_PERSONA_FACTORY)
    asset_persona = factory.SubFactory(_PERSONA_FACTORY)
    role_context = AssetRoleContext.INFORMANT
    source_functionary = factory.SubFactory("world.npc_services.factories.FunctionaryFactory")
