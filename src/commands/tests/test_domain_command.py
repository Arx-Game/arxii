"""Tests for the ``domain`` telnet command (#2239).

Exercises the subverb router end-to-end: bare ``domain`` lists administrable
domains; ``domain holding`` runs the real Action and mutates the DB; a caller
with no standing gets the empty-list message.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from django.test import TestCase

from commands.domains import CmdDomain
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import DomainHolding, HoldingKind
from world.societies.houses.services import create_domain


def _run(caller: Any, args: str) -> CmdDomain:
    cmd = CmdDomain()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"domain {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _capture(caller: Any) -> str:
    return "\n".join(str(c.args[0]) for c in caller.msg.call_args_list if c.args)


class CmdDomainTests(TestCase):
    def setUp(self) -> None:
        self.org = OrganizationFactory(name="House Westrock")
        self.domain = create_domain(area=AreaFactory(), name="Westrock Vale", owner_org=self.org)
        self.kind = HoldingKind.objects.create(
            name="Farmland", stream_kind="domain_tax", base_gross=1000
        )
        self.leader_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=self.org, persona=self.leader_sheet.primary_persona, rank=1
        )

    def test_bare_domain_lists_administrable_domains(self) -> None:
        caller = self.leader_sheet.character
        _run(caller, "")
        self.assertIn("Westrock Vale", _capture(caller))

    def test_holding_subverb_creates_holding(self) -> None:
        caller = self.leader_sheet.character
        _run(caller, "holding Westrock Vale Farmland name=South Fields")
        self.assertTrue(DomainHolding.objects.filter(domain=self.domain).exists())

    def test_outsider_runs_no_domains(self) -> None:
        caller = CharacterSheetFactory().character
        _run(caller, "")
        self.assertIn("don't run any domains", _capture(caller))
