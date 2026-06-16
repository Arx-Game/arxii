"""#931 Phase 4 — rescue plumbing: ``grant_rescue_mission`` stamps the captive."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.services.run import grant_rescue_mission


def _graph(name: str):
    """Entry node → one BRANCH option to a terminal second node."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    second = MissionNodeFactory(template=template, key="second")
    MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="PLACEHOLDER find the cell",
        branch_target=second,
    )
    return template


class GrantRescueMissionTests(TestCase):
    def test_stamps_rescue_target_and_contract_holder(self) -> None:
        rescuer = CharacterFactory()
        CharacterSheetFactory(character=rescuer)
        captive = CharacterSheetFactory()

        instance = grant_rescue_mission(_graph("rescue"), rescuer, captive)

        assert instance.rescue_target == captive
        assert instance.participants.filter(
            character=rescuer,
            is_contract_holder=True,
        ).exists()
