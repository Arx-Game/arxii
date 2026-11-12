"""Accepting a pact at a pledge's closing rite (#4341, spec section 7 steps 1 and 2).

Corwen holds a pledge to Hesk whose favor target is met; the pledge carries Hesk's
pact offer. She reads it on her pledge (telnet and the card API) and closes through
telnet ``pledge/close[/accept]`` or the web's ``pledge_close`` dispatch. The rite's
roll is pinned through ``force_check_outcome``.

Journeys run on the parity tier (``JourneyCase`` is PostgreSQL-only, and signing
applies a staged condition through DISTINCT ON). The paths that sign nothing are
also covered on SQLite in ``world.worship.tests.test_pledges.AcceptPactAtCloseTests``.
"""

from __future__ import annotations

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.factories import ActionPointPoolFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.pacts.constants import CharacterPactCommitmentKind
from world.pacts.factories import (
    PactOfferCommitmentFactory,
    PactOfferFactory,
    make_pact_condition,
)
from world.pacts.models import CharacterPact
from world.projects.constants import ProjectStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import FavorAwardKind, RiteTier
from world.worship.factories import (
    FavorOutcomeAwardFactory,
    PledgeFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import PledgeDetails
from world.worship.pledge_services import take_pledge

_OUTCOMES = (
    ("Critical Success", 2),
    ("Success", 1),
    ("Partial Success", 0),
    ("Failure", -1),
    ("Critical Failure", -2),
)


class AcceptAtCloseBase(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        config = get_devotion_config()
        FavorOutcomeAwardFactory(
            config=config,
            kind=FavorAwardKind.CLOSING,
            outcome_tier=self.outcomes["Success"],
            amount=5,
        )
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        for outcome in self.outcomes.values():
            WorshipRiteTierAwardFactory(tier=RiteTier.DEVOTIONAL, outcome_tier=outcome)

        self.room = self.make_room("Hollow")
        profile = RoomProfileFactory(objectdb=self.room)
        self.corwen = self.make_player("Corwen", room=self.room)
        self.sheet = self.corwen.sheet_data
        scene = SceneFactory(location=profile, is_active=True)
        SceneParticipationFactory(scene=scene, account=self.account_of(self.corwen))
        ActionPointPoolFactory(character=self.sheet, current=10, maximum=10)

        self.hesk = WorshippedBeingFactory(name="Hesk")
        rite = WorshipRiteFactory(
            being=self.hesk,
            kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL),
            name="Hesk's rite",
        )
        self.offer = PactOfferFactory(
            being=self.hesk,
            name="Hesk pact",
            offer_text="[offer text]",
            condition=make_pact_condition(),
        )
        PactOfferCommitmentFactory(offer=self.offer, amount=8)
        PactOfferCommitmentFactory(
            offer=self.offer, kind=CharacterPactCommitmentKind.CUSTOM, amount=0, notes="[promise]"
        )
        self.pledge = PledgeFactory(
            being=self.hesk,
            name="The Ash Vow",
            favor_target=12,
            closing_rite=rite,
            pact_offer=self.offer,
        )
        self.details = take_pledge(self.sheet, self.pledge)
        self.details.project.current_progress = 12
        self.details.project.save(update_fields=["current_progress"])

    def _status(self) -> str:
        return PledgeDetails.objects.get(pk=self.details.pk).project.status

    def _close_by_telnet(self, line: str, outcome: str) -> str:
        with force_check_outcome(self.outcomes[outcome]):
            return self.telnet(self.corwen, line)

    def _close_by_web(self, outcome: str, **kwargs):
        with force_check_outcome(self.outcomes[outcome]):
            return self.web(self.corwen, "pledge_close", **kwargs)


class ReadingTheOfferTests(AcceptAtCloseBase):
    def test_telnet_pledge_shows_the_offer_and_its_stages(self) -> None:
        own = self.telnet(self.corwen, "pledge")
        offered = self.telnet(self.corwen, "pledge Hesk")

        for out in (own, offered):
            self.assertIn("Offered at the close: a pact with Hesk.", out)
            self.assertIn("[offer text]", out)
            self.assertIn("You commit to: earn 8 favor with Hesk every 2 game weeks.", out)
            self.assertIn("Promise (not checked by the game): [promise]", out)
            self.assertIn("1. Sworn", out)
            self.assertIn("4. Breached: the pact ends, if its resist check fails", out)
        self.assertIn("pledge/close/accept", own)


class AcceptingThePactTests(AcceptAtCloseBase):
    def test_accepting_at_success_signs_the_pact(self) -> None:
        result = self._close_by_web("Success", accept_pact=True)

        self.assertTrue(result.success, result.message)
        self.assertTrue(result.data["pact_signed"])
        self.assertIn("Hesk is now your patron. Your pact begins.", result.message)
        pact = CharacterPact.objects.get(character_sheet=self.sheet)
        self.assertEqual(pact.offer, self.offer)
        self.assertIsNone(pact.dissolved_at)
        self.assertEqual(self._status(), ProjectStatus.COMPLETED)

    def test_accepting_on_the_retry_signs_the_pact(self) -> None:
        self._close_by_telnet("pledge/close/accept", "Failure")

        out = self._close_by_telnet("pledge/close/accept", "Success")

        self.assertIn("Hesk is now your patron. Your pact begins.", out)
        self.assertTrue(CharacterPact.objects.filter(character_sheet=self.sheet).exists())
