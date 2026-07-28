"""FactoryBoy factories for the tasking app (#2820 phase 1)."""

from __future__ import annotations

from datetime import timedelta

import factory
from factory.django import DjangoModelFactory

from world.tasking.constants import TaskTargetKind
from world.tasking.models import OrgTask, TaskFulfillment, TaskOutcomeRoute, TaskTemplate

_PERSONA_FACTORY = "world.scenes.factories.PersonaFactory"


class TaskTemplateFactory(DjangoModelFactory):
    class Meta:
        model = TaskTemplate

    name = factory.Sequence(lambda n: f"Task Template {n}")
    description = "PLACEHOLDER task template."
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    check_difficulty = 0
    duration = timedelta(days=1)
    target_kind = TaskTargetKind.NONE


class TaskOutcomeRouteFactory(DjangoModelFactory):
    class Meta:
        model = TaskOutcomeRoute

    template = factory.SubFactory(TaskTemplateFactory)
    outcome_tier = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")
    money_reward = 0


class OrgTaskFactory(DjangoModelFactory):
    class Meta:
        model = OrgTask

    template = factory.SubFactory(TaskTemplateFactory)
    org = factory.SubFactory("world.societies.factories.OrganizationFactory")
    issued_by = factory.SubFactory(_PERSONA_FACTORY)
    target_kind = TaskTargetKind.NONE


class TaskFulfillmentFactory(DjangoModelFactory):
    class Meta:
        model = TaskFulfillment

    task = factory.SubFactory(OrgTaskFactory)
    npc_asset = factory.SubFactory("world.assets.factories.NPCAssetFactory")
    handler = factory.SubFactory(_PERSONA_FACTORY)
