"""FactoryBoy factories for the Missions system (Phases 1 & 2)."""

from __future__ import annotations

from datetime import timedelta

import factory
from factory.django import DjangoModelFactory

from world.missions.constants import (
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    MissionStatus,
    OptionKind,
    OptionProduces,
    OptionSource,
    RewardGroupRule,
)
from world.missions.models import (
    SOURCE_DISTINCTION,
    Affordance,
    AffordanceBinding,
    MissionDeedRecord,
    MissionDeedRewardLine,
    MissionInstance,
    MissionNode,
    MissionNodeSnapshot,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionParticipant,
    MissionTemplate,
)


class AffordanceFactory(DjangoModelFactory):
    """Factory for the Affordance lookup model."""

    class Meta:
        model = Affordance
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"affordance-{n}")
    description = factory.Faker("sentence")


class AffordanceBindingFactory(DjangoModelFactory):
    """Factory for AffordanceBinding.

    Defaults to a distinction-sourced BRANCH binding. Callers exercising
    other discriminators pass ``source_kind=`` plus the matching typed FK and
    clear ``source_distinction``; callers exercising checks pass
    ``produces=OptionProduces.CHECK`` with a ``check_type``.
    """

    class Meta:
        model = AffordanceBinding

    source_kind = SOURCE_DISTINCTION
    source_distinction = factory.SubFactory("world.distinctions.factories.DistinctionFactory")
    affordance = factory.SubFactory(AffordanceFactory)
    produces = OptionProduces.BRANCH
    check_type = None
    base_risk = 0
    ic_framing = factory.Faker("sentence")
    rider = None


# ---------------------------------------------------------------------------
# Phase 2 — mission graph factories
# ---------------------------------------------------------------------------


class MissionTemplateFactory(DjangoModelFactory):
    """Factory for MissionTemplate. Defaults to a valid, active GLOBAL arc."""

    class Meta:
        model = MissionTemplate
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Mission {n}")
    slug = factory.Sequence(lambda n: f"mission-{n}")
    summary = factory.Faker("paragraph")
    epilogue = ""
    level_band_min = 1
    level_band_max = 5
    risk_tier = 1
    base_weight = 1
    created_in_era = None
    arc_scope = ArcScope.GLOBAL
    percent_replace = 0
    cooldown = timedelta(days=1)
    reward_group_rule = RewardGroupRule.ALL_EQUAL
    is_active = True


class MissionNodeFactory(DjangoModelFactory):
    """Factory for MissionNode. Defaults to a non-entry COINFLIP node."""

    class Meta:
        model = MissionNode

    template = factory.SubFactory(MissionTemplateFactory)
    key = factory.Sequence(lambda n: f"node-{n}")
    is_entry = False
    conflict_mode = ConflictMode.COINFLIP
    joint_combine = None
    joint_count = None
    deny_all_riders = False


class MissionOptionFactory(DjangoModelFactory):
    """Factory for MissionOption. Defaults to an AUTHORED BRANCH option."""

    class Meta:
        model = MissionOption

    node = factory.SubFactory(MissionNodeFactory)
    order = factory.Sequence(lambda n: n)
    option_kind = OptionKind.BRANCH
    source_kind = OptionSource.AUTHORED
    visibility_rule = factory.LazyFunction(dict)
    authored_check_type = None
    authored_base_risk = 0
    authored_ic_framing = ""
    branch_target = None


class MissionOptionRouteFactory(DjangoModelFactory):
    """Factory for MissionOptionRoute. Defaults to a terminal BRANCH route."""

    class Meta:
        model = MissionOptionRoute

    option = factory.SubFactory(MissionOptionFactory)
    outcome_tier = None
    target_node = None
    is_random_set = False
    consequence = None


class MissionOptionRouteCandidateFactory(DjangoModelFactory):
    """Factory for a weighted destination in a randomized route."""

    class Meta:
        model = MissionOptionRouteCandidate

    route = factory.SubFactory(MissionOptionRouteFactory)
    target_node = factory.SubFactory(MissionNodeFactory)
    weight = 1


class MissionInstanceFactory(DjangoModelFactory):
    """Factory for MissionInstance. Defaults to an ACTIVE run."""

    class Meta:
        model = MissionInstance

    template = factory.SubFactory(MissionTemplateFactory)
    current_node = None
    status = MissionStatus.ACTIVE
    completed_at = None


class MissionParticipantFactory(DjangoModelFactory):
    """Factory for MissionParticipant."""

    class Meta:
        model = MissionParticipant

    instance = factory.SubFactory(MissionInstanceFactory)
    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    is_contract_holder = False


class MissionNodeSnapshotFactory(DjangoModelFactory):
    """Factory for MissionNodeSnapshot."""

    class Meta:
        model = MissionNodeSnapshot

    instance = factory.SubFactory(MissionInstanceFactory)
    node = factory.SubFactory(MissionNodeFactory)
    participant = factory.SubFactory(MissionParticipantFactory)


class MissionDeedRecordFactory(DjangoModelFactory):
    """Factory for MissionDeedRecord. Defaults to a BRANCH deed (no outcome)."""

    class Meta:
        model = MissionDeedRecord

    instance = factory.SubFactory(MissionInstanceFactory)
    actor = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    node = factory.SubFactory(MissionNodeFactory)
    option = factory.SubFactory(MissionOptionFactory)
    outcome = None


class MissionDeedRewardLineFactory(DjangoModelFactory):
    """Factory for a persisted structured reward line."""

    class Meta:
        model = MissionDeedRewardLine

    deed = factory.SubFactory(MissionDeedRecordFactory)
    kind = DeedRewardKind.IMMEDIATE
    sink = DeedRewardSink.MONEY
    amount = 100
    ref = ""
