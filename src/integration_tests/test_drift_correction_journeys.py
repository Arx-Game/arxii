"""Journeys through drift correction (#4733, slice 4 of #4672).

A deed grows a resonance of the character's own affinity while she carries resonance that
does not fit her; the game offers a chance to correct that drift for the length of the
scene. Ysmay is a Celestial character holding Ruin (Abyssal) drift; Marrow is staff and
tags her moments; Hobb is the other player on the account side.

Everything the rate depends on is the SEEDED pair rows (``seed_canonical_affinities`` and
``_seed_affinity_interactions``): Abyssal -> Celestial is Redemption at 0.5, Celestial ->
Abyssal is Fall at 1.50. Only the characters, scene, resonances, the rite, the check type
and the per-tier outcome shares are built by factories. Expected numbers are worked out by
hand in each journey, from those rows and the authored cap of 50 percent per deed:

* A Dawnlight deed of 20 raises the cap toward Dawnlight by 50% of 20 = 10.
* Converting N Ruin at a full share yields int(N x 0.5) Dawnlight (Redemption), and
  int(N x 1.50) at the Fall rate.

The check is the one thing a journey cannot play for: ``force_check_outcome`` pins the tier
the roll lands on, so the share (authored per tier) is the only thing left to decide.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import override_settings
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.admin import grant_resonance_action
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    DriftCorrectionRiteFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterResonance,
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionOutcomeShare,
    Resonance,
    ResonanceGrant,
)
from world.magic.services.drift import get_drift_correction_config
from world.magic.services.resonance import grant_resonance
from world.scenes.factories import SceneFactory, SceneOwnerParticipationFactory
from world.scenes.interaction_services import get_active_scene, invalidate_active_scene_cache
from world.scenes.models import Scene
from world.seeds.game_content.magic import _seed_affinity_interactions, seed_canonical_affinities
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

NO_OFFER = "You have no open chance to correct drift."
NOTICE = "You carry resonance that does not fit you. Use drift to see what you can correct."
LAPSE = "The chance to correct drift passes with the scene."
PENDING = "/api/magic/drift-correction/pending/"
CONVERT = "/api/magic/drift-correction/convert/"
DECLINE = "/api/magic/drift-correction/decline/"


def balance(character, resonance: Resonance) -> int:
    """The resonance balance the database holds for ``character`` (0 when none)."""
    return (
        CharacterResonance.objects.filter(character_sheet=character.sheet_data, resonance=resonance)
        .values_list("balance", flat=True)
        .first()
        or 0
    )


def consumed(pk: int) -> bool:
    """Whether the offered item is used up. Takes the pk: a delete clears ``item.pk``."""
    row = ItemInstance.objects.filter(pk=pk).values("destroyed_at", "quantity").first()
    return row is None or row["destroyed_at"] is not None or row["quantity"] <= 0


def post(client, url: str, data: dict):
    """POST ``data`` as the JSON body the dialog sends."""
    return client.post(url, data, format="json")


def drift_grants() -> list[ResonanceGrant]:
    return list(ResonanceGrant.objects.filter(source=GainSource.DRIFT_CORRECTION))


@override_settings(SEED_SAMPLE_CONTENT=True)
class DriftJourneyCase(JourneyCase):
    """The Lantern, a live scene, the seeded affinities and the authored rite.

    ``self.ysmay`` is Celestial: 500 lifetime Dawnlight (balance 0, so a deed's gain is
    all there is to read back), 30 Ruin (Abyssal) drift, an aura of 80/10/10.
    """

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        seed_canonical_affinities()
        _seed_affinity_interactions()
        AffinityInteraction.objects.clear_cache()
        self.celestial = Affinity.objects.get(name="Celestial")
        self.abyssal = Affinity.objects.get(name="Abyssal")
        self.dawnlight = ResonanceFactory(name="Dawnlight", affinity=self.celestial)
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)

        self.lantern = self.make_room("The Lantern")
        self.scene = SceneFactory(
            location=RoomProfileFactory(objectdb=self.lantern), is_active=True
        )
        invalidate_active_scene_cache(self.lantern)
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.marrow = self.make_player("Marrow", room=self.lantern)
        account = self.account_of(self.marrow)
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        account.permissions.add("Admin")

        self.hold(self.ysmay, self.dawnlight, 0, lifetime=500)
        self.hold(self.ysmay, self.ruin, 30)
        set_aura_split(
            CharacterAuraFactory(character=self.ysmay.sheet_data),
            celestial="80",
            primal="10",
            abyssal="10",
        )
        self.dawn_flourish = DramaticMomentTypeFactory(
            label="Dawn Flourish", resonance=self.dawnlight, per_scene_cap=3, resonance_amount=20
        )

        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty = 0
        config.cap_percent = 50
        config.save()
        self.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        self.set_shares(**dict.fromkeys(CANONICAL_OUTCOME_LEVELS, "1.00"))

    # -- building ---------------------------------------------------------------

    @staticmethod
    def hold(character, resonance: Resonance, held: int, *, lifetime: int | None = None) -> None:
        CharacterResonance.objects.create(
            character_sheet=character.sheet_data,
            resonance=resonance,
            balance=held,
            lifetime_earned=held if lifetime is None else lifetime,
        )

    @staticmethod
    def set_shares(**shares: str) -> None:
        for name, share in shares.items():
            DriftCorrectionOutcomeShare.objects.update_or_create(
                outcome_tier=ensure_canonical_check_outcome(name),
                defaults={"converted_share": Decimal(share)},
            )

    @staticmethod
    def carry(character, resonance: Resonance, name: str) -> int:
        """Put an item tied to ``resonance`` in ``character``'s hands; return its pk."""
        template = ItemTemplateFactory(
            name=name, tied_resonance=resonance, resonance_tier=ResonanceTierFactory()
        )
        item = ItemInstanceFactory(template=template, holder_character_sheet=character.sheet_data)
        materialize_item_game_object(item, character.sheet_data)
        return item.pk

    def deed(self, character, moment: str = "Dawn Flourish") -> str:
        """Marrow tags ``character``'s moment, committing the way a request does."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.telnet(self.marrow, f"moment tag {character.key}={moment}")

    def offer_of(self, character) -> DriftConversionOffer | None:
        return DriftConversionOffer.objects.filter(character_sheet=character.sheet_data).first()

    def cap_toward(self, character, resonance: Resonance) -> int | None:
        return (
            DriftConversionCap.objects.filter(
                offer__character_sheet=character.sheet_data, target_resonance=resonance
            )
            .values_list("cap", flat=True)
            .first()
        )


class CorrectingDriftAtTheKeyboard(DriftJourneyCase):
    """Ysmay is granted her own resonance twice, then converts her Ruin into Dawnlight."""

    def test_two_deeds_raise_the_cap_and_a_conversion_runs_at_the_seeded_rate(self) -> None:
        self.connect_telnet(self.ysmay)
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")

        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))
        self.assertIsNone(self.offer_of(self.ysmay))

        # First deed: 20 Dawnlight granted; the cap is 50% of 20 = 10.
        told = self.deed(self.ysmay)
        self.assertIn("You tagged Ysmay with 'Dawn Flourish'. 20 Dawnlight and renown", told)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))

        shown = strip_ansi(self.telnet(self.ysmay, "drift"))
        self.assertIn("You may correct drift.", shown)
        self.assertIn("Toward Dawnlight: up to 10.", shown)
        # Ruin is Abyssal, Dawnlight Celestial: the seeded Redemption pair at 0.5, so the
        # whole cap (10) would give 5. She holds all 30 Ruin.
        self.assertIn("From Ruin: you hold 30, REDEMPTION at 0.5", shown)
        self.assertIn("Converting 10 would give 5.", shown)
        self.assertIn("Offering you carry: Dawn-gold Thread (material).", shown)

        # A second deed in the same scene raises the cap to 10 + 10, and tells her nothing
        # new (the offer was already open).
        before = len(self.mailbox(self.ysmay).lines)
        self.deed(self.ysmay)
        self.assertNotIn(NOTICE, strip_ansi("\n".join(self.mailbox(self.ysmay).lines[before:])))
        self.assertEqual(DriftConversionOffer.objects.filter(scene=self.scene).count(), 1)
        shown = strip_ansi(self.telnet(self.ysmay, "drift"))
        self.assertIn("Toward Dawnlight: up to 20.", shown)
        self.assertIn("Converting 20 would give 10.", shown)

        # Convert 12 Ruin at a full share: 12 x 0.5 = 6 Dawnlight.
        with force_check_outcome(self.outcomes["Success"]):
            told = self.telnet(self.ysmay, "drift convert Ruin=Dawnlight 12")
        self.assertIn("12 Ruin became 6 Dawnlight.", told)
        self.assertEqual(balance(self.ysmay, self.ruin), 30 - 12)
        # 20 + 20 from the two deeds, +6 from the rite.
        self.assertEqual(balance(self.ysmay, self.dawnlight), 46)
        (grant,) = drift_grants()
        self.assertEqual((grant.resonance, grant.amount), (self.dawnlight, 6))
        self.assertTrue(consumed(thread))
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 20 - 12)

        # What is left: 8 of cap, 18 Ruin, 8 x 0.5 = 4, and nothing to offer.
        shown = strip_ansi(self.telnet(self.ysmay, "drift"))
        self.assertIn("Toward Dawnlight: up to 8.", shown)
        self.assertIn("From Ruin: you hold 18", shown)
        self.assertIn("Converting 8 would give 4.", shown)
        self.assertIn("You carry nothing that counts as the offering.", shown)

    def test_naming_no_amount_converts_the_most_she_may(self) -> None:
        self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        with force_check_outcome(self.outcomes["Success"]):
            told = self.telnet(self.ysmay, "drift convert Ruin=Dawnlight")
        # Cap 10, 30 Ruin held: 10 Ruin -> int(10 x 0.5) = 5 Dawnlight; the cap is spent,
        # so the offer is gone.
        self.assertIn("10 Ruin became 5 Dawnlight.", told)
        self.assertEqual(balance(self.ysmay, self.ruin), 20)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 25)
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))

    def test_an_offering_that_does_not_count_is_refused_and_nothing_moves(self) -> None:
        other = ResonanceFactory(name="Sunrise", affinity=self.celestial)
        stranger = self.carry(self.ysmay, other, "Sunrise Candle")
        self.deed(self.ysmay)
        with force_check_outcome(self.outcomes["Success"]):
            told = self.telnet(self.ysmay, "drift convert Ruin=Dawnlight 10")
        self.assertIn(
            "Ritual 'Rite of Drift Correction' requires 1x offering for Dawnlight "
            "that you don't have.",
            told,
        )
        self.assertFalse(consumed(stranger))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertEqual(drift_grants(), [])
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)


class LettingTheChancePassOrFailingTheRite(DriftJourneyCase):
    def test_declining_changes_nothing_but_the_offer(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        told = self.telnet(self.ysmay, "drift decline")
        self.assertIn("You let the chance to correct drift pass.", told)
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertFalse(consumed(thread))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertEqual(drift_grants(), [])
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift decline"))

    def test_a_failed_roll_costs_the_offering_and_moves_nothing(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(Failure="0.00")
        self.deed(self.ysmay)
        with force_check_outcome(self.outcomes["Failure"]):
            told = self.telnet(self.ysmay, "drift convert Ruin=Dawnlight 10")
        self.assertIn("The rite fails; nothing is converted.", told)
        self.assertTrue(consumed(thread))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertEqual(drift_grants(), [])
        # The chance itself stays: the cap is whole and she may try again.
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)
        self.assertIn("Toward Dawnlight: up to 10.", self.telnet(self.ysmay, "drift"))

    def test_a_half_share_converts_half_and_keeps_the_rest_of_the_cap(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(Success="0.50")
        self.deed(self.ysmay)
        with force_check_outcome(self.outcomes["Success"]):
            told = self.telnet(self.ysmay, "drift convert Ruin=Dawnlight 10")
        # Half of 10 is 5 Ruin, which is 5 x 0.5 = 2 Dawnlight (floored); the cap falls by 5.
        self.assertIn("5 Ruin became 2 Dawnlight.", told)
        self.assertTrue(consumed(thread))
        self.assertEqual(balance(self.ysmay, self.ruin), 25)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 22)
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 5)


class TheSameChanceOnTheWeb(DriftJourneyCase):
    """The pending inbox, convert and decline, as the browser dialog calls them."""

    def test_the_inbox_shows_what_telnet_showed_and_convert_runs_the_same_rite(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        hobbs = self.carry(self.hobb, self.dawnlight, "Hobb's Dawn Thread")
        self.deed(self.ysmay)
        shown = strip_ansi(self.telnet(self.ysmay, "drift"))
        self.assertIn("Toward Dawnlight: up to 10.", shown)
        self.assertIn("Converting 10 would give 5.", shown)

        ysmay_api = self.api(self.account_of(self.ysmay))
        response = ysmay_api.get(PENDING)
        self.assertEqual(response.status_code, 200)
        (offer,) = response.data["results"]
        self.assertEqual(offer["scene_id"], self.scene.pk)
        (cap,) = offer["caps"]
        self.assertEqual(cap["target_resonance"]["name"], "Dawnlight")
        self.assertEqual(cap["target_resonance"]["affinity"], "Celestial")
        self.assertEqual(cap["cap_remaining"], 10)
        self.assertEqual(cap["focus_bonus"], 0)
        (source,) = cap["sources"]
        self.assertEqual(source["resonance_name"], "Ruin")
        self.assertEqual(
            (source["balance"], source["max_amount"], source["projected_output"]), (30, 10, 5)
        )
        self.assertEqual(Decimal(source["multiplier"]), Decimal("0.5"))
        self.assertEqual(source["conversion_type"], "REDEMPTION")
        (offering,) = cap["qualifying_components"]
        self.assertEqual(
            (offering["item_id"], offering["name"], offering["mode"]),
            (mine, "Dawn-gold Thread", "material"),
        )

        body = {
            "offer_id": offer["id"],
            "source_resonance_id": self.ruin.pk,
            "target_resonance_id": self.dawnlight.pk,
            "amount": 10,
        }

        # Her own offer, offering an item she does not hold or one that does not exist.
        with force_check_outcome(self.outcomes["Success"]):
            foreign = post(ysmay_api, CONVERT, {**body, "component_ids": [hobbs]})
            missing = post(ysmay_api, CONVERT, {**body, "component_ids": [mine + 9999]})
        for refused in (foreign, missing):
            self.assertEqual(refused.status_code, 400)
            self.assertIn("You are not carrying everything you offered.", str(refused.data))
        self.assertFalse(consumed(mine))
        self.assertFalse(consumed(hobbs))

        # The honest request: 10 Ruin at 0.5 is 5 Dawnlight.
        with force_check_outcome(self.outcomes["Success"]):
            done = post(ysmay_api, CONVERT, {**body, "component_ids": [mine]})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["converted_amount"], 10)
        self.assertEqual(done.data["granted_amount"], 5)
        self.assertEqual(done.data["outcome_name"], "Success")
        self.assertEqual(done.data["conversion_type"], "REDEMPTION")
        self.assertEqual(balance(self.ysmay, self.ruin), 20)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 25)
        self.assertTrue(consumed(mine))
        self.assertFalse(consumed(hobbs))
        (grant,) = drift_grants()
        self.assertEqual((grant.resonance, grant.amount), (self.dawnlight, 5))
        # The cap was spent, so the inbox is empty and telnet agrees.
        self.assertEqual(ysmay_api.get(PENDING).data["results"], [])
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))

    def test_another_account_neither_sees_nor_acts_on_her_offer(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        hobbs = self.carry(self.hobb, self.dawnlight, "Hobb's Dawn Thread")
        self.deed(self.ysmay)
        offer_id = self.offer_of(self.ysmay).pk
        body = {
            "offer_id": offer_id,
            "source_resonance_id": self.ruin.pk,
            "target_resonance_id": self.dawnlight.pk,
            "amount": 10,
        }
        hobb_api = self.api(self.account_of(self.hobb))
        self.assertEqual(hobb_api.get(PENDING).data["results"], [])
        self.assertEqual(
            post(hobb_api, CONVERT, {**body, "component_ids": [hobbs]}).status_code, 404
        )
        self.assertEqual(post(hobb_api, DECLINE, {"offer_id": offer_id}).status_code, 404)
        self.assertEqual(self.api().get(PENDING).status_code, 403)
        # Nothing moved: her offer, her thread and her Ruin are as they were.
        self.assertEqual(self.offer_of(self.ysmay).pk, offer_id)
        self.assertFalse(consumed(mine))
        self.assertFalse(consumed(hobbs))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(drift_grants(), [])

    def test_a_failed_roll_is_reported_and_the_chance_stays(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(Failure="0.00")
        self.deed(self.ysmay)
        ysmay_api = self.api(self.account_of(self.ysmay))
        offer_id = ysmay_api.get(PENDING).data["results"][0]["id"]
        with force_check_outcome(self.outcomes["Failure"]):
            done = post(
                ysmay_api,
                CONVERT,
                {
                    "offer_id": offer_id,
                    "source_resonance_id": self.ruin.pk,
                    "target_resonance_id": self.dawnlight.pk,
                    "amount": 10,
                    "component_ids": [mine],
                },
            )
        self.assertEqual(done.status_code, 200)
        self.assertEqual((done.data["converted_amount"], done.data["granted_amount"]), (0, 0))
        self.assertEqual(done.data["outcome_name"], "Failure")
        self.assertTrue(consumed(mine))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(drift_grants(), [])
        self.assertEqual(len(ysmay_api.get(PENDING).data["results"]), 1)
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)

    def test_declining_on_the_web_lets_the_offer_go(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        ysmay_api = self.api(self.account_of(self.ysmay))
        offer_id = ysmay_api.get(PENDING).data["results"][0]["id"]
        done = post(ysmay_api, DECLINE, {"offer_id": offer_id})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["detail"], "You let the chance to correct drift pass.")
        self.assertEqual(ysmay_api.get(PENDING).data["results"], [])
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))
        self.assertFalse(consumed(mine))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(post(ysmay_api, DECLINE, {"offer_id": offer_id}).status_code, 404)


class TheChanceLapsesWithTheScene(DriftJourneyCase):
    def test_finishing_the_scene_takes_the_offer_and_says_so(self) -> None:
        self.connect_telnet(self.ysmay)
        self.watch(self.ysmay)
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))
        self.assertIsNotNone(self.offer_of(self.ysmay))
        ysmay_api = self.api(self.account_of(self.ysmay))
        self.assertEqual(len(ysmay_api.get(PENDING).data["results"]), 1)

        # Marrow owns the scene, so the real `scene finish` route runs (finish_scene_full).
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account_of(self.marrow))
        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.marrow, "scene finish")
        self.assertIn("The scene comes to a close.", told)
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_finished)

        self.assertIn(LAPSE, strip_ansi(self.said(self.ysmay)))
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertEqual(DriftConversionCap.objects.count(), 0)
        self.assertEqual(ysmay_api.get(PENDING).data["results"], [])
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift convert Ruin=Dawnlight 5"))
        self.assertFalse(consumed(mine))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(drift_grants(), [])

    def test_a_deed_after_the_scene_finished_opens_nothing_even_on_a_stale_room_cache(
        self,
    ) -> None:
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account_of(self.marrow))
        self.telnet(self.marrow, "scene finish")
        self.assertTrue(Scene.objects.get(pk=self.scene.pk).is_finished)
        # `scene finish` busts the room's active-scene cache. Another process, or a route
        # that finishes a scene without busting it, can leave the finished scene cached on
        # the room: put it back, so only the `is_finished` guard stands between the deed
        # and an offer for a scene that is over.
        self.lantern._active_scene_cache = Scene.objects.get(pk=self.scene.pk)
        self.assertEqual(get_active_scene(self.lantern).pk, self.scene.pk)

        self.deed(self.ysmay)

        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))


class WhenNothingOpensAChance(DriftJourneyCase):
    def test_a_deed_for_a_character_with_no_drift_opens_nothing(self) -> None:
        self.connect_telnet(self.hobb)
        self.watch(self.hobb)
        self.hold(self.hobb, self.dawnlight, 0, lifetime=500)
        set_aura_split(
            CharacterAuraFactory(character=self.hobb.sheet_data),
            celestial="100",
            primal="0",
            abyssal="0",
        )
        told = self.deed(self.hobb)
        self.assertIn("You tagged Hobb with 'Dawn Flourish'. 20 Dawnlight and renown", told)
        self.assertEqual(balance(self.hobb, self.dawnlight), 20)
        self.assertIsNone(self.offer_of(self.hobb))
        self.assertNotIn(NOTICE, strip_ansi(self.said(self.hobb)))
        self.assertIn(NO_OFFER, self.telnet(self.hobb, "drift"))

    def test_a_staff_grant_is_not_a_deed_and_opens_nothing(self) -> None:
        # The only real face of a staff grant is the admin action `grant_resonance_action`
        # (src/world/magic/admin.py): no telnet verb or API route grants by staff fiat. It
        # is a plain function of (modeladmin, request, queryset), so the journey runs it as
        # staff would from the CharacterResonance changelist, granting 1 per selected row.
        self.connect_telnet(self.ysmay)
        self.watch(self.ysmay)
        rows = CharacterResonance.objects.filter(
            character_sheet=self.ysmay.sheet_data, resonance=self.dawnlight
        )
        staff_request = SimpleNamespace(user=self.account_of(self.marrow))
        with self.captureOnCommitCallbacks(execute=True):
            grant_resonance_action(None, staff_request, rows)
        grant = ResonanceGrant.objects.get(source=GainSource.STAFF_GRANT)
        self.assertEqual((grant.resonance, grant.amount), (self.dawnlight, 1))
        self.assertEqual(balance(self.ysmay, self.dawnlight), 1)
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertNotIn(NOTICE, strip_ansi(self.said(self.ysmay)))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))

    def test_a_deed_in_a_room_with_no_live_scene_opens_nothing(self) -> None:
        elsewhere = self.make_room("The Cellar")
        self.ysmay.move_to(elsewhere, quiet=True)
        grant_resonance(
            self.ysmay.sheet_data,
            self.dawnlight,
            20,
            source=GainSource.DRAMATIC_MOMENT,
            dramatic_moment=DramaticMomentTagFactory(character_sheet=self.ysmay.sheet_data),
        )
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertIn(NO_OFFER, self.telnet(self.ysmay, "drift"))


class AFallingCharacterCorrectsTheOtherWay(DriftJourneyCase):
    """Bram is Abyssal and holds Celestial drift: the seeded Fall pair multiplies."""

    def test_fall_direction_converts_at_one_and_a_half(self) -> None:
        bram = self.make_player("Bram", room=self.lantern)
        self.hold(bram, self.ruin, 0, lifetime=500)
        self.hold(bram, self.dawnlight, 30)
        set_aura_split(
            CharacterAuraFactory(character=bram.sheet_data),
            celestial="10",
            primal="10",
            abyssal="80",
        )
        ruin_flourish = DramaticMomentTypeFactory(
            label="Ruin Flourish", resonance=self.ruin, per_scene_cap=3, resonance_amount=20
        )
        thread = self.carry(bram, self.ruin, "Ashen Thread")
        self.deed(bram, ruin_flourish.label)
        self.assertEqual(balance(bram, self.ruin), 20)

        shown = strip_ansi(self.telnet(bram, "drift"))
        self.assertIn("Toward Ruin: up to 10.", shown)
        # Celestial -> Abyssal is the seeded Fall pair at 1.50: 10 x 1.5 = 15.
        self.assertIn("From Dawnlight: you hold 30, FALL at 1.5", shown)
        self.assertIn("Converting 10 would give 15.", shown)

        with force_check_outcome(self.outcomes["Success"]):
            told = self.telnet(bram, "drift convert Dawnlight=Ruin 10")
        self.assertIn("10 Dawnlight became 15 Ruin.", told)
        self.assertEqual(balance(bram, self.dawnlight), 20)
        # 20 from the deed + 15 from the rite.
        self.assertEqual(balance(bram, self.ruin), 35)
        (grant,) = drift_grants()
        self.assertEqual((grant.resonance, grant.amount), (self.ruin, 15))
        self.assertTrue(consumed(thread))
