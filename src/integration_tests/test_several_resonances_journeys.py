"""Journeys through several resonances (#5123): the telnet face, then the web and API flows.

Ysmay is Celestial by the aura she settled (90 Celestial, 10 Abyssal) but has earned 70
Dawnlight and 30 Ruin: her Abyssal share (30) stands 20 past its settled share (10), so she
is unsettled and Ruin is what did it. Hand-worked from the shipped thresholds (tolerance 5):

* The aura reads in words, never numbers: 90 percent is "nearly all", 10 percent "a tenth".
* Accepting the changes settles who she is where she has got to (70 Celestial, 30 Abyssal),
  so nothing is past anything afterwards; the main affinity is still Celestial.
* A thread paid by a resonance she holds costs that resonance, not the thread's leading one
  (a tier 1 pull costs 1 resonance; the technique's own cast and anima are not what is read).
* An imbue paid by a resonance she holds debits that resonance and writes that row of the
  thread; the leading resonance's balance is untouched.

The second half walks the spec's Verification flows (creation, imbue and pull, unsettled,
atone and accept, Sineater, retune) through the REST API and the web dispatch seam. The
creation intro text, the halo drawing and the dialogs are the frontend's (vitest covers
them); what the browser is told about them is read here as the API payload they draw from.
"""

from __future__ import annotations

from decimal import Decimal
import re

from django.test import override_settings
from django.urls import reverse
from evennia.objects.models import ObjectDB
from evennia.utils.ansi import strip_ansi
from rest_framework import status

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from integration_tests.test_drift_correction_journeys import (
    CONVERT,
    NOTICE,
    PENDING,
    DriftJourneyCase,
    post,
)
from integration_tests.test_resonance_conflict_journeys import CONFLICT, _Drifting
from integration_tests.test_resonance_strain_journeys import _BurningResonance
from integration_tests.test_thread_resonance_journeys import (
    ThreadRetuneCase,
    consumed,
    rows,
    stored,
)
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassFactory
from world.classes.services import set_primary_class_level
from world.magic.constants import EffectKind, GainSource, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    _make_resist_corruption_check_type,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import Affinity, CharacterResonance, Resonance, Thread, ThreadResonance
from world.magic.models.aura import CharacterAuraShare
from world.magic.services.drift import get_drift_config
from world.magic.services.resonance import grant_resonance
from world.magic.specialization.services import provision_latent_gift_thread
from world.scenes.factories import SceneFactory
from world.scenes.models import Scene
from world.scenes.tests.cast_test_helpers import grant_technique, make_benign_castable_technique
from world.traits.factories import CheckSystemSetupFactory, TraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals


def _hold(sheet, resonance, lifetime: int):
    return CharacterResonance.objects.create(
        character_sheet=sheet, resonance=resonance, balance=lifetime, lifetime_earned=lifetime
    )


class _TheAura(JourneyCase):
    """Ysmay, unsettled by Ruin; Hobb, who is settled."""

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        self.celestial, _primal, self.abyssal = ensure_canonical_affinities()
        self.dawnlight = ResonanceFactory(name="Dawnlight", affinity=self.celestial)
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        for character, ruin in ((self.ysmay, 30), (self.hobb, 10)):
            sheet = character.sheet_data
            aura = CharacterAuraFactory(character=sheet)
            set_aura_split(aura, celestial="90", primal="0", abyssal="10")
            _hold(sheet, self.dawnlight, 100 - ruin)
            _hold(sheet, self.ruin, ruin)

    def abyssal_settled(self, character) -> int:
        share = CharacterAuraShare.objects.get(
            aura__character=character.sheet_data, affinity=self.abyssal
        )
        return int(share.settled_percent)


class SeeingTheAura(_TheAura):
    def test_aura_shows_unsettled_line(self) -> None:
        told = strip_ansi(self.telnet(self.ysmay, "aura"))

        self.assertIn("Celestial (nearly all)", told)
        self.assertIn("Abyssal (a tenth)", told)
        self.assertIn("Your Ruin has grown strong enough to make you unsettled.", told)
        self.assertNotIn("accepted", told.lower())
        self.assertIsNone(re.search(r"\d", told), told)

    def test_a_settled_character_is_not_told_she_is_unsettled(self) -> None:
        told = strip_ansi(self.telnet(self.hobb, "aura"))

        self.assertIn("Celestial (nearly all)", told)
        self.assertNotIn("unsettled", told)


class AcceptingTheChanges(_TheAura):
    def test_aura_accept(self) -> None:
        self.assertEqual(self.abyssal_settled(self.ysmay), 10)

        told = strip_ansi(self.telnet(self.ysmay, "aura accept"))

        self.assertIn("You become more abyssal.", told)
        self.assertNotIn("accepted", told.lower())
        self.assertEqual(self.abyssal_settled(self.ysmay), 30)
        self.assertNotIn("unsettled", strip_ansi(self.telnet(self.ysmay, "aura")))
        # Nothing is left to accept.
        again = self.telnet(self.ysmay, "aura accept")
        self.assertNotIn("You become more", again)
        self.assertEqual(self.abyssal_settled(self.ysmay), 30)

    def test_a_settled_character_has_nothing_to_accept(self) -> None:
        told = self.telnet(self.hobb, "aura accept")

        self.assertNotIn("You become more", told)
        self.assertEqual(self.abyssal_settled(self.hobb), 10)

    def test_an_unknown_subverb_prints_the_usage(self) -> None:
        self.assertIn("Usage: aura", self.telnet(self.ysmay, "aura frobnicate"))

    def test_the_old_drift_verb_is_gone(self) -> None:
        self.assertNotIn("Usage: aura", self.telnet(self.ysmay, "drift"))
        self.assertNotIn("unsettled", self.telnet(self.ysmay, "drift"))


class PullingWithANamedPayer(_BurningResonance):
    """Ysmay's skill thread leads with Veil; she also holds Ember, which has a row on it."""

    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.caster("Ysmay")
        self.veil = ResonanceFactory(name="Veil", affinity=self.primal)
        self.ember = ResonanceFactory(name="Ember", affinity=self.primal)
        self.thread = self.thread_for(self.ysmay, self.veil)
        _hold(self.ysmay.sheet_data, self.ember, 10)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.ember,
            tier=1,
            flat_bonus_amount=2,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        # Ember has been imbued into the thread beside Veil, so it brings its own perks.
        ThreadResonance.objects.create(thread=self.thread, resonance=self.ember, amount=5)
        self.thread.developed_points = 5
        self.thread.save(update_fields=["developed_points"])

    def cast(self, pulled: str) -> str:
        told, _channeled = self.cast_with_outcome(
            self.ysmay, f"cast {self.technique.name} pull={pulled}", "Success"
        )
        return strip_ansi(told)

    def test_cast_pull_with_named_payer(self) -> None:
        told = self.cast(f"{self.thread.name}:{self.ember.name}")

        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10 - 1)
        self.assertEqual(self.balance(self.ysmay, self.veil), 10)

    def test_a_bare_pull_is_paid_by_the_leading_resonance(self) -> None:
        told = self.cast(self.thread.name)

        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.veil), 10 - 1)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10)

    def test_a_resonance_she_does_not_hold_is_refused_in_words_and_nothing_is_paid(self) -> None:
        stranger = ResonanceFactory(name="Dusk", affinity=self.primal)
        for name in ("Nonesuch", stranger.name):
            told = self.cast(f"{self.thread.name}:{name}")
            self.assertIn(f"You hold no resonance called '{name}'.", told)
            self.assertNotIn("Traceback", told)

        self.assertEqual(self.balance(self.ysmay, self.veil), 10)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10)


class PullingAGiftThreadByTheGiftsName(_BurningResonance):
    """A Gift thread has no name of its own, so ``pull=`` names it by its Gift."""

    def setUp(self) -> None:
        super().setUp()
        self.ysmay = self.caster("Ysmay")
        self.veil = ResonanceFactory(name="Veil", affinity=self.primal)
        self.ember = ResonanceFactory(name="Ember", affinity=self.primal)
        sheet = self.ysmay.sheet_data
        self.gift = GiftFactory(name="Kindling")
        self.thread = provision_latent_gift_thread(sheet, self.gift, resonances=[self.veil])
        _hold(sheet, self.veil, 10)
        _hold(sheet, self.ember, 10)
        for resonance in (self.veil, self.ember):
            ThreadPullEffectFactory(
                target_kind=TargetKind.GIFT,
                resonance=resonance,
                tier=1,
                flat_bonus_amount=2,
                effect_kind=EffectKind.FLAT_BONUS,
            )
        ThreadResonance.objects.create(thread=self.thread, resonance=self.ember, amount=5)
        self.thread.developed_points = 5
        self.thread.save(update_fields=["developed_points"])

    def cast(self, pulled: str) -> str:
        told, _channeled = self.cast_with_outcome(
            self.ysmay, f"cast {self.technique.name} pull={pulled}", "Success"
        )
        return strip_ansi(told)

    def test_the_gifts_name_pulls_it_paid_by_the_leading_resonance(self) -> None:
        self.assertEqual(self.thread.name, "")

        told = self.cast("Kindling")

        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.veil), 10 - 1)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10)

    def test_the_number_pulls_it_too(self) -> None:
        told = self.cast(f"{self.thread.pk}:Ember")

        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10 - 1)

    def test_the_gifts_name_and_a_resonance_pays_with_that_resonance(self) -> None:
        told = self.cast("kindling:Ember")

        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.ember), 10 - 1)
        self.assertEqual(self.balance(self.ysmay, self.veil), 10)


class ImbuingWithAResonance(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        ImbuingRitualFactory()
        self.room = self.make_room("The Loom Room")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)
        set_primary_class_level(self.ysmay, CharacterClassFactory(), 1)
        self.veil = ResonanceFactory(name="Veil")
        self.ember = ResonanceFactory(name="Ember")
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.veil, balance=10, lifetime_earned=10
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=self.ember, balance=10, lifetime_earned=10
        )
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 500
        pool.maximum = 500
        pool.save()
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.veil,
            level=0,
            developed_points=0,
            _trait_value=200,
            name="Loom Strand",
        )

    def balance(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).balance

    def imbue(self, tail: str) -> str:
        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        return strip_ansi(self.telnet(self.ysmay, f"imbue thread={self.thread.pk} {tail}"))

    def test_imbue_with_resonance(self) -> None:
        told = self.imbue("amount=3 resonance=ember")

        self.assertIn("You complete the rite, imbuing Loom Strand.", told)
        self.assertEqual(self.balance(self.ember), 10 - 3)
        self.assertEqual(self.balance(self.veil), 10)
        row = ThreadResonance.objects.get(thread=self.thread, resonance=self.ember)
        self.assertEqual(row.amount, 3)
        self.thread.refresh_from_db()
        # A level from stored level 0 costs ten points: three points bank toward it.
        self.assertEqual((self.thread.level, self.thread.developed_points), (0, 3))

    def test_a_stray_word_after_the_amount_is_ignored_and_resonance_still_reads(self) -> None:
        told = self.imbue("amount=2 please resonance=ember")

        self.assertIn("You complete the rite, imbuing Loom Strand.", told)
        self.assertEqual(self.balance(self.ember), 10 - 2)
        self.assertEqual(self.balance(self.veil), 10)

    def test_a_stray_word_after_the_amount_alone_still_takes_the_amount(self) -> None:
        told = self.imbue("amount=3 please")

        self.assertIn("You complete the rite, imbuing Loom Strand.", told)
        self.assertEqual(self.balance(self.veil), 10 - 3)
        self.assertEqual(self.balance(self.ember), 10)

    def test_a_named_resonance_she_does_not_hold_is_refused_in_words(self) -> None:
        told = self.imbue("amount=3 resonance=Nonesuch")

        self.assertIn(
            "You hold no resonance called 'Nonesuch'. Your resonances: Ember, Veil.", told
        )
        self.assertEqual(self.balance(self.ember), 10)
        self.assertEqual(self.balance(self.veil), 10)

    def _gift_thread(self, gift_name: str = "Flame") -> Thread:
        gift = GiftFactory(name=gift_name)
        return provision_latent_gift_thread(self.sheet, gift, resonances=[self.veil])

    def test_a_gift_thread_is_imbued_by_the_gifts_name(self) -> None:
        gift_thread = self._gift_thread()
        self.assertEqual(gift_thread.name, "")  # no name of its own: the Gift's name is it

        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        told = strip_ansi(self.telnet(self.ysmay, "imbue thread=flame amount=3 resonance=ember"))

        self.assertIn("You complete the rite, imbuing Flame.", told)
        self.assertEqual(self.balance(self.ember), 10 - 3)
        row = ThreadResonance.objects.get(thread=gift_thread, resonance=self.ember)
        self.assertEqual(row.amount, 3)

    def test_threads_prints_the_name_a_player_can_type(self) -> None:
        self._gift_thread()

        told = strip_ansi(self.telnet(self.ysmay, "threads"))

        self.assertIn("Veil Flame (level 0)", told)
        self.assertIn("Loom Strand", told)

    def test_a_threads_own_name_that_is_another_threads_anchor_name_is_refused(self) -> None:
        gift_thread = self._gift_thread()
        named = ThreadFactory(
            owner=self.sheet, resonance=self.ember, level=2, _trait_value=200, name="Flame"
        )

        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        told = strip_ansi(self.telnet(self.ysmay, "imbue thread=Flame amount=3"))

        self.assertIn("More than one thread answers to 'Flame'", told)
        self.assertIn(f"number {gift_thread.pk} is Veil", told)
        self.assertIn(f"number {named.pk} is Ember", told)
        self.assertEqual(self.balance(self.ember), 10)
        self.assertEqual(self.balance(self.veil), 10)

    def test_the_gift_thread_is_reached_by_its_number_and_threads_prints_it(self) -> None:
        gift_thread = self._gift_thread()
        ThreadFactory(
            owner=self.sheet, resonance=self.ember, level=2, _trait_value=200, name="Flame"
        )

        listed = strip_ansi(self.telnet(self.ysmay, "threads"))
        self.assertIn(f"Flame [number {gift_thread.pk}]", listed)

        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        told = strip_ansi(
            self.telnet(self.ysmay, f"imbue thread={gift_thread.pk} amount=3 resonance=ember")
        )

        self.assertIn("You complete the rite, imbuing Flame.", told)
        self.assertEqual(
            ThreadResonance.objects.get(thread=gift_thread, resonance=self.ember).amount, 3
        )

    def test_a_name_two_anchors_share_is_refused_with_the_numbers(self) -> None:
        first = self._gift_thread()
        second = ThreadFactory(
            owner=self.sheet,
            resonance=self.ember,
            target_trait=TraitFactory(name="Flame"),
            name="",
            _trait_value=200,
        )

        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        told = strip_ansi(self.telnet(self.ysmay, "imbue thread=Flame amount=3"))

        self.assertIn("More than one thread answers to 'Flame'", told)
        self.assertIn(f"number {first.pk} is Veil", told)
        self.assertIn(f"number {second.pk} is Ember", told)
        self.assertEqual(self.balance(self.veil), 10)

    def test_threads_lists_the_mix_in_words(self) -> None:
        self.imbue("amount=3 resonance=ember")
        self.thread.refresh_from_db()
        self.imbue("amount=1 resonance=veil")

        told = strip_ansi(self.telnet(self.ysmay, "threads"))

        # 3 Ember and 1 Veil: Ember holds three quarters ("most"), Veil a quarter ("a fifth").
        self.assertIn("Ember (most), Veil (a fifth)", told)


# ---------------------------------------------------------------------------------------
# The web and API flows (the spec's Verification flows 1 to 6)
# ---------------------------------------------------------------------------------------

AURAS = "/api/magic/character-auras/"
THREADS = "/api/magic/threads/"
PERFORM_URL = "/api/magic/rituals/perform/"


def _share_rows(payload: dict) -> dict[str, tuple[Decimal, Decimal]]:
    """The aura payload's shares as ``{affinity name: (percent, settled percent)}``."""
    return {
        row["affinity_name"]: (Decimal(row["percent"]), Decimal(row["settled_percent"]))
        for row in payload["shares"]
    }


def _aura_payload(client, character) -> dict:
    """The one aura row the REST list returns for ``character`` (what the sheet's halo draws)."""
    response = client.get(f"{AURAS}?character={character.pk}")
    assert response.status_code == status.HTTP_200_OK, response.content
    (row,) = response.json()
    return row


class CreatingACharacterWithSeveralResonances(FinalizationTestMixin, JourneyCase):
    """Flow 1: Fury 6, Wonder 1, Domination 3 (Fury and Wonder are Primal, Domination Abyssal).

    Hand-worked from the shipped creation numbers (10 points, 10 lifetime per point): the
    picks seed 60 Fury, 10 Wonder and 30 Domination lifetime, so the aura is Primal 70 and
    Abyssal 30, and she begins settled exactly there. The spec's halo reads "a third
    abyssal" for 30 percent. No balance is granted by the seed.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="Several", height_min=700, height_max=800)
        cls.staff = AccountFactory(is_staff=True)
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.fury = ResonanceFactory(name="Fury", affinity=cls.primal)
        cls.wonder = ResonanceFactory(name="Wonder", affinity=cls.primal)
        cls.domination = ResonanceFactory(name="Domination", affinity=cls.abyssal)

    def _finalized_with(self, picks: list[tuple[Resonance, int]]):
        self.account = self.staff
        draft = self._create_base_draft(first_name="Several")
        # The picks go in the way the Gift stage sends them: a PATCH of the draft (which
        # merges its draft_data), so the stage's own validation is on the journey's path.
        picked = self.api(self.staff).patch(
            f"/api/character-creation/drafts/{draft.pk}/",
            {
                "draft_data": {
                    "gift_resonance_weights": [
                        {"resonance_id": resonance.pk, "weight": weight}
                        for resonance, weight in picks
                    ]
                }
            },
            format="json",
        )
        self.assertEqual(picked.status_code, status.HTTP_200_OK, picked.content)
        added = self.api(self.staff).post(
            f"/api/character-creation/drafts/{draft.pk}/add-to-roster/", {}, format="json"
        )
        self.assertEqual(added.status_code, status.HTTP_200_OK, added.content)
        return ObjectDB.objects.get(pk=added.json()["character_id"])

    def test_the_halo_the_resonances_and_the_gift_thread_all_follow_the_picks(self) -> None:
        character = self._finalized_with([(self.fury, 6), (self.wonder, 1), (self.domination, 3)])
        client = self.api(self.staff)

        payload = _aura_payload(client, character)
        shares = _share_rows(payload)
        # Not a fixed 80/20, and settled where she stands: nothing for her to atone for.
        self.assertEqual(
            shares, {"Primal": (Decimal(70), Decimal(70)), "Abyssal": (Decimal(30), Decimal(30))}
        )
        self.assertEqual(payload["dominant_affinity"], "Primal")
        self.assertIs(payload["unsettled"], False)
        self.assertEqual(payload["unsettled_line"], "")
        # What she reads of it: the aura verb says the same shares in words (the halo's own
        # sentence, "Mostly primal, a third abyssal", is drawn by the sheet from these).
        told = strip_ansi(self.telnet(character, "aura"))
        self.assertIn("Primal (most)", told)
        self.assertIn("Abyssal (a third)", told)
        self.assertIsNone(re.search(r"\d", told), told)

        held = client.get(f"/api/magic/character-resonances/?character_sheet={character.pk}")
        self.assertEqual(held.status_code, status.HTTP_200_OK, held.content)
        self.assertEqual(
            {
                row["resonance_name"]: (row["lifetime_earned"], row["balance"])
                for row in held.json()
            },
            {"Fury": (60, 0), "Wonder": (10, 0), "Domination": (30, 0)},
        )

        threads = client.get(f"{THREADS}?owner={character.pk}&target_kind=GIFT")
        self.assertEqual(threads.status_code, status.HTTP_200_OK, threads.content)
        (gift_thread,) = threads.json()["results"]
        # Every pick is on the one Gift thread with nothing imbued, the heaviest leading it.
        self.assertEqual(gift_thread["resonance_name"], "Fury")
        self.assertEqual(
            [
                (row["resonance_name"], row["amount"], row["leads"])
                for row in gift_thread["resonances"]
            ],
            [("Fury", 0, True), ("Domination", 0, False), ("Wonder", 0, False)],
        )

    def test_one_resonance_picks_make_a_wholly_that_affinity_aura(self) -> None:
        character = self._finalized_with([(self.domination, 10)])

        payload = _aura_payload(self.api(self.staff), character)

        self.assertEqual(_share_rows(payload), {"Abyssal": (Decimal(100), Decimal(100))})
        self.assertIs(payload["unsettled"], False)


class _TheLoom(JourneyCase):
    """Ysmay holds Fury (Primal), Domination (Abyssal) and Wonder (Celestial), 20 each, and a
    thread on her technique "Lantern Ward", level 20, that holds nothing imbued yet.

    The character is level 3, so her threads reach 30. Two staff-authored tier 1 pull perks
    exist for each of Fury and Domination (an intensity bump of 2 from thread level 0 and of 6
    from level 20); Wonder has none. A tier 1 pull costs 3 resonance and 1 anima.
    """

    def setUp(self) -> None:
        super().setUp()
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        CheckSystemSetupFactory.create()
        _make_resist_corruption_check_type()
        self.ritual = ImbuingRitualFactory()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.fury = ResonanceFactory(name="Fury", affinity=self.primal)
        self.domination = ResonanceFactory(name="Domination", affinity=self.abyssal)
        self.wonder = ResonanceFactory(name="Wonder", affinity=self.celestial)
        self.room = self.make_room("The Loom Room")
        self.scene = SceneFactory(room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)  # Gifted: the hedge gate
        set_primary_class_level(self.ysmay, CharacterClassFactory(), 3)
        CharacterAnimaFactory(character=self.sheet, current=30, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 500
        pool.maximum = 500
        pool.save()
        for resonance in (self.fury, self.domination, self.wonder):
            CharacterResonanceFactory(
                character_sheet=self.sheet, resonance=resonance, balance=20, lifetime_earned=20
            )
        self.technique = make_benign_castable_technique()
        self.technique.level = 3
        self.technique.save(update_fields=["level"])
        grant_technique(self.sheet.primary_persona, self.technique)
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.fury,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
            level=20,
            name="Loom Strand",
        )
        ThreadPullCostFactory(tier=1, resonance_cost=3, anima_per_thread=1)
        for resonance in (self.fury, self.domination):
            for min_level, amount in ((0, 2), (20, 6)):
                ThreadPullEffectFactory(
                    target_kind=TargetKind.TECHNIQUE,
                    resonance=resonance,
                    tier=1,
                    min_thread_level=min_level,
                    as_intensity_bump=True,
                    intensity_bump_amount=amount,
                )

    def balance(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).balance

    def imbue(self, resonance, amount: int):
        return self.api(self.account_of(self.ysmay)).post(
            PERFORM_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {
                    "thread_id": self.thread.pk,
                    "amount": amount,
                    "resonance_id": resonance.pk,
                },
                "components": [],
            },
            format="json",
        )

    def pull_options(self) -> dict[str, dict]:
        """What the Pull threads dialog lists for the thread: one option per paying resonance."""
        response = self.api(self.account_of(self.ysmay)).post(
            reverse("magic:thread-pull-preview"),
            {"character_sheet_id": self.sheet.pk, "tier": 1, "thread_ids": [self.thread.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (pulled,) = response.json()["per_thread"]
        return {row["resonance_name"]: row for row in pulled["options"]}

    def cast_with_pull(self, payer) -> dict:
        """Ysmay casts Lantern Ward with the thread pulled and ``payer`` paying for it."""
        response = self.api(self.account_of(self.ysmay)).post(
            reverse("sceneactionrequest-cast"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.sheet.primary_persona.pk,
                "technique_id": self.technique.pk,
                "pull": {
                    "tier": 1,
                    "thread_ids": [self.thread.pk],
                    "payers": {str(self.thread.pk): payer.pk},
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()


class ImbuingAndPullingTheMix(_TheLoom):
    """Flow 2: Fury and Domination imbued, then Pull threads read per paying resonance."""

    def test_each_payer_lists_its_own_perks_and_a_pull_applies_them(self) -> None:
        self.assertEqual(self.imbue(self.fury, 4).status_code, status.HTTP_200_OK)
        self.assertEqual(self.imbue(self.domination, 6).status_code, status.HTTP_200_OK)

        self.assertEqual(
            (self.balance(self.fury), self.balance(self.domination), self.balance(self.wonder)),
            (16, 14, 20),
        )
        thread = self.api(self.account_of(self.ysmay)).get(f"{THREADS}{self.thread.pk}/").json()
        # Domination has more imbued than Fury now, so it leads; the thread did not move level.
        self.assertEqual(thread["resonance_name"], "Domination")
        self.assertEqual(
            [(row["resonance_name"], row["amount"]) for row in thread["resonances"]],
            [("Domination", 6), ("Fury", 4)],
        )
        self.assertEqual(thread["level"], 20)

        options = self.pull_options()
        self.assertEqual(set(options), {"Fury", "Domination", "Wonder"})
        # Every authored perk at or under the level read applies. The leader reads the
        # thread's own level (20), so both its perks (2 and 6); Fury, which the thread also
        # carries, reads ten levels lower (10): only the level 0 perk (2). Wonder was never
        # imbued: it can pay, and has no perks.
        self.assertEqual(options["Domination"]["level_read"], 20)
        self.assertEqual([e["authored_value"] for e in options["Domination"]["effects"]], [2, 6])
        self.assertEqual(options["Fury"]["level_read"], 10)
        self.assertEqual([e["authored_value"] for e in options["Fury"]["effects"]], [2])
        self.assertEqual(options["Wonder"]["effects"], [])
        self.assertTrue(all(row["affordable"] for row in options.values()))

        def bump(body: dict) -> int:
            (entry,) = [
                e
                for e in body["result"]["power_ledger"]["entries"]
                if e["source_label"] == "thread power"
            ]
            return entry["amount"]

        # Pulling applies the payer's perks, each bumped by the level it reads divided by ten
        # (a thread rung per ten levels): Domination (2 + 6) x 2 = 16, Fury 2 x 1 = 2. The
        # payer is charged the tier's 3 and no other resonance is touched.
        by_domination = self.cast_with_pull(self.domination)
        self.assertEqual(bump(by_domination), 16)
        self.assertEqual(self.balance(self.domination), 14 - 3)
        by_fury = self.cast_with_pull(self.fury)
        self.assertEqual(bump(by_fury), 2)
        self.assertEqual(self.balance(self.fury), 16 - 3)
        self.assertEqual(self.balance(self.wonder), 20)

    def test_a_cast_pull_at_a_tier_with_no_cost_row_is_refused_in_a_sentence(self) -> None:
        """Only tier 1 has an authored cost row; the cast refuses tier 2 rather than 500."""
        response = self.api(self.account_of(self.ysmay)).post(
            reverse("sceneactionrequest-cast"),
            {
                "scene": self.scene.pk,
                "initiator_persona": self.sheet.primary_persona.pk,
                "technique_id": self.technique.pk,
                "pull": {"tier": 2, "thread_ids": [self.thread.pk]},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("That pull tier is not available yet.", str(response.json()))

    def test_a_resonance_never_imbued_pays_and_brings_no_perks(self) -> None:
        body = self.cast_with_pull(self.wonder)

        labels = [e["source_label"] for e in body["result"]["power_ledger"]["entries"]]
        self.assertNotIn("thread power", labels)
        self.assertEqual(self.balance(self.wonder), 20 - 3)
        self.assertEqual(self.balance(self.fury), 20)


class BecomingUnsettled(_Drifting):
    """Flow 3: Ysmay is settled Celestial 80 / Abyssal 20; 40 of her 100 lifetime resonance is
    Abyssal (her Ruin), 15 past the line and its tolerance of 5.

    The sheet reads her aura payload: unsettled, in the sentence the dialog shows, naming her
    Abyssal resonance. Her next cast rolls the focus check (difficulty 10 + 2 for each of the
    three steps past the line = 16). A settled character reads none of this.
    """

    def aura(self) -> dict:
        return _aura_payload(self.api(self.account_of(self.ysmay)), self.ysmay)

    def test_the_sheet_says_unsettled_and_the_next_cast_rolls_focus(self) -> None:
        payload = self.aura()
        self.assertIs(payload["unsettled"], True)
        self.assertEqual(
            payload["unsettled_line"],
            f"Your {self.abyssal_resonance.name} has grown strong enough to make you unsettled.",
        )
        self.assertEqual(payload["dominant_affinity"], "Celestial")
        self.watch(self.ysmay)

        rec = self.cast(focus="Failure")

        self.assertEqual(rec.focus_difficulties, [16])
        self.assertIsNotNone(self.conflict())
        self.assertTold(
            self.ysmay,
            f"Your {self.abyssal_resonance.name} has grown strong enough to make you unsettled",
        )
        self.assertTold(self.ysmay, f"You lose your focus as you work Lantern Ward: {CONFLICT}.")

    def web_cast_result(self, *, focus: str | None) -> dict:
        """Ysmay casts through the scene's web cast endpoint; the response's ``result``."""
        scene = Scene.objects.get(location_id=self.room.pk)
        body = {
            "scene": scene.pk,
            "initiator_persona": self.sheet.primary_persona.pk,
            "technique_id": self.technique.pk,
        }
        self.ysmay.resonances.invalidate()
        client = self.api(self.account_of(self.ysmay))
        if focus is None:
            response = client.post(reverse("sceneactionrequest-cast"), body, format="json")
        else:
            with force_check_outcome(CheckOutcome.objects.get(name=focus)):
                response = client.post(reverse("sceneactionrequest-cast"), body, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()["result"]

    def test_the_web_cast_result_carries_the_focus_lines_telnet_prints(self) -> None:
        self.watch(self.ysmay)
        intro = (
            f"Your {self.abyssal_resonance.name} has grown strong enough to make you unsettled. "
            "You must keep your focus."
        )
        lost = f"You lose your focus as you work Lantern Ward: {CONFLICT}."

        result = self.web_cast_result(focus="Failure")

        self.assertEqual(result["technique_result"]["focus_lines"], [intro, lost])
        self.assertTold(self.ysmay, intro)
        self.assertTold(self.ysmay, lost)

    def test_a_kept_focus_still_tells_her_to_keep_it_and_a_settled_cast_says_nothing(self) -> None:
        kept = self.web_cast_result(focus="Success")
        self.assertEqual(len(kept["technique_result"]["focus_lines"]), 1)
        self.assertIn("You must keep your focus.", kept["technique_result"]["focus_lines"][0])

        client = self.api(self.account_of(self.ysmay))
        accepted = client.post(f"{AURAS}{self.aura()['id']}/accept/")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)

        settled = self.web_cast_result(focus=None)
        self.assertEqual(settled["technique_result"]["focus_lines"], [])

    def test_accepting_ends_the_check(self) -> None:
        client = self.api(self.account_of(self.ysmay))
        payload = self.aura()

        done = client.post(f"{AURAS}{payload['id']}/accept/")

        self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)
        self.assertEqual(done.data["detail"], "You become more abyssal.")
        after = self.aura()
        self.assertIs(after["unsettled"], False)
        self.assertEqual(after["unsettled_line"], "")
        # Who she is moved to where she has got to, so the next cast rolls no focus at all.
        self.assertEqual(self.cast().focus_difficulties, [])
        self.assertIsNone(self.conflict())


@override_settings(SEED_SAMPLE_CONTENT=True)
class AtoningOrAccepting(DriftJourneyCase):
    """Flow 4. Ysmay is Celestial (settled 100/0/0) with 500 Dawnlight and 30 Ruin lifetime,
    and a tolerance of 5 points past her line.

    Hand-worked: 30 of 530 is 5.66 percent Abyssal, so she is unsettled. A Dawn Flourish deed
    of 20 makes it 30 of 550, 5.45 percent: 0.45 past the tolerance, which is 3 Ruin she
    may convert (rounded up, so a sliver past the line can still be atoned). The deed adds
    10 to her cap toward Dawnlight. Converting those 3 Ruin at the seeded Redemption rate 0.5
    gives int(1.5) = 1 Dawnlight, leaving 27 of 548, 4.93 percent: back under the line.
    Hobb, with 40 Ruin of 540 (7.41 percent) and no deed in a scene, can only accept.
    """

    def setUp(self) -> None:
        super().setUp()
        config = get_drift_config()
        config.unsettled_tolerance_percent = 5
        config.save()
        self.hobb_dawn = self.hold(self.hobb, self.dawnlight, 0, lifetime=500)
        self.hold(self.hobb, self.ruin, 40)
        set_aura_split(
            CharacterAuraFactory(character=self.hobb.sheet_data),
            celestial="100",
            primal="0",
            abyssal="0",
        )

    def aura(self, character) -> dict:
        return _aura_payload(self.api(self.account_of(character)), character)

    def test_a_deed_in_the_scene_offers_atone_and_atoning_settles_her(self) -> None:
        self.connect_telnet(self.ysmay)
        self.watch(self.ysmay)
        self.assertIs(self.aura(self.ysmay)["unsettled"], True)
        offering = self.carry(self.ysmay, self.dawnlight, "Dawn-gold Thread")
        self.deed(self.ysmay)
        self.assertIn(NOTICE, strip_ansi(self.said(self.ysmay)))

        ysmay_api = self.api(self.account_of(self.ysmay))
        (offer,) = ysmay_api.get(PENDING).data["results"]
        (cap,) = offer["caps"]
        self.assertEqual(cap["target_resonance"]["name"], "Dawnlight")
        self.assertEqual(cap["cap_remaining"], 10)
        (source,) = cap["sources"]
        self.assertEqual((source["resonance_name"], source["max_amount"]), ("Ruin", 3))

        with force_check_outcome(self.outcomes["Success"]):
            done = post(
                ysmay_api,
                CONVERT,
                {
                    "offer_id": offer["id"],
                    "source_resonance_id": self.ruin.pk,
                    "target_resonance_id": self.dawnlight.pk,
                    "amount": 3,
                    "component_ids": [offering],
                },
            )
        self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)
        self.assertEqual((done.data["converted_amount"], done.data["granted_amount"]), (3, 1))
        payload = self.aura(self.ysmay)
        self.assertIs(payload["unsettled"], False)
        self.assertEqual(payload["unsettled_line"], "")
        self.assertNotIn("unsettled", strip_ansi(self.telnet(self.ysmay, "aura")))

    def test_outside_a_scene_there_is_only_accept_and_it_ends_the_unsettled_state(self) -> None:
        hobb_api = self.api(self.account_of(self.hobb))
        before = self.aura(self.hobb)
        self.assertIs(before["unsettled"], True)
        self.assertIn(
            "Your Ruin has grown strong enough to make you unsettled.",
            strip_ansi(self.telnet(self.hobb, "aura")),
        )
        self.assertEqual(hobb_api.get(PENDING).data["results"], [])
        # Her Abyssal streak is no part of who she is: not even a share row for it yet.
        self.assertNotIn("Abyssal", _share_rows(before))

        done = hobb_api.post(f"{AURAS}{before['id']}/accept/")

        self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)
        self.assertEqual(done.data["detail"], "You become more abyssal.")
        after = self.aura(self.hobb)
        self.assertIs(after["unsettled"], False)
        self.assertEqual(after["unsettled_line"], "")
        self.assertNotIn("unsettled", strip_ansi(self.telnet(self.hobb, "aura")))
        # 40 of 540 is 7.41: who she is moved up to where she has got to, the line with it.
        self.assertEqual(_share_rows(after)["Abyssal"], (Decimal("7.41"), Decimal("7.41")))
        self.assertEqual(after["dominant_affinity"], "Celestial")


class ASineaterTakesTheMire(JourneyCase):
    """Flow 5. Ysmay is settled wholly Celestial, with 700 Dawnlight lifetime, and as a bonded
    Sineater takes Ruin (Abyssal) from her Sinner's Mire the way a Sineating does: a grant
    from the Sineating source flagged as Mire.

    Hand-worked with the shipped allowance of 30 percent of all lifetime resonance: 200 Mire
    of 900 is 22 percent, a fifth, inside it, and the Mire is kept apart from her own share
    (her own Abyssal is 0), so she is not unsettled. A further 200 makes 400 of 1100, 36 percent,
    6 past the allowance: unsettled by her Ruin. Accepting makes the Mire her own: the aura
    shows it as her Abyssal share (36.36) and no Mire remains.
    """

    def setUp(self) -> None:
        super().setUp()
        Affinity.objects.clear_cache()
        self.celestial, _primal, self.abyssal = ensure_canonical_affinities()
        self.dawnlight = ResonanceFactory(name="Dawnlight", affinity=self.celestial)
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.room = self.make_room("The Mire Edge")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        set_aura_split(
            CharacterAuraFactory(character=self.sheet), celestial="100", primal="0", abyssal="0"
        )
        _hold(self.sheet, self.dawnlight, 700)
        self.client = self.api(self.account_of(self.ysmay))

    def take(self, units: int) -> None:
        grant_resonance(self.sheet, self.ruin, units, source=GainSource.SINEATING, from_mire=True)

    def aura(self) -> dict:
        return _aura_payload(self.client, self.ysmay)

    def test_the_mire_shows_apart_and_unsettles_only_past_the_allowance(self) -> None:
        self.take(200)

        inside = self.aura()
        self.assertEqual(inside["mire_share_words"], "a fifth")
        self.assertIs(inside["unsettled"], False)
        self.assertEqual(inside["unsettled_line"], "")

        self.take(200)

        past = self.aura()
        self.assertEqual(past["mire_share_words"], "a third")
        self.assertIs(past["unsettled"], True)
        self.assertEqual(
            past["unsettled_line"], "Your Ruin has grown strong enough to make you unsettled."
        )

        done = self.client.post(f"{AURAS}{past['id']}/accept/")

        self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)
        after = self.aura()
        self.assertIs(after["unsettled"], False)
        self.assertEqual(after["mire_share_words"], "none")
        self.assertEqual(_share_rows(after)["Abyssal"], (Decimal("36.36"), Decimal("36.36")))
        row = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.ruin)
        self.assertEqual((row.lifetime_earned, row.mire_lifetime), (400, 0))


class RetuningAThreadOnTheWeb(ThreadRetuneCase):
    """Flow 6. Ysmay's thread on Ruin (Abyssal) holds 40 developed points, all Ruin, at level
    20. She retunes 5 of its Ruin to Dread, another Abyssal resonance (the same affinity, so
    one point for one). The level and the developed points do not move; the thread now holds
    35 Ruin and 5 Dread, still led by Ruin; and Pull threads lists Dread's perk, which it
    could not before because the thread held nothing of Dread.
    """

    def setUp(self) -> None:
        super().setUp()
        self.dread = ResonanceFactory(name="Dread", affinity=self.abyssal)
        self.thread = ThreadFactory(
            owner=self.sheet, resonance=self.ruin, developed_points=40, level=20
        )
        for resonance in (self.ruin, self.dread):
            CharacterResonanceFactory(
                character_sheet=self.sheet, resonance=resonance, balance=10, lifetime_earned=10
            )
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.dread,
            tier=1,
            min_thread_level=0,
            flat_bonus_amount=3,
        )

    def dread_perks(self) -> list[int]:
        response = self.api(self.account_of(self.ysmay)).post(
            reverse("magic:thread-pull-preview"),
            {"character_sheet_id": self.sheet.pk, "tier": 1, "thread_ids": [self.thread.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (pulled,) = response.json()["per_thread"]
        (dread,) = [row for row in pulled["options"] if row["resonance_name"] == "Dread"]
        return [effect["authored_value"] for effect in dread["effects"]]

    def test_retune_part_of_a_row(self) -> None:
        offering = self.carry(self.ysmay, self.dread, "Dread Shard")
        self.assertEqual(self.dread_perks(), [])
        threads_before = Thread.objects.filter(owner=self.sheet, retired_at__isnull=True).count()

        response = self.api(self.account_of(self.ysmay)).post(
            PERFORM_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.rite.pk,
                "kwargs": {
                    "thread_id": self.thread.pk,
                    "from_resonance": self.ruin.pk,
                    "target_resonance": self.dread.pk,
                    "amount": 5,
                },
                "components": [offering],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertIn(
            "moved 5 Ruin into Dread. It now holds 35 Ruin and 5 Dread.",
            response.data["message"],
        )
        self.assertEqual(rows(self.thread), {"Ruin": 35, "Dread": 5})
        # Never a level change, never a second thread.
        thread = stored(self.thread)
        self.assertEqual((thread["level"], thread["developed_points"]), (20, 40))
        self.assertEqual(thread["resonance_id"], self.ruin.pk)
        self.assertEqual(
            Thread.objects.filter(owner=self.sheet, retired_at__isnull=True).count(),
            threads_before,
        )
        self.assertTrue(consumed(offering))
        shown = self.api(self.account_of(self.ysmay)).get(f"{THREADS}{self.thread.pk}/").json()
        self.assertEqual(
            [(row["resonance_name"], row["amount"]) for row in shown["resonances"]],
            [("Ruin", 35), ("Dread", 5)],
        )
        # Dread's perk is listed now: the level read is ten under the thread's own (10).
        self.assertEqual(self.dread_perks(), [3])
