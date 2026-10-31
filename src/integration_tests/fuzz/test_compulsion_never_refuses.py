"""Fuzz: a compulsion never refuses a player character an action (#4802, ruling 14).

Mira is Berserk in a fight with a Bandit Captain (the ``_CompelledMira`` journey cast).
Hypothesis picks what she declares, on telnet or the web, and the outcome of the resist
roll the round then makes. The properties are the owner's ruling, judged on what she was
told and what the round did:

- the declare seam accepts the declaration (it never answers with a refusal);
- the round resolves without raising, whatever the resist roll came to;
- afterwards she either kept the action she declared, or was told the rage won out.

Each example runs in its own transaction, so the round it resolves is rolled back; the
shared rows built in ``setUp`` are loaded again first (``fresh``).
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from integration_tests.test_losing_control_journeys import _CompelledMira
from world.checks.test_helpers import force_check_outcome
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant
from world.conditions.berserk_content import outcome_at_level

# Every one is a declaration an uncompelled Mira can make in this fight.
TELNET_LINES = (
    "combat flee",
    "combat parley Bandit Captain",
    "cast Claw at Bandit Captain",
    "cast Mend",
)
WEB_KEYS = ("combat_flee", "combat_parley")
REFUSALS = ("Could not", "Cannot", "cannot", "will not", "You can't")


class ACompulsionNeverRefuses(HypothesisTestCase, _CompelledMira):
    def fresh(self) -> None:
        """Load the shared rows again: the identity map is emptied between examples, and
        a round leaves its writes on the old instances after the rollback."""
        self.encounter = CombatEncounter.objects.get(pk=self.encounter.pk)
        self.seat = CombatParticipant.objects.get(pk=self.seat.pk)
        self.captain = CombatOpponent.objects.get(pk=self.captain.pk)
        # A broken captain can be parleyed with (and may run before the rage reaches him,
        # which only cancels a lost declaration).
        self.captain.morale = 0
        self.captain.save(update_fields=["morale"])
        self._mailboxes.pop(self.mira.pk, None)
        self.mira = ObjectDB.objects.get(pk=self.mira.pk)
        self.watch(self.mira)

    def declare(self, seam: str, choice: str) -> None:
        if seam == "telnet":
            told = self.telnet(self.mira, choice)
            for refusal in REFUSALS:
                self.assertNotIn(refusal, told, f"{choice!r} was refused: {told!r}")
            return
        kwargs = {"opponent_id": self.captain.pk} if choice == "combat_parley" else {}
        result = self.web(self.mira, choice, **kwargs)
        self.assertTrue(result.detail.success, f"{choice!r} was refused: {result.detail.message}")

    @settings(max_examples=20, deadline=None)
    @given(
        st.one_of(
            st.tuples(st.just("telnet"), st.sampled_from(TELNET_LINES)),
            st.tuples(st.just("web"), st.sampled_from(WEB_KEYS)),
        ),
        st.sampled_from((-2, -1, 0, 1, 2)),
    )
    def test_any_declaration_stands_or_the_rage_wins_out(
        self, declaration: tuple[str, str], level: int
    ) -> None:
        self.fresh()
        seam, choice = declaration
        self.declare(seam, choice)
        before = self.declared()
        self.assertIsNotNone(before, f"{choice!r} left no declaration")
        declared_as = (before.maneuver, before.focused_action_id)

        with force_check_outcome(outcome_at_level(level)):
            self.resolve()

        after = self.declared()
        kept = after is not None and (after.maneuver, after.focused_action_id) == declared_as
        if not kept:
            self.assertTold(self.mira, "Berserk wins out:")
