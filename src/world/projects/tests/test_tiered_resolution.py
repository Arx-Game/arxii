"""Tests for the TIERED_PERIOD tiered-resolver registry + scan wiring (#1891).

GANG_TURF is the first ``TIERED_PERIOD`` kind; before this, ``scan_active_projects``
only transitioned ACTIVE -> RESOLVING and never mapped progress -> tier ->
``resolve_project``. These tests cover the registry and the in-scan resolution
with per-project error isolation.
"""

import datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.services import (
    clear_tiered_resolvers,
    get_tiered_resolver,
    register_tiered_resolver,
    scan_active_projects,
)


class TieredResolverRegistryTests(TestCase):
    def setUp(self) -> None:
        clear_tiered_resolvers()

    def tearDown(self) -> None:
        clear_tiered_resolvers()

    def test_register_and_lookup(self) -> None:
        def resolver(_project) -> None: ...

        register_tiered_resolver(ProjectKind.TEST_KIND, resolver)
        self.assertIs(get_tiered_resolver(ProjectKind.TEST_KIND), resolver)

    def test_lookup_unknown_kind_raises(self) -> None:
        with self.assertRaises(LookupError):
            get_tiered_resolver(ProjectKind.TEST_KIND)


class ScanWiringTests(TestCase):
    def setUp(self) -> None:
        clear_tiered_resolvers()

    def tearDown(self) -> None:
        clear_tiered_resolvers()
        from world.projects.services import clear_kind_handlers

        clear_kind_handlers()

    def test_scan_calls_registered_resolver_after_transition(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            threshold_target=None,
        )
        project.time_limit = timezone.now() - datetime.timedelta(seconds=1)
        project.save(update_fields=["time_limit"])

        resolver = mock.Mock()
        register_tiered_resolver(ProjectKind.TEST_KIND, resolver)

        scan_active_projects()

        project.refresh_from_db()
        # The resolver is a bare Mock that does not call resolve_project, so the
        # project stays RESOLVING (transitioned) — we assert the resolver ran.
        self.assertEqual(project.status, ProjectStatus.RESOLVING)
        resolver.assert_called_once_with(project)

    def test_resolver_failure_rolls_back_to_active_and_continues(self) -> None:
        first = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            threshold_target=None,
        )
        first.time_limit = timezone.now() - datetime.timedelta(seconds=2)
        first.save(update_fields=["time_limit"])
        second = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            threshold_target=None,
        )
        second.time_limit = timezone.now() - datetime.timedelta(seconds=1)
        second.save(update_fields=["time_limit"])

        from world.projects.services import register_kind_handler, resolve_project
        from world.traits.factories import CheckOutcomeFactory

        def resolve_second(project) -> None:
            resolve_project(project, outcome_tier=CheckOutcomeFactory(success_level=1))

        def resolver(project) -> None:
            if project.pk == first.pk:
                msg = "boom"
                raise RuntimeError(msg)
            resolve_second(project)

        register_tiered_resolver(ProjectKind.TEST_KIND, resolver)
        # resolve_project dispatches the kind handler; TEST_KIND has none, so
        # register a no-op so the second project can reach COMPLETED.
        register_kind_handler(ProjectKind.TEST_KIND, lambda _p, _t: None)

        scan_active_projects()

        first.refresh_from_db()
        second.refresh_from_db()
        # First rolled back to ACTIVE (retryable next tick); not stranded RESOLVING.
        self.assertEqual(first.status, ProjectStatus.ACTIVE)
        # Second still resolved despite the first raising.
        self.assertEqual(second.status, ProjectStatus.COMPLETED)

    def test_no_resolver_leaves_project_resolving(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            threshold_target=None,
        )
        project.time_limit = timezone.now() - datetime.timedelta(seconds=1)
        project.save(update_fields=["time_limit"])

        scan_active_projects()

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RESOLVING)
