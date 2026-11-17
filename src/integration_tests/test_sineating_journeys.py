"""Journeys through Sineating as a ritual: a plea by pose, the ritual by pose (#5177).

Ysmay is a Sinner carrying Ruin (Abyssal) corruption; Corvin is her Sineater; Hobb is the
other player in the room and sees only the poses. Marrow is an NPC Sineater run by Gideon, a
GM, with no player tenure of his own.

Everything the numbers depend on is staff-set and built by the setup: 60 corruption and 5
resonance per unit (the starting values), a full share (1.00) for a success and a quarter for
a failure, and no resistance yet. Expected numbers are worked out by hand from Trace 1 of the
spec, not read from the code:

* Ysmay carries 260 Ruin (stage 2). Two units move 2 x 60 = 120, so she drops to 140.
* Corvin has no resistance, so all 120 arrive and his Mire from her reads 120.
* The Hollow refills by the 2 units.
* At a full share each earns 2 x 5 x 1.00 = 10, in the resonance of their own thread: Ysmay
  in Ruin (her thread's), Corvin in Primal (his).

The roll is the one thing a journey cannot play for: ``force_check_outcome`` pins its tier.
"""

from __future__ import annotations

from decimal import Decimal
import uuid

from django.test import override_settings
from rest_framework import status

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    SineatingOutcomeAwardFactory,
    ThreadWeavingUnlockFactory,
    ensure_conversion_pairs,
    set_aura_split,
    wire_soul_tether_content,
    with_corruption_at_stage,
)
from world.magic.models import Affinity, AffinityInteraction, CharacterAura, MireHolding, Thread
from world.magic.models.aura import CharacterResonance
from world.magic.models.soul_tether import Sineating, SineatingPendingOffer
from world.magic.services.soul_tether import accept_soul_tether, get_soul_tether_config
from world.magic.types.soul_tether import SoulTetherRole
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTypeFactory
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.scenes.models import Interaction
from world.seeds.modifier_values import seed_pool_and_cap_lanes
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

SUBMIT_POSE = "/api/interactions/submit-pose/"
OPTIONS = "/api/magic/sineating-options/"
ENTREAT = "kneels and offers up the weight of it."
PERFORM = "lays a hand on the offered weight and takes it."
SHARES = {
    "Critical Success": "1.50",
    "Success": "1.00",
    "Partial Success": "0.50",
    "Failure": "0.25",
    "Critical Failure": "0.00",
}


def corruption(character, resonance) -> int:
    row = CharacterResonance.objects.filter(
        character_sheet=character.sheet_data, resonance=resonance
    ).first()
    return row.corruption_current if row is not None else 0


def balance(character, resonance) -> int:
    row = CharacterResonance.objects.filter(
        character_sheet=character.sheet_data, resonance=resonance
    ).first()
    return row.balance if row is not None else 0


@override_settings(SEED_SAMPLE_CONTENT=True)
class SineatingJourneyCase(JourneyCase):
    """The Lantern with a live scene, a Sinner, a Sineater, a bystander and a GM's NPC."""

    def setUp(self) -> None:
        super().setUp()
        seed_pool_and_cap_lanes()
        wire_soul_tether_content()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.celestial, self.primal_affinity, self.abyssal = ensure_conversion_pairs()
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.primal = ResonanceFactory(name="Tide", affinity=self.primal_affinity)

        self.lantern = self.make_room("The Lantern")
        self.scene = SceneFactory(
            location=RoomProfileFactory(objectdb=self.lantern), is_active=True
        )
        invalidate_active_scene_cache(self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.corvin = self.make_player("Corvin", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.gideon = self.make_player("Gideon", room=self.lantern)
        for who in (self.ysmay, self.corvin, self.hobb):
            self.watch(who)
            self.connect_telnet(who)

        self.aura(self.ysmay, abyssal="80")
        self.aura(self.corvin, primal="80")
        CharacterResonanceFactory(character_sheet=self.ysmay.sheet_data, resonance=self.ruin)
        CharacterResonanceFactory(character_sheet=self.corvin.sheet_data, resonance=self.primal)
        self.tether(self.ysmay, self.corvin)
        with_corruption_at_stage(self.ysmay.sheet_data, self.ruin, stage=2)
        row = CharacterResonance.objects.get(
            character_sheet=self.ysmay.sheet_data, resonance=self.ruin
        )
        row.corruption_current = 260
        row.save(update_fields=["corruption_current"])

        config = get_soul_tether_config()
        config.sineating_check_type = CheckTypeFactory()
        config.sineating_difficulty_level = 0
        config.save()
        self.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        for name, share in SHARES.items():
            SineatingOutcomeAwardFactory(
                outcome_tier=self.outcomes[name], earned_share=Decimal(share)
            )
        self.ysmay_web = self.api(self.account_of(self.ysmay))
        self.corvin_web = self.api(self.account_of(self.corvin))

    # -- building ---------------------------------------------------------------

    @staticmethod
    def aura(character, *, celestial="10", primal="10", abyssal="10") -> None:
        sheet = character.sheet_data
        set_aura_split(
            CharacterAura.objects.filter(character=sheet).first()
            or CharacterAuraFactory(character=sheet),
            celestial=celestial,
            primal=primal,
            abyssal=abyssal,
        )

    def tether(self, sinner, sineater) -> None:
        """Bind ``sinner`` to ``sineater`` and give the Sinner's thread a Hollow that holds 30."""
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_type=RelationshipTypeFactory(),
            unlock_trait=None,
        )
        CharacterThreadWeavingUnlockFactory(character=sinner.sheet_data, unlock=unlock)
        CharacterRelationshipFactory(source=sinner.sheet_data, target=sineater.sheet_data)
        CharacterRelationshipFactory(source=sineater.sheet_data, target=sinner.sheet_data)
        accept_soul_tether(
            initiator_sheet=sinner.sheet_data,
            partner_sheet=sineater.sheet_data,
            sinner_role=SoulTetherRole.SINNER,
            resonance=self.ruin,
            ritual_components=[],
            sineater_resonance=self.primal,
        )
        thread = Thread.objects.get(
            owner=sinner.sheet_data,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone__relationship__target=sineater.sheet_data,
            retired_at__isnull=True,
        )
        thread.level = 30
        thread.save(update_fields=["level"])

    def hollow(self) -> int:
        return Thread.objects.get(
            owner=self.ysmay.sheet_data,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone__relationship__target=self.corvin.sheet_data,
            retired_at__isnull=True,
        ).hollow_current

    def entreat(self, sineater_name: str = "Corvin", units: int = 2) -> str:
        return self.telnet(self.ysmay, f"pose/entreat {sineater_name}={units} {ENTREAT}")

    def perform(self, character, sinner_name: str = "Ysmay", units: int = 2, tier="Success"):
        with force_check_outcome(self.outcomes[tier]):
            return self.telnet(character, f"pose/sineat {sinner_name}={units} {PERFORM}")

    def telnet(self, character, line: str) -> str:
        """A typed line, with the after-commit sends it causes run: a Sinner's notices are
        stored narrative messages sent once the transaction commits (#5177)."""
        with self.captureOnCommitCallbacks(execute=True):
            return super().telnet(character, line)

    def web_pose(self, client, character, content: str, **fields):
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(
                SUBMIT_POSE,
                {
                    "persona_id": character.sheet_data.primary_persona.pk,
                    "content": content,
                    "client_request_id": str(uuid.uuid4()),
                    **fields,
                },
                format="json",
            )


class ASineatingByTelnet(SineatingJourneyCase):
    def test_a_plea_then_the_ritual_moves_the_corruption_and_pays_each_their_own_thread(
        self,
    ) -> None:
        told = self.entreat()

        self.assertIn("You entreat Corvin to take on your sins. 2 are offered.", told)
        self.assertTold(self.corvin, "Ysmay asks you to take on their sins (2 offered).")
        self.assertTold(self.corvin, "Answer with a pose.")
        plea = SineatingPendingOffer.objects.get()
        self.assertEqual((plea.units_offered, plea.resonance), (2, self.ruin))
        # Nothing has moved yet.
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)
        pleas = self.telnet(self.corvin, "sineater pleas")
        self.assertIn("Ysmay - 2 sins in Ruin", pleas)

        told = self.perform(self.corvin)

        self.assertIn("You take 120 of Ysmay's corruption into the Mire.", told)
        self.assertIn("Your Tide grows by 10.", told)
        self.assertTold(self.ysmay, "Corvin takes on your sins")
        self.assertTold(self.ysmay, "your corruption in Ruin falls by 120")
        self.assertTold(self.ysmay, "Your Ruin grows by 10.")
        self.assertEqual(corruption(self.ysmay, self.ruin), 140)
        self.assertEqual(corruption(self.corvin, self.ruin), 120)
        self.assertEqual(MireHolding.objects.get().amount, 120)
        self.assertEqual(self.hollow(), 2)
        self.assertEqual(balance(self.ysmay, self.ruin), 10)
        self.assertEqual(balance(self.corvin, self.primal), 10)
        audit = Sineating.objects.get()
        self.assertEqual(
            (audit.units_accepted, audit.corruption_moved, audit.corruption_taken, audit.outcome),
            (2, 120, 120, self.outcomes["Success"]),
        )
        self.assertFalse(SineatingPendingOffer.objects.exists())
        carried = self.telnet(self.corvin, "sineater pleas")
        self.assertIn("You carry:", carried)
        self.assertIn("120 of Ysmay's corruption in Ruin", carried)

        # Hobb, standing there, read both poses and nothing of what they did.
        self.assertTold(self.hobb, ENTREAT)
        self.assertTold(self.hobb, PERFORM)
        for private in ("asks you to take on", "takes on your sins", "into the Mire", "grows by"):
            self.assertNotTold(self.hobb, private)

    def test_a_failed_roll_moves_the_same_corruption_but_pays_a_quarter(self) -> None:
        self.entreat()

        self.perform(self.corvin, tier="Failure")

        self.assertEqual(corruption(self.ysmay, self.ruin), 140)
        self.assertEqual(corruption(self.corvin, self.ruin), 120)
        self.assertEqual(balance(self.ysmay, self.ruin), 2)
        self.assertEqual(balance(self.corvin, self.primal), 2)

    def test_a_pose_that_cannot_carry_its_sineating_is_never_posted(self) -> None:
        told = self.perform(self.corvin)  # no plea is waiting

        self.assertIn("No pending Sineating offer found.", told)
        self.assertNotTold(self.hobb, PERFORM)
        self.assertFalse(Interaction.objects.filter(content__contains=PERFORM).exists())
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)

    def test_a_pair_cannot_perform_twice_in_one_scene(self) -> None:
        self.entreat()
        self.perform(self.corvin)

        told = self.entreat()

        self.assertIn("You have already performed Sineating with Corvin in this scene.", told)
        self.assertEqual(Sineating.objects.count(), 1)

    def test_a_fallen_sineater_carries_no_one(self) -> None:
        self.aura(self.corvin, celestial="5", primal="5", abyssal="90")

        told = self.entreat()

        self.assertIn("Corvin has fallen too far into the Abyss to carry anyone's sins.", told)
        self.assertFalse(SineatingPendingOffer.objects.exists())

    def test_an_unset_up_ritual_refuses_and_the_pose_is_not_posted(self) -> None:
        self.entreat()
        config = get_soul_tether_config()
        config.sineating_check_type = None
        config.save()

        told = self.perform(self.corvin)

        self.assertIn("Sineating has not been set up yet.", told)
        self.assertNotTold(self.hobb, PERFORM)
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)
        self.assertTrue(SineatingPendingOffer.objects.exists())

    def test_a_sineater_can_turn_a_plea_down(self) -> None:
        self.entreat()

        told = self.telnet(self.corvin, "sineater decline Ysmay")

        self.assertIn("You decline Ysmay's plea.", told)
        self.assertFalse(SineatingPendingOffer.objects.exists())
        self.assertEqual(Sineating.objects.get().units_accepted, 0)
        self.assertEqual(corruption(self.ysmay, self.ruin), 260)


class ASineatingByTheWeb(SineatingJourneyCase):
    def test_the_same_plea_and_ritual_through_the_pose_endpoint(self) -> None:
        listed = self.ysmay_web.get(OPTIONS, {"character_sheet": self.ysmay.sheet_data.pk})
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.content)
        (option,) = listed.json()["results"]
        self.assertEqual(
            (option["role"], option["partner_sheet_id"], option["partner_name"]),
            ("entreat", self.corvin.sheet_data.pk, "Corvin"),
        )

        with self.captureOnCommitCallbacks(execute=True):
            entreated = self.web_pose(
                self.ysmay_web,
                self.ysmay,
                ENTREAT,
                sineating_role="entreat",
                sineating_partner_id=self.corvin.sheet_data.pk,
                sineating_units=2,
            )
        self.assertEqual(entreated.status_code, status.HTTP_201_CREATED, entreated.content)
        self.assertTrue(entreated.json()["sineating_recorded"])
        self.assertIn("You entreat Corvin", entreated.json()["sineating_line"])
        self.assertTold(self.corvin, "Ysmay asks you to take on their sins (2 offered).")

        waiting = self.corvin_web.get(OPTIONS, {"character_sheet": self.corvin.sheet_data.pk})
        (answer,) = waiting.json()["results"]
        self.assertEqual(
            (answer["role"], answer["partner_sheet_id"], answer["max_units"]),
            ("perform", self.ysmay.sheet_data.pk, 2),
        )

        with (
            force_check_outcome(self.outcomes["Success"]),
            self.captureOnCommitCallbacks(execute=True),
        ):
            performed = self.web_pose(
                self.corvin_web,
                self.corvin,
                PERFORM,
                sineating_role="perform",
                sineating_partner_id=self.ysmay.sheet_data.pk,
                sineating_units=2,
            )
        self.assertEqual(performed.status_code, status.HTTP_201_CREATED, performed.content)
        self.assertTrue(performed.json()["sineating_recorded"])
        self.assertIn("You take 120 of Ysmay's corruption", performed.json()["sineating_line"])
        self.assertEqual(corruption(self.ysmay, self.ruin), 140)
        self.assertEqual(corruption(self.corvin, self.ruin), 120)
        self.assertEqual(MireHolding.objects.get().amount, 120)
        self.assertEqual(self.hollow(), 2)
        self.assertEqual(balance(self.ysmay, self.ruin), 10)
        self.assertEqual(balance(self.corvin, self.primal), 10)
        self.assertTold(self.ysmay, "your corruption in Ruin falls by 120")
        # The others present read the poses and none of what they did.
        self.assertShownRow(self.hobb, PERFORM)
        for private in ("asks you to take on", "takes on your sins", "into the Mire"):
            self.assertNotTold(self.hobb, private)
            self.assertNotIn(private, " ".join(self.mailbox(self.hobb).rows))

    def test_a_refused_ritual_posts_no_pose(self) -> None:
        refused = self.web_pose(
            self.corvin_web,
            self.corvin,
            PERFORM,
            sineating_role="perform",
            sineating_partner_id=self.ysmay.sheet_data.pk,
            sineating_units=2,
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertEqual(refused.json()["detail"], "No pending Sineating offer found.")
        self.assertFalse(Interaction.objects.filter(content=PERFORM).exists())

    def test_a_pose_cannot_carry_a_reflection_and_a_sineating(self) -> None:
        refused = self.web_pose(
            self.ysmay_web,
            self.ysmay,
            ENTREAT,
            sineating_role="entreat",
            sineating_partner_id=self.corvin.sheet_data.pk,
            sineating_units=2,
            reflect_choice="EMBRACE",
            reflect_resonance_id=self.ruin.pk,
        )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertFalse(SineatingPendingOffer.objects.exists())


class AnNpcSineaterAGmRuns(SineatingJourneyCase):
    def setUp(self) -> None:
        super().setUp()
        # Marrow is an NPC: a character and a sheet, no roster entry and no tenure. Gideon, a
        # GM, puppets him from his own account.
        self.marrow = CharacterFactory(db_key="Marrow", location=self.lantern)
        CharacterSheetFactory(character=self.marrow)
        self.marrow.db_account = self.account_of(self.gideon)
        self.marrow.save()
        self.watch(self.marrow)
        self.aura(self.marrow, primal="80")
        CharacterResonanceFactory(character_sheet=self.marrow.sheet_data, resonance=self.primal)
        self.tether(self.ysmay, self.marrow)

    def test_the_gm_performs_for_the_npc_and_the_player_earns_as_with_any_sineater(self) -> None:
        self.entreat("Marrow")
        self.assertTold(self.marrow, "Ysmay asks you to take on their sins (2 offered).")

        told = self.perform(self.marrow)

        self.assertIn("You take 120 of Ysmay's corruption into the Mire.", told)
        self.assertEqual(corruption(self.ysmay, self.ruin), 140)
        self.assertEqual(corruption(self.marrow, self.ruin), 120)
        self.assertEqual(balance(self.ysmay, self.ruin), 10)
        self.assertEqual(balance(self.marrow, self.primal), 10)
