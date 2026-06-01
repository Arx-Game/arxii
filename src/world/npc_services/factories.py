"""FactoryBoy factories for the unified NPC service framework."""

from datetime import timedelta

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    PermitOfferDetails,
)


class NPCStandingFactory(DjangoModelFactory):
    """Per-(PC persona, NPC persona) standing row.

    Defaults to an already-elapsed cooldown and zero affection so the row
    exists without acting as a gate. Tests exercising the cooldown or
    affection sides override ``available_at=`` / ``affection=`` explicitly.
    """

    class Meta:
        model = NPCStanding

    persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    npc_persona = factory.SubFactory("world.scenes.factories.PersonaFactory")
    available_at = factory.LazyFunction(lambda: timezone.now() - timedelta(seconds=1))
    affection = 0


class NPCRoleFactory(DjangoModelFactory):
    class Meta:
        model = NPCRole
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"npc-role-{n}")
    description = ""
    default_description_template = ""
    default_rapport_starting_value = 0
    faction_affiliation = None


class NPCServiceOfferFactory(DjangoModelFactory):
    class Meta:
        model = NPCServiceOffer

    role = factory.SubFactory(NPCRoleFactory)
    kind = OfferKind.PERMIT
    label = factory.Sequence(lambda n: f"offer-{n}")
    draw_mode = DrawMode.MENU
    eligibility_rule = factory.LazyFunction(dict)
    rapport_requirement = 0
    is_final = True
    rapport_delta_success = 0
    rapport_delta_failure = 0


class PermitOfferDetailsFactory(DjangoModelFactory):
    class Meta:
        model = PermitOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.PERMIT)
