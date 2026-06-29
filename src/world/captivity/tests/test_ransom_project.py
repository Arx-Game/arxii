"""Ransom-as-Project tests (#1500).

Covers the crowdfundable ransom loop end to end: the GM demand surface
(``demand_ransom_project`` + the telnet command + the web endpoint), the
instant-completion seam that frees the captive the moment the threshold is
funded, the idempotent kind handler, and the red captive-status banner the
cell room shows.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from commands.captivity import CmdDemandRansom
from evennia_extensions.factories import AccountFactory
from typeclasses.mixins import _maybe_render_captivity_status
from world.captivity.constants import CaptivityStatus
from world.captivity.exceptions import AlreadyDemandedError, NotHeldError
from world.captivity.ransom import _RANSOM_FLOOR_COPPERS
from world.captivity.ransom_project import (
    demand_ransom_project,
    resolve_ransom_project,
)
from world.captivity.services import capture_character, escape_captivity
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.currency.models import CharacterPurse
from world.instances.factories import InstancedRoomFactory
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.models import Project
from world.projects.services import (
    donate_to_project,
    register_instant_completion_kind,
    register_kind_handler,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


def _held_captivity():
    """A freshly captured captive, held in a spawned cell, with a captor org."""
    return capture_character(
        captive=CharacterSheetFactory(),
        captor_organization=OrganizationFactory(),
    )


class DemandRansomProjectTests(TestCase):
    def test_demand_creates_active_ransom_project_linked_to_captivity(self) -> None:
        captivity = _held_captivity()

        project = demand_ransom_project(captivity, amount=10_000)

        assert project.kind == ProjectKind.RANSOM
        assert project.status == ProjectStatus.ACTIVE
        assert project.completion_mode == CompletionMode.SINGLE_THRESHOLD
        assert project.threshold_target == 100  # 10_000 coppers // 100
        assert project.owner_persona == captivity.captive.primary_persona
        captivity.refresh_from_db()
        assert captivity.ransom_project == project

    def test_demand_uses_the_default_amount_when_unspecified(self) -> None:
        captivity = _held_captivity()

        project = demand_ransom_project(captivity)

        assert project.threshold_target == _RANSOM_FLOOR_COPPERS // 100

    def test_demand_on_a_freed_captive_is_rejected(self) -> None:
        captivity = _held_captivity()
        escape_captivity(captivity.captive)  # they're no longer HELD

        with self.assertRaises(NotHeldError):
            demand_ransom_project(captivity)

    def test_demand_twice_is_rejected_while_the_first_stands(self) -> None:
        captivity = _held_captivity()
        demand_ransom_project(captivity)

        with self.assertRaises(AlreadyDemandedError):
            demand_ransom_project(captivity)


class RansomProjectPaymentTests(TestCase):
    def setUp(self) -> None:
        # Defensive: app-ready registers these, but other framework tests may
        # clear the registries. Re-register so this suite is self-contained.
        register_kind_handler(ProjectKind.RANSOM, resolve_ransom_project)
        register_instant_completion_kind(ProjectKind.RANSOM)

    def _donor(self, *, balance: int):
        donor = PersonaFactory()
        CharacterPurse.objects.create(character_sheet=donor.character_sheet, balance=balance)
        return donor

    def test_full_donation_frees_the_captive_instantly(self) -> None:
        captivity = _held_captivity()
        project = demand_ransom_project(captivity, amount=10_000)  # threshold 100
        donor = self._donor(balance=10_000)

        donate_to_project(project, donor_persona=donor, amount=10_000)

        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED
        captivity.captive.refresh_from_db()
        assert captivity.captive.lifecycle_state == LifecycleState.ALIVE
        project.refresh_from_db()
        assert project.status == ProjectStatus.COMPLETED

    def test_partial_donation_leaves_the_captive_held(self) -> None:
        captivity = _held_captivity()
        project = demand_ransom_project(captivity, amount=10_000)  # threshold 100
        donor = self._donor(balance=10_000)

        donate_to_project(project, donor_persona=donor, amount=5_000)  # progress 50 < 100

        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.HELD
        project.refresh_from_db()
        assert project.status == ProjectStatus.ACTIVE

    def test_two_donors_crowdfund_the_release(self) -> None:
        captivity = _held_captivity()
        project = demand_ransom_project(captivity, amount=10_000)  # threshold 100

        donate_to_project(project, donor_persona=self._donor(balance=6_000), amount=6_000)
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.HELD  # 60/100 so far

        donate_to_project(project, donor_persona=self._donor(balance=4_000), amount=4_000)
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED  # 100/100 → freed


class ResolveRansomProjectHandlerTests(TestCase):
    def test_handler_is_idempotent_once_freed(self) -> None:
        captivity = _held_captivity()
        project = demand_ransom_project(captivity, amount=10_000)
        resolve_ransom_project(project)
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED

        # A second fire (e.g. a concurrent funder) is a harmless no-op.
        resolve_ransom_project(project)
        captivity.refresh_from_db()
        assert captivity.status == CaptivityStatus.RANSOMED

    def test_handler_noops_when_no_captivity_points_at_the_project(self) -> None:
        orphan = Project.objects.create(
            kind=ProjectKind.RANSOM,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            owner_persona=PersonaFactory(),
            started_at="2026-01-01T00:00:00Z",
            time_limit="2030-01-01T00:00:00Z",
            threshold_target=1,
        )
        resolve_ransom_project(orphan)  # no linked captivity → must not raise


class CaptiveStatusInCellDescTests(TestCase):
    def test_cell_shows_a_red_ooc_ransom_banner(self) -> None:
        captivity = _held_captivity()
        project = demand_ransom_project(captivity, amount=10_000)

        rendered = _maybe_render_captivity_status(captivity.cell.room)

        assert rendered is not None
        assert "held captive here" in rendered
        assert "|r" in rendered  # red OOC styling
        assert f"project/donate {project.pk}" in rendered

    def test_a_room_with_no_captive_renders_nothing(self) -> None:
        empty_room = InstancedRoomFactory().room
        assert _maybe_render_captivity_status(empty_room) is None


class CmdDemandRansomTests(TestCase):
    def setUp(self) -> None:
        self.account = AccountFactory(is_staff=True)
        self.caller = MagicMock()
        self.caller.msg = MagicMock()

    def _run(self, args: str, target: object | None) -> str:
        self.caller.search = MagicMock(return_value=target)
        cmd = CmdDemandRansom()
        cmd.caller = self.caller
        cmd.account = self.account
        cmd.args = args
        cmd.switches = []
        cmd.func()
        return "\n".join(str(c.args[0]) for c in self.caller.msg.call_args_list if c.args)

    def test_demand_creates_the_project_and_reports_it(self) -> None:
        captivity = _held_captivity()
        out = self._run("Captive = 10000", target=captivity.captive.character)

        captivity.refresh_from_db()
        assert captivity.ransom_project is not None
        assert captivity.ransom_project.threshold_target == 100
        assert "Ransom demanded" in out

    def test_demand_on_a_non_captive_is_rejected(self) -> None:
        free_sheet = CharacterSheetFactory()
        out = self._run("Nobody", target=free_sheet.character)
        assert "not being held captive" in out


class DemandRansomViewTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("gm:gm-demand-ransom")

    def test_staff_can_demand_a_ransom(self) -> None:
        staff = AccountFactory(is_staff=True)
        captivity = _held_captivity()
        self.client.force_authenticate(user=staff)

        resp = self.client.post(
            self.url,
            {"captivity_id": captivity.pk, "amount": 10_000},
            format="json",
        )

        assert resp.status_code == 201
        captivity.refresh_from_db()
        assert captivity.ransom_project is not None
        assert resp.data["project_id"] == captivity.ransom_project.pk
        assert resp.data["threshold_target"] == 100

    def test_a_non_gm_non_staff_user_is_forbidden(self) -> None:
        random_user = AccountFactory()
        captivity = _held_captivity()
        self.client.force_authenticate(user=random_user)

        resp = self.client.post(
            self.url,
            {"captivity_id": captivity.pk, "amount": 10_000},
            format="json",
        )

        assert resp.status_code == 403
        captivity.refresh_from_db()
        assert captivity.ransom_project is None
