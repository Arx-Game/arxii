"""Tests for the GANG_TURF project kind (#1891). PG-only — societies app."""

import datetime

from django.test import TestCase, tag
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.services import (
    clear_kind_handlers,
    clear_tiered_resolvers,
    register_kind_handler,
    register_tiered_resolver,
    scan_active_projects,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.gang_turf import (
    _select_tier,
    _tier_to_reputation_delta,
    complete_gang_turf,
    resolve_gang_turf,
    start_gang_turf_project,
)
from world.societies.membership_services import ensure_default_rank_ladder
from world.societies.models import (
    GangTurfDetails,
    GangTurfReputationAward,
    GangTurfTierThreshold,
    OrganizationMembership,
    OrganizationReputation,
)
from world.traits.factories import CheckOutcomeFactory


def _gang_org_with_leader():
    """Create a gang org + a leader (tier-1, can_lead_rituals) membership."""
    org_type = OrganizationTypeFactory(name="gang")
    org = OrganizationFactory(org_type=org_type)
    ranks = ensure_default_rank_ladder(org)
    leader_rank = next(r for r in ranks if r.tier == 1)
    leader = PersonaFactory()
    OrganizationMembership.objects.create(organization=org, persona=leader, rank=leader_rank)
    return org, leader, leader_rank


@tag("postgres")
class SelectTierTests(TestCase):
    def test_highest_threshold_at_or_below_progress(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.GANG_TURF, completion_mode=CompletionMode.TIERED_PERIOD
        )
        org, _, _ = _gang_org_with_leader()
        details = GangTurfDetails.objects.create(project=project, organization=org)
        failure = CheckOutcomeFactory(success_level=-1)
        partial = CheckOutcomeFactory(success_level=0)
        success = CheckOutcomeFactory(success_level=1)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=failure, min_progress=0)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=partial, min_progress=25)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=success, min_progress=50)

        thresholds = list(details.tier_thresholds.all())
        self.assertEqual(_select_tier(thresholds, 0).outcome_tier, failure)
        self.assertEqual(_select_tier(thresholds, 25).outcome_tier, partial)
        self.assertEqual(_select_tier(thresholds, 49).outcome_tier, partial)
        self.assertEqual(_select_tier(thresholds, 50).outcome_tier, success)
        self.assertEqual(_select_tier(thresholds, 999).outcome_tier, success)


@tag("postgres")
class TierToDeltaTests(TestCase):
    def test_returns_delta_for_awarded_tier(self) -> None:
        outcome = CheckOutcomeFactory(success_level=1)
        GangTurfReputationAward.objects.create(outcome_tier=outcome, reputation_delta=250)
        self.assertEqual(_tier_to_reputation_delta(outcome), 250)

    def test_returns_zero_when_no_award_row(self) -> None:
        outcome = CheckOutcomeFactory(success_level=1)
        self.assertEqual(_tier_to_reputation_delta(outcome), 0)


@tag("postgres")
class CompleteGangTurfTests(TestCase):
    def test_success_tier_bumps_org_reputation(self) -> None:
        org, leader, _ = _gang_org_with_leader()
        project = ProjectFactory(
            kind=ProjectKind.GANG_TURF,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=leader,
            current_progress=50,
        )
        details = GangTurfDetails.objects.create(project=project, organization=org)
        success = CheckOutcomeFactory(success_level=1)
        GangTurfTierThreshold.objects.create(
            details=details, outcome_tier=CheckOutcomeFactory(success_level=-1), min_progress=0
        )
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=success, min_progress=50)
        GangTurfReputationAward.objects.create(outcome_tier=success, reputation_delta=250)

        complete_gang_turf(project, success)

        rep = OrganizationReputation.objects.get(persona=leader, organization=org)
        self.assertEqual(rep.value, 250)

    def test_failure_tier_no_op(self) -> None:
        org, leader, _ = _gang_org_with_leader()
        project = ProjectFactory(
            kind=ProjectKind.GANG_TURF,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=leader,
        )
        GangTurfDetails.objects.create(project=project, organization=org)
        failure = CheckOutcomeFactory(success_level=-1)

        complete_gang_turf(project, failure)

        self.assertFalse(
            OrganizationReputation.objects.filter(persona=leader, organization=org).exists()
        )


@tag("postgres")
class ResolveGangTurfTests(TestCase):
    def setUp(self) -> None:
        # resolve_project dispatches the kind handler; register GANG_TURF's.
        register_kind_handler(ProjectKind.GANG_TURF, complete_gang_turf)

    def tearDown(self) -> None:
        clear_kind_handlers()
        clear_tiered_resolvers()

    def test_grades_by_progress_and_resolves(self) -> None:
        org, leader, _ = _gang_org_with_leader()
        project = ProjectFactory(
            kind=ProjectKind.GANG_TURF,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.RESOLVING,
            owner_persona=leader,
            current_progress=50,
        )
        details = GangTurfDetails.objects.create(project=project, organization=org)
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=failure, min_progress=0)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=success, min_progress=50)
        GangTurfReputationAward.objects.create(outcome_tier=success, reputation_delta=250)

        resolve_gang_turf(project)

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier, success)


@tag("postgres")
class StartGangTurfProjectTests(TestCase):
    def test_leader_can_open_and_thresholds_seeded(self) -> None:
        org, leader, _ = _gang_org_with_leader()
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        thresholds = [(failure, 0), (success, 50)]

        project = start_gang_turf_project(
            organization=org, owner_persona=leader, tier_thresholds=thresholds, period_days=30
        )

        self.assertEqual(project.kind, ProjectKind.GANG_TURF)
        self.assertEqual(project.completion_mode, CompletionMode.TIERED_PERIOD)
        self.assertEqual(project.owner_persona, leader)
        self.assertIsNone(project.threshold_target)
        self.assertEqual(project.gang_turf_details.tier_thresholds.count(), 2)
        self.assertAlmostEqual(
            (project.time_limit - project.started_at).total_seconds(), 30 * 86400, delta=5
        )

    def test_non_leader_rejected(self) -> None:
        org_type = OrganizationTypeFactory(name="gang")
        org = OrganizationFactory(org_type=org_type)
        ranks = ensure_default_rank_ladder(org)
        member_rank = next(r for r in ranks if r.tier == 2)  # can_lead_rituals False
        member = PersonaFactory()
        OrganizationMembership.objects.create(organization=org, persona=member, rank=member_rank)

        with self.assertRaises(ValueError):
            start_gang_turf_project(organization=org, owner_persona=member)

    def test_non_member_rejected(self) -> None:
        org, _, _ = _gang_org_with_leader()
        outsider = PersonaFactory()

        with self.assertRaises(ValueError):
            start_gang_turf_project(organization=org, owner_persona=outsider)


@tag("postgres")
class ScanJourneyTests(TestCase):
    def setUp(self) -> None:
        register_kind_handler(ProjectKind.GANG_TURF, complete_gang_turf)
        register_tiered_resolver(ProjectKind.GANG_TURF, resolve_gang_turf)

    def tearDown(self) -> None:
        clear_kind_handlers()
        clear_tiered_resolvers()

    def test_scan_grades_and_resolves_in_one_tick(self) -> None:
        org, leader, _ = _gang_org_with_leader()
        project = ProjectFactory(
            kind=ProjectKind.GANG_TURF,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            owner_persona=leader,
            current_progress=50,
            threshold_target=None,
        )
        details = GangTurfDetails.objects.create(project=project, organization=org)
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=failure, min_progress=0)
        GangTurfTierThreshold.objects.create(details=details, outcome_tier=success, min_progress=50)
        GangTurfReputationAward.objects.create(outcome_tier=success, reputation_delta=250)
        project.time_limit = timezone.now() - datetime.timedelta(seconds=1)
        project.save(update_fields=["time_limit"])

        scan_active_projects()

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier, success)
        self.assertEqual(
            OrganizationReputation.objects.get(persona=leader, organization=org).value, 250
        )
