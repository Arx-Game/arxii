"""Journeys through the rite of settling and the open chance to atone (#4733, #5124).

A deed grows a resonance of the character's own affinity while she carries resonance that
does not fit her, and the game opens a chance to atone that stays open until the rite spends
it. A character writes reflections (a pose or a journal entry that names a deed, or the
resonance unsettling her, and Embrace or Disown); one rite of settling, one offering and one
roll, carries out every reflection waiting. Ysmay is a Celestial character holding Ruin
(Abyssal) drift; Marrow is staff and tags her moments; Hobb is the other player on the
account side.

Everything the rate depends on is the SEEDED pair rows (``seed_canonical_affinities`` and
``_seed_affinity_interactions``): Abyssal -> Celestial is Redemption at 0.5, Celestial ->
Abyssal is Fall at 1.50. Only the characters, scene, resonances, the rite, the check type
and the per-tier outcome shares are built by factories. Expected numbers are worked out by
hand in each journey, from those rows, the authored cap of 50 percent per deed and the
authored 75 percent a disowned deed turns:

* A Dawnlight deed of 20 raises the cap toward Dawnlight by 50% of 20 = 10.
* Converting N Ruin at a full share yields int(N x 0.5) Dawnlight (Redemption).
* Embracing a deed of N at share s grows it by int(N x s); disowning a deed of N turns
  int(N x 0.75 x s) of it.

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
from web.admin.tuning.required_content import _probe_drift_correction_config
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import ItemFacetFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.admin import grant_resonance_action
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    DriftCorrectionRiteFactory,
    FacetFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    RecordedActFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    set_aura_split,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    CharacterAuraShare,
    CharacterResonance,
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionOutcomeShare,
    Reflection,
    Resonance,
    ResonanceGrant,
    SettlingRite,
)
from world.magic.services.drift import (
    drift_for,
    get_drift_config,
    get_drift_correction_config,
)
from world.magic.services.resonance import grant_resonance
from world.scenes.factories import SceneFactory, SceneOwnerParticipationFactory
from world.scenes.interaction_services import get_active_scene, invalidate_active_scene_cache
from world.scenes.models import Scene
from world.seeds.game_content.magic import _seed_affinity_interactions, seed_canonical_affinities
from world.skills.factories import MagicSkillFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

NOTICE = "You have grown unsettled. Use aura to see how you can atone."
NOT_READY = "The rite of settling is not set up yet; tell staff."
NOTHING_WAITING = "You have no reflections waiting."
PENDING = "/api/magic/drift-correction/pending/"
RITE = "/api/magic/settling-rite/"
AURAS = "/api/magic/character-auras/"
POSE = "sets the iron on the altar and looks at it."


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
    all there is to read back), 30 Ruin (Abyssal) of unsettled excess (an aura of 100/0/0,
    no tolerance).
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
            celestial="100",
            primal="0",
            abyssal="0",
        )
        # Nothing of Ruin is who she is and no tolerance is allowed it, so all 30 of it is
        # unsettled excess, which is what the rite may convert.
        tolerance = get_drift_config()
        tolerance.unsettled_tolerance_percent = 0
        tolerance.save()
        self.dawn_flourish = DramaticMomentTypeFactory(
            label="Dawn Flourish", resonance=self.dawnlight, per_scene_cap=3, resonance_amount=20
        )

        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty_level = 0
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

    def reflect(self, character, target: str, choice: str) -> str:
        """Write a pose that reflects on ``target`` (a deed's number or a resonance's name)."""
        return self.telnet(character, f"pose/reflect {target}={choice} {POSE}")

    def kindled_deed(self, character, resonance: Resonance, amount: int) -> ResonanceGrant:
        """Grant ``character`` a kindled deed of ``amount`` of ``resonance``."""
        situation = KindlingSituationFactory(resonance=resonance, reason_text="Held the line")
        grant_resonance(
            character.sheet_data,
            resonance,
            amount,
            source=GainSource.KINDLED_DEED,
            kindling_situation=situation,
        )
        return ResonanceGrant.objects.filter(
            character_sheet=character.sheet_data, source=GainSource.KINDLED_DEED
        ).latest("pk")

    def waiting(self, character) -> int:
        return Reflection.objects.filter(
            character_sheet=character.sheet_data, rite__isnull=True
        ).count()

    def settle(self, character, offering: str, tier: str = "Success") -> str:
        with force_check_outcome(self.outcomes[tier]):
            return strip_ansi(self.telnet(character, f"aura settle {offering}"))

    def aura_payload(self, character) -> dict:
        """The one aura row the sheet reads for ``character``, as her own account asks."""
        response = self.api(self.account_of(character)).get(f"{AURAS}?character={character.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        (row,) = response.json()
        return row


class DisowningWhatUnsettlesHer(DriftJourneyCase):
    """Ysmay disowns her Ruin; the rite atones up to the chance a deed opened."""

    def test_two_deeds_raise_the_cap_and_the_rite_turns_ruin_at_the_seeded_rate(self) -> None:
        self.connect_telnet(self.ysmay)
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")

        self.assertIn(NOTHING_WAITING, strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertIsNone(self.offer_of(self.ysmay))

        # First deed: 20 Dawnlight granted; the cap is 50% of 20 = 10. A second raises it
        # to 20 and tells her nothing new.
        self.deed(self.ysmay)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))
        before = len(self.mailbox(self.ysmay).lines)
        self.deed(self.ysmay)
        self.assertNotIn(NOTICE, strip_ansi("\n".join(self.mailbox(self.ysmay).lines[before:])))
        self.assertEqual(
            DriftConversionOffer.objects.filter(character_sheet=self.ysmay.sheet_data).count(), 1
        )
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 20)

        told = self.reflect(self.ysmay, "Ruin", "disown")
        self.assertIn("recorded", told)
        shown = strip_ansi(self.telnet(self.ysmay, "aura"))
        self.assertIn("Your reflections, waiting for the rite of settling:", shown)
        self.assertIn("Disown your Ruin", shown)
        self.assertIn("Ruin turns toward Dawnlight, up to 20.", shown)
        self.assertIn("Offering you carry: Dawn-gold Thread.", shown)
        self.assertIn("A chance to atone is open: up to 20 toward Dawnlight.", shown)

        # The rite turns the whole cap: 20 Ruin at 0.5 is 10 Dawnlight.
        told = self.settle(self.ysmay, "Dawn-gold")
        self.assertIn("Success.", told)
        self.assertIn("You disown your Ruin: 20 Ruin became 10 Dawnlight.", told)
        self.assertEqual(balance(self.ysmay, self.ruin), 30 - 20)
        # 20 + 20 from the two deeds, +10 from the rite.
        self.assertEqual(balance(self.ysmay, self.dawnlight), 50)
        (grant,) = drift_grants()
        self.assertEqual((grant.resonance, grant.amount), (self.dawnlight, 10))
        self.assertTrue(consumed(thread))
        # The cap was spent, so the chance closed; the reflection is no longer waiting.
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertEqual(self.waiting(self.ysmay), 0)
        rite = SettlingRite.objects.get()
        self.assertEqual((rite.share, rite.outcome.name), (Decimal("1.00"), "Success"))
        self.assertEqual(Reflection.objects.get().rite, rite)
        self.assertIn(NOTHING_WAITING, strip_ansi(self.telnet(self.ysmay, "aura")))

    def test_a_half_share_turns_half_the_cap_and_keeps_the_rest_of_it(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(**{"Partial Success": "0.50"})
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        told = self.settle(self.ysmay, "Dawn-gold", "Partial Success")

        # Half of the cap of 10 is 5 Ruin, which is int(5 x 0.5) = 2 Dawnlight; the cap falls
        # by 5. The tier leads the line, so a partial rite never reads as a full one.
        self.assertIn("Partial Success.", told)
        self.assertIn("You disown your Ruin: 5 Ruin became 2 Dawnlight.", told)
        self.assertTrue(consumed(thread))
        self.assertEqual(balance(self.ysmay, self.ruin), 25)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 22)
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 5)
        self.assertEqual(self.waiting(self.ysmay), 0)

    def test_a_failed_roll_costs_the_offering_and_takes_every_reflection_for_nothing(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(Failure="0.00")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        told = self.settle(self.ysmay, "Dawn-gold", "Failure")

        self.assertIn("Failure.", told)
        self.assertIn("the rite turns nothing of it away", told)
        self.assertTrue(consumed(thread))
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 20)
        self.assertEqual(drift_grants(), [])
        # Every reflection took the rite even at a share of 0, and the chance itself stays.
        self.assertEqual(self.waiting(self.ysmay), 0)
        self.assertEqual(SettlingRite.objects.get().share, Decimal("0.00"))
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)


class TheRitesRollCarriesTheSkillOfWhereItTurns(DriftJourneyCase):
    """Staff gave Celestial a skill, Heroism; Ysmay (Celestial) performs the rite (#5308).

    The roll adds the skill of the affinity the conversion turns toward: here Celestial, the
    affinity of the Dawnlight her offering is tied to. The check is captured, so what the
    roll carried is read from its own call and nothing of ours is patched.
    """

    def setUp(self) -> None:
        super().setUp()
        self.heroism = MagicSkillFactory(name="Heroism")
        self.celestial.skill = self.heroism
        self.celestial.save()
        Affinity.objects.clear_cache()

    def rite_roll(self, offering: str):
        """Perform the rite on Success; the one call the rite's own check made."""
        with force_check_outcome(self.outcomes["Success"]) as capture:
            self.telnet(self.ysmay, f"aura settle {offering}")
        (call,) = capture.calls
        return call

    def test_a_rite_that_turns_ruin_toward_dawnlight_adds_heroism_once(self) -> None:
        self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        call = self.rite_roll("Dawn-gold")

        self.assertEqual([term.trait for term in call.extra_traits], [self.heroism])
        self.assertEqual(SettlingRite.objects.count(), 1)

    def test_a_rite_that_only_embraces_adds_no_skill(self) -> None:
        self.carry(self.ysmay, self.ruin, "Ruin-iron Ring")
        self.reflect(self.ysmay, "Ruin", "embrace")

        call = self.rite_roll("Ring")

        self.assertEqual(call.extra_traits, ())
        self.assertEqual(SettlingRite.objects.count(), 1)

    def test_an_inactive_skill_is_not_added(self) -> None:
        self.heroism.is_active = False
        self.heroism.save()
        self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        call = self.rite_roll("Dawn-gold")

        self.assertEqual(call.extra_traits, ())
        self.assertEqual(SettlingRite.objects.count(), 1)


class WhenTheRiteRefuses(DriftJourneyCase):
    """A refusal writes nothing and leaves every reflection waiting."""

    def test_with_no_reflection_waiting_nothing_is_spent(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)

        told = self.settle(self.ysmay, "Dawn-gold")

        self.assertIn("You have no reflections waiting.", told)
        self.assertFalse(consumed(thread))
        self.assertEqual(SettlingRite.objects.count(), 0)
        self.assertEqual(balance(self.ysmay, self.ruin), 30)

    def test_with_no_offering_carried_the_rite_refuses_and_every_reflection_keeps_waiting(
        self,
    ) -> None:
        deed = self.kindled_deed(self.ysmay, self.ruin, 10)
        self.reflect(self.ysmay, str(deed.pk), "disown")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")
        self.assertEqual(self.waiting(self.ysmay), 2)

        told = self.settle(self.ysmay, "Thread")
        with force_check_outcome(self.outcomes["Success"]):
            on_the_web = self.web(self.ysmay, "perform_settling_rite", components_provided=[])

        self.assertIn("You carry nothing called 'Thread'", told)
        self.assertFalse(on_the_web.detail.success)
        self.assertEqual(self.waiting(self.ysmay), 2)
        self.assertEqual(SettlingRite.objects.count(), 0)
        self.assertEqual(balance(self.ysmay, self.ruin), 40)

    def test_a_generic_dispatch_with_raw_ids_is_refused_in_a_sentence_and_writes_nothing(
        self,
    ) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        with force_check_outcome(self.outcomes["Success"]):
            result = self.web(self.ysmay, "perform_settling_rite", components_provided=[thread])

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "You are not carrying everything you offered.")
        self.assertFalse(consumed(thread))
        self.assertEqual(self.waiting(self.ysmay), 1)
        self.assertEqual(SettlingRite.objects.count(), 0)

    def test_an_offering_that_counts_for_nothing_the_rite_moves_is_refused(self) -> None:
        other = ResonanceFactory(name="Sunrise", affinity=self.celestial)
        stranger = self.carry(self.ysmay, other, "Sunrise Candle")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        told = self.settle(self.ysmay, "Candle")

        self.assertIn("Sunrise Candle does not count as an offering", told)
        self.assertFalse(consumed(stranger))
        self.assertEqual(self.waiting(self.ysmay), 1)
        self.assertEqual(SettlingRite.objects.count(), 0)
        self.assertEqual(balance(self.ysmay, self.ruin), 30)
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)

    def test_a_faceted_cloak_is_spent_only_when_she_names_it(self) -> None:
        # Her motif ties the Dawn Sigil facet to Dawnlight, so a cloak bearing it counts
        # toward a Dawnlight offering by the facet route. She carries no material.
        sigil = FacetFactory(name="Dawn Sigil")
        link = MotifResonanceFactory(
            motif__character=self.ysmay.sheet_data, resonance=self.dawnlight
        )
        MotifResonanceAssociationFactory(motif_resonance=link, facet=sigil)
        cloak = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Sigil Cloak"),
            holder_character_sheet=self.ysmay.sheet_data,
        )
        ItemFacetFactory(item_instance=cloak, facet=sigil)
        materialize_item_game_object(cloak, self.ysmay.sheet_data)
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        self.assertIn(
            "Offering you carry: Sigil Cloak.", strip_ansi(self.telnet(self.ysmay, "aura"))
        )
        self.assertIn("You carry nothing called 'Thread'", self.settle(self.ysmay, "Thread"))
        self.assertFalse(consumed(cloak.pk))

        cloak_pk = cloak.pk
        told = self.settle(self.ysmay, "cloak")
        self.assertIn("You disown your Ruin: 10 Ruin became 5 Dawnlight.", told)
        self.assertTrue(consumed(cloak_pk))

    def test_when_staff_have_not_set_up_the_rite_it_says_so_everywhere(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        # The rite and its check type are set; only the Partial Success share is missing.
        DriftCorrectionOutcomeShare.objects.filter(
            outcome_tier=self.outcomes["Partial Success"]
        ).delete()
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")

        self.assertIn(NOT_READY, strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertIn(NOT_READY, self.settle(self.ysmay, "Dawn-gold"))
        reading = self.api(self.account_of(self.ysmay)).get(
            RITE, {"character_sheet": self.ysmay.sheet_data.pk}
        )
        self.assertEqual(reading.status_code, 200)
        self.assertEqual(
            (
                reading.data["rite_ready"],
                reading.data["not_ready_message"],
                reading.data["offerings"],
            ),
            (False, NOT_READY, []),
        )
        self.assertFalse(consumed(thread))
        self.assertEqual(self.waiting(self.ysmay), 1)
        probe = _probe_drift_correction_config()
        self.assertEqual((probe.present, probe.missing), (False, ("Partial Success",)))


class ReflectingOnDeeds(DriftJourneyCase):
    def test_embracing_a_deed_grows_what_it_earned_by_the_share(self) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.set_shares(**{"Partial Success": "0.50"})
        deed = self.kindled_deed(self.ysmay, self.dawnlight, 8)
        self.assertIn("recorded", self.reflect(self.ysmay, str(deed.pk), "embrace"))
        before = balance(self.ysmay, self.dawnlight)

        told = self.settle(self.ysmay, "Dawn-gold", "Partial Success")

        # int(8 x 0.5) = 4.
        self.assertIn("You embrace Held the line: your Dawnlight grows by 4.", told)
        self.assertEqual(balance(self.ysmay, self.dawnlight), before + 4)
        embraced = ResonanceGrant.objects.get(source=GainSource.EMBRACED_DEED)
        self.assertEqual((embraced.resonance, embraced.amount), (self.dawnlight, 4))
        reflection = Reflection.objects.get()
        self.assertEqual(
            (embraced.source_reflection, embraced.source_settling_rite),
            (reflection, reflection.rite),
        )
        self.assertTrue(consumed(thread))

    def test_disowning_a_deed_turns_most_of_it_toward_the_main_affinity_with_no_chance_open(
        self,
    ) -> None:
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        deed = self.kindled_deed(self.ysmay, self.ruin, 10)
        # A deed of Ruin is not of her own affinity, so it opens no chance to atone.
        self.assertIsNone(self.offer_of(self.ysmay))
        self.reflect(self.ysmay, str(deed.pk), "disown")

        told = self.settle(self.ysmay, "Dawn-gold")

        # int(10 x 75 / 100) = 7 Ruin, at 0.5 is 3 Dawnlight.
        self.assertIn("You disown Held the line: 7 Ruin became 3 Dawnlight.", told)
        self.assertEqual(balance(self.ysmay, self.ruin), 40 - 7)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 3)
        self.assertTrue(consumed(thread))

    def test_a_pose_disowning_a_deed_then_the_rite_turns_it_and_the_room_saw_only_the_pose(
        self,
    ) -> None:
        self.watch(self.hobb)
        self.connect_telnet(self.hobb)
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        deed = self.kindled_deed(self.ysmay, self.ruin, 10)

        told = self.reflect(self.ysmay, str(deed.pk), "disown")

        # She alone is told it is recorded; the room read the pose and nothing of the reflection.
        self.assertIn("is recorded", told)
        self.assertTold(self.hobb, POSE)
        for word in ("reflect", "disown", "recorded", "Held the line"):
            self.assertNotTold(self.hobb, word)
        self.assertEqual(self.waiting(self.ysmay), 1)
        self.assertEqual(balance(self.ysmay, self.ruin), 40)

        settled = self.settle(self.ysmay, "Dawn-gold")

        # Most of the deed (75%, 7 of 10) turned toward the main affinity, at the 0.5 rate.
        self.assertIn("7 Ruin became 3 Dawnlight", settled)
        self.assertEqual(balance(self.ysmay, self.ruin), 40 - 7)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 3)
        self.assertEqual(self.waiting(self.ysmay), 0)
        self.assertTrue(consumed(thread))

    def test_a_deed_is_reflected_on_once_and_the_deeds_show_on_the_aura_until_then(self) -> None:
        self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        deed = self.kindled_deed(self.ysmay, self.dawnlight, 8)
        shown = strip_ansi(self.telnet(self.ysmay, "aura"))
        self.assertIn("Deeds not yet reflected on:", shown)
        self.assertIn(f"#{deed.pk} Held the line", shown)
        self.reflect(self.ysmay, str(deed.pk), "embrace")
        self.assertNotIn("Deeds not yet reflected on:", strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertIn("already reflected on", self.reflect(self.ysmay, str(deed.pk), "disown"))


class AcceptingWhatSheHasBecome(DriftJourneyCase):
    def test_embracing_the_unsettling_resonance_settles_her_in_full_at_a_full_share(self) -> None:
        sheet = self.ysmay.sheet_data
        # A tolerance of 1 point keeps the shares' rounding (5.45 stored, 5.4545 read) from
        # reading as excess once she is settled; the setup's tolerance of 0 would.
        tolerance = get_drift_config()
        tolerance.unsettled_tolerance_percent = 1
        tolerance.save()
        self.carry(self.ysmay, self.ruin, "Ruin-iron Ring")
        self.assertGreater(drift_for(sheet).steps_past, 0)
        self.reflect(self.ysmay, "Ruin", "embrace")

        told = self.settle(self.ysmay, "Ring")

        self.assertIn("You become more abyssal.", told)
        self.assertEqual(drift_for(sheet).steps_past, 0)
        share = CharacterAuraShare.objects.get(aura__character=sheet, affinity=self.abyssal)
        self.assertEqual(share.settled_percent, share.percent)
        self.assertEqual(self.waiting(self.ysmay), 0)

    def test_a_weaker_roll_moves_her_only_part_of_the_way(self) -> None:
        sheet = self.ysmay.sheet_data
        self.set_shares(**{"Partial Success": "0.50"})
        self.carry(self.ysmay, self.ruin, "Ruin-iron Ring")
        self.reflect(self.ysmay, "Ruin", "embrace")

        told = self.settle(self.ysmay, "Ring", "Partial Success")

        self.assertIn("You move part of the way toward being more abyssal.", told)
        share = CharacterAuraShare.objects.get(aura__character=sheet, affinity=self.abyssal)
        self.assertTrue(0 < share.settled_percent < share.percent)
        self.assertGreater(drift_for(sheet).steps_past, 0)
        self.assertEqual(self.waiting(self.ysmay), 0)


class TheMainAffinitysOwnRange(DriftJourneyCase):
    """Staff narrow Celestial's range before Unsettled; a small Abyssal deed then unsettles her."""

    def test_a_deed_inside_the_general_range_unsettles_her_once_celestial_sets_a_narrower_one(
        self,
    ) -> None:
        sheet = self.ysmay.sheet_data
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        # Start from a settled Celestial with no Ruin and the general 5 and 5.
        ruin_row = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.ruin)
        ruin_row.balance = 0
        ruin_row.lifetime_earned = 0
        ruin_row.save()
        general = get_drift_config()
        general.unsettled_tolerance_percent = 5
        general.unsettled_step_percent = 5
        general.save()

        # She threatens a prisoner and earns 20 Ruin. Her lifetime resonance is now 500
        # Dawnlight + 20 Ruin = 520, so Ruin is 20 / 520 = 3.85% of it, past the 0% she has
        # settled for Abyssal. That is inside the general 5 points of range.
        deed = self.kindled_deed(self.ysmay, self.ruin, 20)
        self.assertIsNone(self.celestial.unsettled_tolerance_percent)
        self.assertIsNone(self.celestial.unsettled_step_percent)
        self.assertIs(self.aura_payload(self.ysmay)["unsettled"], False)
        self.assertEqual(self.aura_payload(self.ysmay)["unsettled_line"], "")
        self.assertNotIn("unsettled", strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertEqual(drift_for(sheet).steps_past, 0)

        # Staff set Celestial's range to 1 point and its step to 2. The same 3.85% is now
        # 3.85 - 0 - 1 = 2.85 points past, and 2.85 / 2 = 1.42 rounds up to 2 steps.
        self.celestial.unsettled_tolerance_percent = 1
        self.celestial.unsettled_step_percent = 2
        self.celestial.save()

        payload = self.aura_payload(self.ysmay)
        line = "Your Ruin has grown strong enough to make you unsettled."
        self.assertIs(payload["unsettled"], True)
        self.assertEqual(payload["unsettled_line"], line)
        self.assertIn(line, strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertEqual(drift_for(sheet).steps_past, 2)

        # She disowns the deed and performs the rite at a full share. 75% of 20 is 15 Ruin
        # turned, and 15 at Redemption's 0.5 is int(7.5) = 7 Dawnlight. Lifetime follows:
        # Ruin 20 - 15 = 5 and Dawnlight 500 + 15 = 515, still 520 in all. 5 / 520 = 0.96%
        # is under the 1 point of range, so she is settled again.
        self.assertIn("recorded", self.reflect(self.ysmay, str(deed.pk), "disown"))
        told = self.settle(self.ysmay, "Dawn-gold")

        self.assertIn("You disown Held the line: 15 Ruin became 7 Dawnlight.", told)
        self.assertTrue(consumed(thread))
        ruin_after = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.ruin)
        self.assertEqual((ruin_after.balance, ruin_after.lifetime_earned), (5, 5))
        dawn_after = CharacterResonance.objects.get(character_sheet=sheet, resonance=self.dawnlight)
        self.assertEqual((dawn_after.balance, dawn_after.lifetime_earned), (7, 515))
        payload = self.aura_payload(self.ysmay)
        self.assertIs(payload["unsettled"], False)
        self.assertEqual(payload["unsettled_line"], "")
        self.assertNotIn("unsettled", strip_ansi(self.telnet(self.ysmay, "aura")))
        self.assertEqual(drift_for(sheet).steps_past, 0)


class AJournalEntryEmbracingWhatUnsettlesHer(DriftJourneyCase):
    def test_a_journal_entry_then_a_partial_rite_moves_her_settled_share_part_of_the_way(
        self,
    ) -> None:
        sheet = self.ysmay.sheet_data
        self.set_shares(**{"Partial Success": "0.50"})
        self.carry(self.ysmay, self.ruin, "Ruin-iron Ring")
        self.assertGreater(drift_for(sheet).steps_past, 0)

        told = self.telnet(
            self.ysmay,
            "journal/reflect Ruin=embrace title=What I have become body=It is mine now.",
        )

        self.assertIn("Your reflection on your Ruin is recorded", told)
        self.assertEqual(self.waiting(self.ysmay), 1)
        # Writing it settles nothing.
        self.assertGreater(drift_for(sheet).steps_past, 0)
        self.assertFalse(
            CharacterAuraShare.objects.filter(
                aura__character=sheet, affinity=self.abyssal, settled_percent__gt=0
            ).exists()
        )

        settled = self.settle(self.ysmay, "Ring", "Partial Success")

        self.assertIn("You move part of the way toward being more abyssal.", settled)
        after = CharacterAuraShare.objects.get(aura__character=sheet, affinity=self.abyssal)
        self.assertTrue(0 < after.settled_percent < after.percent)
        self.assertGreater(drift_for(sheet).steps_past, 0)
        self.assertEqual(self.waiting(self.ysmay), 0)

    def test_the_web_journal_editor_records_the_same_reflection_for_the_rite(self) -> None:
        response = self.api(self.account_of(self.ysmay)).post(
            "/api/journals/entries/",
            {
                "title": "What I have become",
                "body": "It is mine now.",
                "is_public": False,
                "reflect_choice": "EMBRACE",
                "reflect_resonance_id": self.ruin.pk,
            },
            format="json",
            HTTP_X_CHARACTER_ID=str(self.ysmay.pk),
        )

        self.assertEqual(response.status_code, 201, response.content)
        reflection = Reflection.objects.get()
        self.assertEqual(
            (reflection.resonance, reflection.journal_entry_id),
            (self.ruin, response.json()["id"]),
        )
        self.assertEqual(self.waiting(self.ysmay), 1)


class TheSameRiteOnTheWeb(DriftJourneyCase):
    """The rite's reading and its perform, as the browser dialog calls them."""

    def test_the_reading_shows_what_telnet_showed_and_perform_runs_the_same_rite(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        hobbs = self.carry(self.hobb, self.dawnlight, "Hobb's Dawn Thread")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")
        sheet_id = self.ysmay.sheet_data.pk
        ysmay_api = self.api(self.account_of(self.ysmay))

        reading = ysmay_api.get(RITE, {"character_sheet": sheet_id})
        self.assertEqual(reading.status_code, 200)
        (reflection,) = reading.data["reflections"]
        self.assertEqual(
            (reflection["choice"], reflection["kind"], reflection["title"]),
            ("DISOWN", "resonance", "Disown your Ruin"),
        )
        self.assertEqual(reflection["effect_line"], "Ruin turns toward Dawnlight, up to 10.")
        self.assertEqual(reflection["excerpt"], POSE)
        self.assertEqual(reflection["where"], "Pose in " + self.scene.name)
        (offering,) = reading.data["offerings"]
        self.assertEqual(
            (offering["item_id"], offering["name"], offering["mode"]),
            (mine, "Dawn-gold Thread", "material"),
        )
        (offer,) = ysmay_api.get(PENDING).data["results"]
        (cap,) = offer["caps"]
        self.assertEqual((cap["target_resonance"]["name"], cap["cap_remaining"]), ("Dawnlight", 10))

        body = {"character_sheet_id": sheet_id}
        # An item she does not hold, or one that does not exist, is refused before anything.
        with force_check_outcome(self.outcomes["Success"]):
            foreign = ysmay_api.post(RITE, {**body, "component_ids": [hobbs]}, format="json")
            missing = ysmay_api.post(RITE, {**body, "component_ids": [mine + 9999]}, format="json")
        for refused in (foreign, missing):
            self.assertEqual(refused.status_code, 400)
            self.assertEqual(
                refused.data, {"detail": "You are not carrying everything you offered."}
            )
        self.assertFalse(consumed(mine))
        self.assertFalse(consumed(hobbs))
        # No offering at all is the service's own refusal.
        with force_check_outcome(self.outcomes["Success"]):
            bare = ysmay_api.post(RITE, body, format="json")
        self.assertEqual(bare.status_code, 400)
        self.assertEqual(self.waiting(self.ysmay), 1)

        with force_check_outcome(self.outcomes["Success"]):
            done = ysmay_api.post(RITE, {**body, "component_ids": [mine]}, format="json")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["outcome_name"], "Success")
        self.assertEqual(done.data["lines"], ["You disown your Ruin: 10 Ruin became 5 Dawnlight."])
        self.assertEqual(balance(self.ysmay, self.ruin), 20)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 25)
        self.assertTrue(consumed(mine))
        self.assertFalse(consumed(hobbs))
        self.assertEqual(ysmay_api.get(RITE, {"character_sheet": sheet_id}).data["reflections"], [])
        self.assertEqual(ysmay_api.get(PENDING).data["results"], [])

    def test_another_account_neither_reads_nor_performs_her_rite(self) -> None:
        mine = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.reflect(self.ysmay, "Ruin", "disown")
        sheet_id = self.ysmay.sheet_data.pk
        hobb_api = self.api(self.account_of(self.hobb))

        self.assertEqual(hobb_api.get(RITE, {"character_sheet": sheet_id}).status_code, 404)
        with force_check_outcome(self.outcomes["Success"]):
            stolen = hobb_api.post(
                RITE, {"character_sheet_id": sheet_id, "component_ids": [mine]}, format="json"
            )
        self.assertEqual(stolen.status_code, 404)
        self.assertEqual(hobb_api.get(PENDING).data["results"], [])
        self.assertEqual(self.api().get(PENDING).status_code, 403)
        self.assertFalse(consumed(mine))
        self.assertEqual(self.waiting(self.ysmay), 1)
        self.assertEqual(balance(self.ysmay, self.ruin), 30)


class EmbracingAFallOnTheWeb(DriftJourneyCase):
    """Embracing a deed of another affinity pays at the direction rate, shown before and after."""

    def test_the_preview_the_result_line_and_the_balance_all_carry_the_rate(self) -> None:
        ring = self.carry(self.ysmay, self.ruin, "Ruin-iron Ring")
        # Ysmay is Celestial and the deed is Abyssal, so the pair is the seeded Celestial to
        # Abyssal Fall at 1.50. A deed of 15 embraced at the full share of Success (1.00) grows
        # 15 x 1.00 x 1.50 = 22.5, rounded down to 22; without the rate it would be 15.
        deed = self.kindled_deed(self.ysmay, self.ruin, 15)
        self.assertIn("recorded", self.reflect(self.ysmay, str(deed.pk), "embrace"))
        before = balance(self.ysmay, self.ruin)
        self.assertEqual(before, 30 + 15)
        sheet_id = self.ysmay.sheet_data.pk
        ysmay_api = self.api(self.account_of(self.ysmay))

        reading = ysmay_api.get(RITE, {"character_sheet": sheet_id})

        self.assertEqual(reading.status_code, 200)
        (reflection,) = reading.data["reflections"]
        self.assertEqual(reflection["choice"], "EMBRACE")
        self.assertEqual(reflection["effect_line"], "Your Ruin from Held the line grows, up to 22.")
        self.assertEqual(balance(self.ysmay, self.ruin), before)

        with force_check_outcome(self.outcomes["Success"]):
            done = ysmay_api.post(
                RITE, {"character_sheet_id": sheet_id, "component_ids": [ring]}, format="json"
            )

        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(done.data["lines"], ["You embrace Held the line: your Ruin grows by 22."])
        self.assertEqual(balance(self.ysmay, self.ruin), before + 22)
        embraced = ResonanceGrant.objects.get(source=GainSource.EMBRACED_DEED)
        self.assertEqual((embraced.resonance, embraced.amount), (self.ruin, 22))
        self.assertEqual(self.waiting(self.ysmay), 0)


class TheChanceStaysOpenWhenTheSceneEnds(DriftJourneyCase):
    def test_finishing_the_scene_leaves_the_chance_and_the_rite_still_uses_it(self) -> None:
        self.connect_telnet(self.ysmay)
        self.watch(self.ysmay)
        thread = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))
        ysmay_api = self.api(self.account_of(self.ysmay))
        self.assertEqual(len(ysmay_api.get(PENDING).data["results"]), 1)

        # Marrow owns the scene, so the real `scene finish` route runs (finish_scene_full).
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account_of(self.marrow))
        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.marrow, "scene finish")
        self.assertIn("The scene comes to a close.", told)
        self.scene.refresh_from_db()
        self.assertTrue(self.scene.is_finished)

        self.assertNotIn("passes with the scene", strip_ansi(self.said(self.ysmay)))
        self.assertIsNotNone(self.offer_of(self.ysmay))
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 10)
        self.assertEqual(len(ysmay_api.get(PENDING).data["results"]), 1)
        self.assertIn(
            "A chance to atone is open: up to 10 toward Dawnlight.",
            strip_ansi(self.telnet(self.ysmay, "aura")),
        )

        # Out of any scene, she writes the reflection and settles; the cap is still hers.
        self.reflect(self.ysmay, "Ruin", "disown")
        told = self.settle(self.ysmay, "Dawn-gold")
        self.assertIn("You disown your Ruin: 10 Ruin became 5 Dawnlight.", told)
        self.assertTrue(consumed(thread))
        self.assertIsNone(self.offer_of(self.ysmay))
        self.assertEqual(SettlingRite.objects.get().scene, None)

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


class AMarkIsADeedAndOpensTheChance(DriftJourneyCase):
    """A gain Ysmay marks on an act in the live scene is a deed like a GM's tag (#5327)."""

    def test_marking_an_act_with_dawnlight_grows_it_and_opens_the_chance_to_atone(self) -> None:
        self.connect_telnet(self.ysmay)
        success = self.outcomes["Success"]
        KindledDeedAwardFactory(outcome_tier=success, amount=10)
        KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=100)
        act = RecordedActFactory(
            character_sheet=self.ysmay.sheet_data, outcome=success, label="Held the line"
        )
        self.assertIsNone(self.offer_of(self.ysmay))

        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.ysmay, f"pose/reach Dawnlight:{act.pk}=holds the line.")

        self.assertIn("Your Dawnlight grows by 10.", told)
        self.assertEqual(balance(self.ysmay, self.dawnlight), 10)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))
        # The chance is half the deed: 50 percent of 10.
        self.assertEqual(self.cap_toward(self.ysmay, self.dawnlight), 5)


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
