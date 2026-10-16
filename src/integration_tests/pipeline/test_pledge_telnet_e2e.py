"""Telnet journey: pledges and sacrifices (#4333 slice 2, walkthrough A steps 1 to 3).

Drives the real commands: ``pledge <being>`` (what a being offers and what earns
favor), ``pledge <being>/<pledge>=<prayer>``, ``sacrifice <item>``, ``pledge`` (the
card) and ``pledge/close``. The closing rite's roll is pinned through
``force_check_outcome``; the rest is the service path the web uses. An onlooker's
telnet session is checked for exactly the room lines.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from commands.tests.message_capture import message_text
from commands.worship import CmdPledge, CmdSacrifice
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.action_points.factories import ActionPointPoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemFacetFactory, ItemInstanceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.services import active_persona_for_sheet
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import BeingResonanceTier, FavorAwardKind, RiteTier
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    PledgeFactory,
    RiteKindFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import DevotionStanding, PatronageValence, PledgeDetails
from world.worship.services import bump_devotion


def _run(command_class, caller, args: str, switches: list[str] | None = None):
    cmd = command_class()
    cmd.caller = caller
    cmd.args = args
    cmd.switches = switches or []
    cmd.raw_string = f"{command_class.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _said(caller) -> str:
    chunks: list[str] = []
    for call in caller.msg.call_args_list:
        chunks.extend(message_text(arg) for arg in call.args if isinstance(arg, (str, tuple)))
    return "\n".join(chunks)


class PledgeTelnetTests(TestCase):
    def setUp(self) -> None:
        outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level)
            for name, level in (
                ("Critical Success", 2),
                ("Success", 1),
                ("Partial Success", 0),
                ("Failure", -1),
                ("Critical Failure", -2),
            )
        }
        self.success = outcomes["Success"]
        config = get_devotion_config()
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.CLOSING, outcome_tier=self.success, amount=5
        )
        for outcome in outcomes.values():
            WorshipRiteTierAwardFactory(tier=RiteTier.DEVOTIONAL, outcome_tier=outcome)

        self.room = ObjectDBFactory(db_key="Shrine", db_typeclass_path="typeclasses.rooms.Room")
        self.profile = RoomProfileFactory(objectdb=self.room)
        self.scene = SceneFactory(location=self.profile, is_active=True)
        self.ysmay = self._pc("Ysmay")
        self.caddoc = self._pc("Caddoc")
        ActionPointPoolFactory(character=self.ysmay.sheet_data, current=10, maximum=10)

        self.ombrin = WorshippedBeingFactory(name="Ombrin")
        BeingResonanceFactory(being=self.ombrin, tier=BeingResonanceTier.FAVORED)
        self.silk = BeingFacetFactory(being=self.ombrin, facet__name="Silk").facet
        rite = WorshipRiteFactory(
            being=self.ombrin,
            kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL),
            name="Ombrin's rite",
        )
        ShrineDetailsFactory(feature_instance__room_profile=self.profile, being=self.ombrin)
        DevotionStandingFactory(
            character_sheet=self.ysmay.sheet_data,
            being=self.ombrin,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        self.pledge = PledgeFactory(
            being=self.ombrin, name="The Silk Watch", favor_target=20, closing_rite=rite
        )

    def _pc(self, name):
        character = CharacterFactory(db_key=name, location=self.room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        SceneParticipationFactory(scene=self.scene, account=tenure.player_data.account)
        return character

    def _onlooker_hears(self, command_class, args: str, switches=None, outcome=None) -> list[str]:
        self.caddoc.msg = MagicMock()
        with (
            patch(
                "world.scenes.interaction_services.non_web_sessions",
                side_effect=lambda obj: ["telnet"] if obj.pk == self.caddoc.pk else [],
            ),
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(outcome or self.success),
        ):
            _run(command_class, self.ysmay, args, switches)
        return [str(call.args[0]) for call in self.caddoc.msg.call_args_list if call.args]

    def test_pledge_journey(self) -> None:
        name = active_persona_for_sheet(self.ysmay.sheet_data).name

        _run(CmdPledge, self.ysmay, "Ombrin")
        out = _said(self.ysmay)
        self.assertIn("The Silk Watch: favor target 20 within 2 game weeks", out)
        self.assertIn("Your earning rate: 200%", out)
        self.assertIn("items with the Silk facet count x2", out)

        _run(CmdPledge, self.ysmay, "Ombrin/The Silk Watch=[player prayer]")
        out = _said(self.ysmay)
        self.assertIn("You pledge yourself to Ombrin: The Silk Watch.", out)
        self.assertIn("Your earning rate with Ombrin: 200% (100% + 100% Chosen).", out)
        details = PledgeDetails.objects.get()

        obj = ObjectDBFactory(db_key="silk scarf", db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = self.ysmay
        obj.save(update_fields=["db_location"])
        item = ItemInstanceFactory(template__name="silk scarf", template__value=20, game_object=obj)
        ItemFacetFactory(item_instance=item, facet=self.silk)
        heard = self._onlooker_hears(CmdSacrifice, "silk scarf")
        self.assertIn(
            "Value 20: 2 base, x2 Silk = 4, at 200% = +8 favor with Ombrin.", _said(self.ysmay)
        )
        self.assertEqual(heard, [f"{name} sacrifices silk scarf at Ombrin's shrine."])

        bump_devotion(self.ysmay.sheet_data, self.ombrin, 5)  # +10: now at the target
        _run(CmdPledge, self.ysmay, "")
        out = _said(self.ysmay)
        self.assertIn("20 of 20 favor since pledging. Ready to close.", out)
        self.assertIn("Sacrificed silk scarf (Silk facet, favored)", out)

        favor_before = DevotionStanding.objects.get(
            character_sheet=self.ysmay.sheet_data, being=self.ombrin
        ).favor
        heard = self._onlooker_hears(CmdPledge, "", switches=["close"])
        self.assertIn(
            "You close your pledge with Ombrin's rite: Success. Closing award for Success: "
            "5 base, at 200% = +10 favor with Ombrin.",
            _said(self.ysmay),
        )
        self.assertEqual(heard, [f"{name} performs Ombrin's rite."])
        favor_after = DevotionStanding.objects.get(
            character_sheet=self.ysmay.sheet_data, being=self.ombrin
        ).favor
        self.assertEqual(favor_after, favor_before + 10)
        self.assertIsNotNone(PledgeDetails.objects.get(pk=details.pk).closing_performance)

    def test_close_before_the_target_is_refused(self) -> None:
        _run(CmdPledge, self.ysmay, "Ombrin/The Silk Watch")
        _run(CmdPledge, self.ysmay, "", switches=["close"])
        self.assertIn("has not reached its favor target", _said(self.ysmay))

    def test_sacrifice_away_from_a_holy_site(self) -> None:
        road = ObjectDBFactory(db_key="Road", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=road)
        self.ysmay.db_location = road
        self.ysmay.save(update_fields=["db_location"])
        obj = ObjectDBFactory(db_key="coin", db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = self.ysmay
        obj.save(update_fields=["db_location"])
        ItemInstanceFactory(template__name="coin", game_object=obj)

        _run(CmdSacrifice, self.ysmay, "coin")

        self.assertIn("There is no shrine or temple here to sacrifice at.", _said(self.ysmay))
