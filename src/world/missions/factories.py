"""FactoryBoy factories for the Missions system (Phases 1 & 2)."""

from __future__ import annotations

from datetime import timedelta

import factory
from factory.django import DjangoModelFactory

from world.missions.constants import (
    AccessTier,
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    GiverKind,
    MissionStatus,
    OptionKind,
    OptionSource,
    RewardGroupRule,
)
from world.missions.models import (
    MissionCategory,
    MissionDeedRecord,
    MissionDeedRewardLine,
    MissionGiver,
    MissionGiverOffering,
    MissionInstance,
    MissionNode,
    MissionNodeSnapshot,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionParticipant,
    MissionRewardQueue,
    MissionTemplate,
)


class MissionCategoryFactory(DjangoModelFactory):
    """Factory for the MissionCategory lookup model."""

    class Meta:
        model = MissionCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"mission-category-{n}")
    description = factory.Faker("sentence")


# ---------------------------------------------------------------------------
# Mission graph factories
# ---------------------------------------------------------------------------


class MissionTemplateFactory(DjangoModelFactory):
    """Factory for MissionTemplate. Defaults to a valid, active GLOBAL arc."""

    class Meta:
        model = MissionTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Mission {n}")
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
    # Factory default differs from MODEL default: the model defaults to
    # STAFF_ONLY (production-safe — new authored templates are in testing
    # until staff publishes them). The factory defaults to OPEN so the
    # entire test suite keeps surfacing templates to non-staff characters
    # without every caller passing access_tier. Tests covering the
    # STAFF_ONLY tier set access_tier explicitly.
    #
    # NOTE: factory_boy's ``django_get_or_create`` silently drops non-lookup
    # kwargs when the row pre-exists. If a test calls
    # ``MissionTemplateFactory(name="x", access_tier=AccessTier.STAFF_ONLY)``
    # after another call has already created name="x" (with the default OPEN),
    # the second call returns the existing OPEN row and the access_tier kwarg
    # is silently dropped. Tests that care about the tier MUST use a unique
    # name (the convention in OfferMissionsAccessTierTests).
    access_tier = AccessTier.OPEN


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
    """Factory for MissionInstance. Defaults to an ACTIVE, free (no source Beat) run.

    Callers exercising the Phase 5b.3 stories-missions seam pass
    ``source_beat=`` with a ``world.stories.factories.BeatFactory()``
    instance; the default ``None`` keeps the existing fixture surface
    unchanged (a "free" mission).
    """

    class Meta:
        model = MissionInstance

    template = factory.SubFactory(MissionTemplateFactory)
    current_node = None
    status = MissionStatus.ACTIVE
    completed_at = None
    source_beat = None


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


class MissionGiverFactory(DjangoModelFactory):
    """Factory for MissionGiver.

    Defaults to an active, target-less ROOM_TRIGGER-kind giver — a
    drafty row (passes ``clean()``, fails ``is_publishable``). Tests
    exercising a specific kind pass ``giver_kind=`` + a matching
    ``target=`` (whose typeclass clean() validates).
    """

    class Meta:
        model = MissionGiver
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Giver {n}")
    giver_kind = GiverKind.ROOM_TRIGGER
    target = None
    org = None
    is_active = True


class MissionGiverOfferingFactory(DjangoModelFactory):
    """Factory for the MissionGiver↔MissionTemplate through-model."""

    class Meta:
        model = MissionGiverOffering

    giver = factory.SubFactory(MissionGiverFactory)
    template = factory.SubFactory(MissionTemplateFactory)
    weight_override = None
    requirements_override = factory.LazyFunction(dict)


class MissionDeedRewardLineFactory(DjangoModelFactory):
    """Factory for a persisted structured reward line.

    ``recipient`` defaults to a fresh CharacterFactory; callers that want the
    line to point at the deed's actor or a participant should pass it
    explicitly.
    """

    class Meta:
        model = MissionDeedRewardLine

    deed = factory.SubFactory(MissionDeedRecordFactory)
    recipient = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    kind = DeedRewardKind.IMMEDIATE
    sink = DeedRewardSink.MONEY
    amount = 100
    ref = ""


class MissionOptionRouteRewardFactory(DjangoModelFactory):
    """Factory for an authored reward template on a MissionOptionRoute.

    Defaults to a broadcast IMMEDIATE/MONEY reward of 100 (i.e.
    ``contract_holder_only=False``). Callers exercising contract-only payouts
    pass ``contract_holder_only=True``; callers exercising the cron/propagation
    seams override ``kind=`` accordingly.
    """

    class Meta:
        model = MissionOptionRouteReward

    route = factory.SubFactory(MissionOptionRouteFactory)
    kind = DeedRewardKind.IMMEDIATE
    sink = DeedRewardSink.MONEY
    amount = 100
    ref = ""
    contract_holder_only = False


class MissionRewardQueueFactory(DjangoModelFactory):
    """Factory for a deferred-payout queue entry on a MissionDeedRewardLine.

    Defaults to a pending (applied=False) row mirroring the line's
    POST_CRON/LEGEND_POINTS shape — the canonical 5b.1 deferred-payout case.
    ``kind`` and ``sink`` are LazyAttribute-derived from ``line`` so callers
    that only pass a line get a consistent queue row by default.
    """

    class Meta:
        model = MissionRewardQueue

    deed = factory.SelfAttribute("line.deed")
    line = factory.SubFactory(
        MissionDeedRewardLineFactory,
        kind=DeedRewardKind.POST_CRON,
        sink=DeedRewardSink.LEGEND_POINTS,
    )
    kind = factory.SelfAttribute("line.kind")
    sink = factory.SelfAttribute("line.sink")
    applied = False
    applied_at = None
    failure_reason = ""
