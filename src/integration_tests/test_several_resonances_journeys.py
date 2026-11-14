"""Journeys through the telnet face of several resonances (#5123).

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
"""

from __future__ import annotations

import re

from evennia.utils.ansi import strip_ansi

from integration_tests.harness import JourneyCase
from integration_tests.test_resonance_strain_journeys import _BurningResonance
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.classes.factories import CharacterClassFactory
from world.classes.services import set_primary_class_level
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import Affinity, CharacterResonance, ThreadResonance
from world.magic.models.aura import CharacterAuraShare


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
        self.cast(f"{self.thread.name}:{self.ember.name}")

        self.assertEqual(self.balance(self.ysmay, self.ember), 10 - 1)
        self.assertEqual(self.balance(self.ysmay, self.veil), 10)

    def test_a_bare_pull_is_paid_by_the_leading_resonance(self) -> None:
        self.cast(self.thread.name)

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
        # Three points at a point a level (stored level 0): the thread climbs three levels.
        self.assertEqual(self.thread.level, 3)

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

    def test_threads_lists_the_mix_in_words(self) -> None:
        self.imbue("amount=3 resonance=ember")
        self.thread.refresh_from_db()
        self.imbue("amount=1 resonance=veil")

        told = strip_ansi(self.telnet(self.ysmay, "threads"))

        # 3 Ember and 1 Veil: Ember holds three quarters ("most"), Veil a quarter ("a fifth").
        self.assertIn("Ember (most), Veil (a fifth)", told)
