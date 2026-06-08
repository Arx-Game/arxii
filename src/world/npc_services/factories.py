"""FactoryBoy factories for the unified NPC service framework."""

from datetime import timedelta

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.models import (
    MissionOfferDetails,
    NPCRole,
    NPCRoleCooldown,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    PermitOfferDetails,
)

# Factory-path string for the Persona sub-factory, referenced by multiple
# factories below. Centralized to avoid the duplicated-literal SonarCloud
# smell (python:S1192).
_PERSONA_FACTORY = "world.scenes.factories.PersonaFactory"


class NPCStandingFactory(DjangoModelFactory):
    """Per-(PC persona, NPC persona) affection row.

    Standing is just affection now — cooldown moved to ``OfferCooldown``.
    Tests exercising the affection side pass ``affection=`` explicitly.
    """

    class Meta:
        model = NPCStanding

    persona = factory.SubFactory(_PERSONA_FACTORY)
    npc_persona = factory.SubFactory(_PERSONA_FACTORY)
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
    cooldown = None
    check_type = None
    check_difficulty = 0


class OfferCooldownFactory(DjangoModelFactory):
    """Per-(offer, persona) cooldown row.

    Default ``available_at`` is 1 second in the past so the row exists
    without gating. Tests exercising an active cooldown override
    ``available_at`` with a future datetime.
    """

    class Meta:
        model = OfferCooldown

    offer = factory.SubFactory(NPCServiceOfferFactory)
    persona = factory.SubFactory(_PERSONA_FACTORY)
    available_at = factory.LazyFunction(lambda: timezone.now() - timedelta(seconds=1))


class PermitOfferDetailsFactory(DjangoModelFactory):
    class Meta:
        model = PermitOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.PERMIT)


class NPCRoleCooldownFactory(DjangoModelFactory):
    """Per-(role, persona) cooldown row (#686). Inactive by default."""

    class Meta:
        model = NPCRoleCooldown

    role = factory.SubFactory(NPCRoleFactory)
    persona = factory.SubFactory(_PERSONA_FACTORY)
    available_at = factory.LazyFunction(lambda: timezone.now() - timedelta(seconds=1))


class MissionOfferDetailsFactory(DjangoModelFactory):
    """Per-(NPCServiceOffer, MissionTemplate) catalog row for MISSION offers (#686)."""

    class Meta:
        model = MissionOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.MISSION)
    mission_template = factory.SubFactory("world.missions.factories.MissionTemplateFactory")
    weight = None
    requirements_override = factory.LazyFunction(dict)
    role_cooldown_duration = None
