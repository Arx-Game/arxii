"""CONTEST options (#3568): difficulty adds the opposition's level term; tiers route as CHECK."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import level_opposition
from world.checks.test_helpers import force_check_outcome
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.resolution import resolve_option
from world.traits.factories import CheckOutcomeFactory

_LEVEL = "world.missions.services.resolution.effective_combat_level"


class ContestResolutionTests(TestCase):
    def setUp(self) -> None:
        # Mirrors the fixture shape of ResolveCheckOptionTests in
        # test_services_resolution_resolve.py: a template with risk_tier, an
        # entry node, an actor participant with a character, success/failure
        # CheckOutcome rows, one route per tier.
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

        self.template = MissionTemplateFactory(name="contest-tmpl", risk_tier=4)
        self.instance = MissionInstanceFactory(template=self.template)
        self.entry = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.node_a = MissionNodeFactory(template=self.template, key="a")
        self.node_b = MissionNodeFactory(template=self.template, key="b")
        self.actor = MissionParticipantFactory(
            instance=self.instance,
            character=self.character.sheet_data,
            is_contract_holder=True,
        )

        self.success = CheckOutcomeFactory(name="ContestSuccess", success_level=3)
        self.failure = CheckOutcomeFactory(name="ContestFailure", success_level=-3)
        self.check_type = CheckTypeFactory(name="ContestCheck")

        self.opposition = CharacterSheetFactory()
        self.opp_check = CheckTypeFactory(name="ContestOppCheck")
        self.contest = MissionOptionFactory(
            node=self.entry,
            order=5,
            option_kind=OptionKind.CONTEST,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
            opposition_sheet=self.opposition,
            opposition_check_type=self.opp_check,
        )
        MissionOptionRouteFactory(
            option=self.contest, outcome_tier=self.success, target_node=self.node_a
        )
        MissionOptionRouteFactory(
            option=self.contest, outcome_tier=self.failure, target_node=self.node_b
        )

    def test_difficulty_is_template_risk_plus_opposition_level_term(self) -> None:
        with mock.patch(_LEVEL, return_value=4), force_check_outcome(self.success) as capture:
            resolve_option(self.instance, self.entry, self.contest, self.actor)
        expected = self.template.risk_tier + level_opposition(
            self.opp_check, level=4, character=self.opposition.character
        )
        self.assertEqual(capture.target_difficulty, expected)
        self.assertEqual(capture.check_type, self.check_type)

    def test_tiers_route_like_check(self) -> None:
        with mock.patch(_LEVEL, return_value=1), force_check_outcome(self.failure):
            deed = resolve_option(self.instance, self.entry, self.contest, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.node_b)
        self.assertEqual(deed.outcome, self.failure)
