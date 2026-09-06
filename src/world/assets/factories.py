"""FactoryBoy factories for the assets app (#1872)."""

from __future__ import annotations

import factory
from factory.django import DjangoModelFactory

from world.assets.constants import AssetRoleContext
from world.assets.models import CluePool, CluePoolEntry, DistinctionAssetGrant, NPCAsset

_PERSONA_FACTORY = "world.scenes.factories.PersonaFactory"


class DistinctionAssetGrantFactory(DjangoModelFactory):
    """Staff-authored sidecar granting an NPCAsset from a Distinction (#1906, #3660)."""

    class Meta:
        model = DistinctionAssetGrant

    distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    npc_role = factory.SubFactory("world.npc_services.factories.NPCRoleFactory")
    role_context = AssetRoleContext.INFORMANT
    starting_affection = 0
    asset_display_name = factory.Sequence(lambda n: f"Asset Grant Figure {n}")


class NPCAssetFactory(DjangoModelFactory):
    class Meta:
        model = NPCAsset

    promoter_persona = factory.SubFactory(_PERSONA_FACTORY)
    asset_persona = factory.SubFactory(_PERSONA_FACTORY)
    role_context = AssetRoleContext.INFORMANT
    source_functionary = factory.SubFactory("world.npc_services.factories.FunctionaryFactory")
    weekly_income = 0
    uncollected_pool = 0


class CluePoolFactory(DjangoModelFactory):
    class Meta:
        model = CluePool

    name = factory.Sequence(lambda n: f"Clue Pool {n}")
    description = "A pool of clues for intel tasks."


class CluePoolEntryFactory(DjangoModelFactory):
    class Meta:
        model = CluePoolEntry

    pool = factory.SubFactory(CluePoolFactory)
    clue = factory.SubFactory("world.clues.factories.ClueFactory")
    weight = 1
