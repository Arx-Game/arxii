"""Fuzz: a technique dodge at low anima never refuses and never lets anima go negative
(#5066 decisions 5 and 13).

Ondrelle is the dodging journeys' blink dodger (``_TheCellar``): each automatic dodge is a
cast of Blink Step (2 anima). Hypothesis picks her anima (0 to 3), how many blades attack
her in one round (1 to 4), the technique roll's success level, and whether her "dodge even
into Soulfray" box is ticked. The properties, from the spec, judged on the round's result:

- the round resolves without raising;
- with the box ticked, every attack is answered by a dodge (lack of anima never refuses
  magic; the overspend becomes Soulfray);
- with it unticked, a dodge that would overspend does not happen, so she never pays more
  than she held;
- her anima never goes below 0.

Each example runs in its own transaction; the shared rows built in ``setUp`` are loaded again
first (``fresh``).
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from integration_tests.test_dodging_journeys import RecordingRoll, _TheCellar
from world.combat.models import CombatEncounter, CombatParticipant
from world.magic.models.anima import CharacterAnima

BLINK_COST = 2


class DodgingAtLowAnima(HypothesisTestCase, _TheCellar):
    def setUp(self) -> None:
        super().setUp()
        self.ondrelle = self.fighter("Ondrelle", at=self.stage, blinks=True)

    def fresh(self, anima: int, into_soulfray: bool) -> None:
        self.encounter = CombatEncounter.objects.get(pk=self.encounter.pk)
        seat = CombatParticipant.objects.get(pk=self.participants[self.ondrelle.pk].pk)
        seat.dodge_into_soulfray = into_soulfray
        seat.save(update_fields=["dodge_into_soulfray"])
        pool = CharacterAnima.objects.get(character=self.ondrelle.sheet_data)
        pool.current = anima
        pool.save(update_fields=["current"])

    @settings(deadline=None)
    @given(
        anima=st.integers(min_value=0, max_value=3),
        attackers=st.integers(min_value=1, max_value=4),
        level=st.integers(min_value=-1, max_value=3),
        into_soulfray=st.booleans(),
    )
    def test_never_refused_never_negative(
        self, anima: int, attackers: int, level: int, into_soulfray: bool
    ) -> None:
        self.fresh(anima, into_soulfray)
        for index in range(attackers):
            self.blade(f"Blade {index}", at=self.gallery)
        self.technique_level = level
        roll = RecordingRoll(*([2] * attackers))

        self.resolve(roll)

        left = self.anima(self.ondrelle)
        self.assertGreaterEqual(left, 0)
        dodged = self.participant(self.ondrelle).reactions_used
        if into_soulfray:
            self.assertEqual(dodged, attackers)
        else:
            self.assertLessEqual(dodged * BLINK_COST, anima)
