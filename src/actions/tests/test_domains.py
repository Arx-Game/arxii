"""In-play domain management action tests (#2239).

Every dispatch here passes plain int kwargs (``domain_id`` etc.), proving the
REST dispatch shape works — the actions resolve ids themselves (see
``actions/CLAUDE.md`` on REST not auto-resolving ObjectDB/model kwargs).
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.domains import (
    AddDomainHoldingAction,
    AppointDomainOfficeAction,
    StartDomainImprovementAction,
    VacateDomainOfficeAction,
)
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.constants import DOMAIN_STEWARD_OFFICE
from world.societies.houses.models import DomainHolding, HoldingKind
from world.societies.houses.services import create_domain
from world.societies.office_services import holds_office


class DomainManagementActionTests(TestCase):
    def setUp(self) -> None:
        self.org = OrganizationFactory(name="House Westrock")
        self.domain = create_domain(area=AreaFactory(), name="Westrock Vale", owner_org=self.org)
        self.kind = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        # Leader — a can_manage_ranks (tier 1) membership for the actor's persona.
        self.leader_sheet = CharacterSheetFactory()
        self.leader = self.leader_sheet.character
        OrganizationMembershipFactory(
            organization=self.org, persona=self.leader_sheet.primary_persona, rank=1
        )
        # Outsider — no membership, no office.
        self.outsider_sheet = CharacterSheetFactory()
        self.outsider = self.outsider_sheet.character

    def test_add_holding_success_via_rest_int_kwargs(self) -> None:
        result = AddDomainHoldingAction().run(
            actor=self.leader,
            domain_id=self.domain.pk,
            holding_kind_id=self.kind.pk,
            name="South Fields",
        )
        self.assertTrue(result.success, result.message)
        holding = DomainHolding.objects.get(pk=result.data["holding_id"])
        self.assertEqual(holding.domain, self.domain)
        self.assertEqual(holding.income_stream.organization, self.org)

    def test_add_holding_rejected_for_outsider(self) -> None:
        result = AddDomainHoldingAction().run(
            actor=self.outsider,
            domain_id=self.domain.pk,
            holding_kind_id=self.kind.pk,
        )
        self.assertFalse(result.success)
        self.assertFalse(DomainHolding.objects.filter(domain=self.domain).exists())

    def test_add_holding_unknown_domain(self) -> None:
        result = AddDomainHoldingAction().run(
            actor=self.leader, domain_id=999999, holding_kind_id=self.kind.pk
        )
        self.assertFalse(result.success)

    def test_start_improvement_creates_project(self) -> None:
        result = StartDomainImprovementAction().run(
            actor=self.leader,
            domain_id=self.domain.pk,
            cost=500,
            prosperity_increase=5,
        )
        self.assertTrue(result.success, result.message)
        project = Project.objects.get(pk=result.data["project_id"])
        self.assertEqual(project.kind, ProjectKind.DOMAIN_IMPROVEMENT)
        self.assertEqual(project.owner_persona, self.leader_sheet.primary_persona)

    def test_start_improvement_rejected_for_outsider(self) -> None:
        result = StartDomainImprovementAction().run(
            actor=self.outsider, domain_id=self.domain.pk, cost=500
        )
        self.assertFalse(result.success)
        self.assertFalse(Project.objects.filter(kind=ProjectKind.DOMAIN_IMPROVEMENT).exists())

    def test_appoint_office_by_leader_then_steward_can_administer(self) -> None:
        steward_sheet = CharacterSheetFactory()
        result = AppointDomainOfficeAction().run(
            actor=self.leader,
            domain_id=self.domain.pk,
            holder_persona_id=steward_sheet.primary_persona.pk,
            title="Minister of the Domains",
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            holds_office(steward_sheet.primary_persona, self.org, DOMAIN_STEWARD_OFFICE)
        )
        # The freshly-appointed steward can now add a holding.
        steward_result = AddDomainHoldingAction().run(
            actor=steward_sheet.character,
            domain_id=self.domain.pk,
            holding_kind_id=self.kind.pk,
        )
        self.assertTrue(steward_result.success, steward_result.message)

    def test_appoint_office_rejected_for_non_leader(self) -> None:
        target_sheet = CharacterSheetFactory()
        result = AppointDomainOfficeAction().run(
            actor=self.outsider,
            domain_id=self.domain.pk,
            holder_persona_id=target_sheet.primary_persona.pk,
        )
        self.assertFalse(result.success)
        self.assertFalse(
            holds_office(target_sheet.primary_persona, self.org, DOMAIN_STEWARD_OFFICE)
        )

    def test_vacate_office_by_leader(self) -> None:
        steward_sheet = CharacterSheetFactory()
        AppointDomainOfficeAction().run(
            actor=self.leader,
            domain_id=self.domain.pk,
            holder_persona_id=steward_sheet.primary_persona.pk,
        )
        result = VacateDomainOfficeAction().run(actor=self.leader, domain_id=self.domain.pk)
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            holds_office(steward_sheet.primary_persona, self.org, DOMAIN_STEWARD_OFFICE)
        )
