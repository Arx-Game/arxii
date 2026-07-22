"""FactoryBoy factories for the unified NPC service framework."""

from datetime import timedelta

from django.utils import timezone
import factory
from factory.django import DjangoModelFactory

from world.npc_services.constants import DrawMode, NpcRegardEventReason, OfferKind, RegardTargetType
from world.npc_services.models import (
    DistinctionRegardSeed,
    Functionary,
    MissionOfferDetails,
    NpcRegard,
    NpcRegardEvent,
    NPCRole,
    NPCRoleCooldown,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
    PermitOfferDetails,
    ProfileRecordingOfferDetails,
    StylingOfferDetails,
    TrainOfferDetails,
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


class FunctionaryFactory(DjangoModelFactory):
    """A class-1 NPC placed in a room (#1766)."""

    class Meta:
        model = Functionary

    role = factory.SubFactory(NPCRoleFactory)
    room = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    name_override = ""
    description_override = ""
    is_active = True


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


class TrainOfferDetailsFactory(DjangoModelFactory):
    """Per-offer TRAIN details (#2440) — one row per teachable technique."""

    class Meta:
        model = TrainOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.TRAIN)
    technique = factory.SubFactory("world.magic.factories.TechniqueFactory")
    learn_ap_cost = 5
    gold_cost = 0


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


class NpcRegardFactory(DjangoModelFactory):
    """A notable NPC's opinion of a persona (default), an Organization, or a Society."""

    class Meta:
        model = NpcRegard

    holder_persona = factory.SubFactory(_PERSONA_FACTORY)
    target_type = RegardTargetType.PERSONA
    target_persona = factory.SubFactory(_PERSONA_FACTORY)
    target_organization = None
    target_society = None
    value = 0

    class Params:
        on_organization = factory.Trait(
            target_type=RegardTargetType.ORGANIZATION,
            target_persona=None,
            target_organization=factory.SubFactory("world.societies.factories.OrganizationFactory"),
        )
        on_society = factory.Trait(
            target_type=RegardTargetType.SOCIETY,
            target_persona=None,
            target_society=factory.SubFactory("world.societies.factories.SocietyFactory"),
        )


class NpcRegardEventFactory(DjangoModelFactory):
    class Meta:
        model = NpcRegardEvent

    regard = factory.SubFactory(NpcRegardFactory)
    reason = NpcRegardEventReason.GM_MANUAL_ADJUSTMENT
    amount = 5


class DistinctionRegardSeedFactory(DjangoModelFactory):
    class Meta:
        model = DistinctionRegardSeed

    distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    npc_persona = factory.SubFactory(_PERSONA_FACTORY)
    starting_value = 50
    reason = ""


class StylingOfferDetailsFactory(DjangoModelFactory):
    class Meta:
        model = StylingOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.STYLING)
    trait = factory.SubFactory("world.forms.factories.FormTraitFactory", is_cosmetic=True)
    target_option = factory.SubFactory(
        "world.forms.factories.FormTraitOptionFactory",
        trait=factory.SelfAttribute("..trait"),
    )
    price_coppers = 100


class ProfileRecordingOfferDetailsFactory(DjangoModelFactory):
    class Meta:
        model = ProfileRecordingOfferDetails

    offer = factory.SubFactory(NPCServiceOfferFactory, kind=OfferKind.PROFILE_RECORDING)
    price_coppers = 500
