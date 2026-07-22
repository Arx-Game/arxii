"""E2E journey test: 3-PC party vs a factory-composed boss (#2095).

Walks the full DoD beat sequence via ``resolve_round`` against a
``BossFightScenarioFactory``-built encounter: solo-spam mitigation -> combo
break-bar break -> vulnerability window -> phase 2 transition (reinforcement
adds) -> phase 3 transition (enrage) -> a break-bar re-break -> the party
finishing the boss off while still inside the reopened vulnerability window.

Round-by-round numeric derivation (all authored, not tuned by trial and
error — see ``BossFightScenarioFactory`` in ``world/combat/factories.py``
for the underlying config). Break-bar depletion uses the #2642
diversity-weighted formula (``assess_break_bar``): 1 unit per distinct
(actor, kind) pair this round, doubled to 2 for a (kind, effect_type) pair's
first-ever occurrence in the encounter, plus a landed combo's flat
``bonus_damage``, undivided here (no lieutenants — ``reinforces`` is unset —
so the #2642 gate divisor is always 1):

- Phase 1: ``soak_value=15``, ``break_bar_threshold=10`` (raised from the
  pre-#2642 6 so round 1's now-larger novelty-loaded depletion doesn't
  prematurely open the vulnerability window — see round 1 below). Each PC's
  technique deals ``base_damage=10`` (``EffectType.base_power=10``, no
  intensity/SL scaling, ``DamageSuccessLevelMultiplier`` seeded at
  ``min_success_level=1`` -> ``1.00``). ``apply_damage_to_opponent``'s
  ``damage_through = max(0, raw - soak - resistance)`` -> ``10 - 15 = 0`` for
  a solo hit: fully soaked while the guard is unbroken.
- Round 1: 3 PCs solo-attack (no combo) -> 0 damage through each -> boss
  health unchanged (100). Each PC's outcome still "damaged" the boss per
  ``_outcome_damaged_boss`` (which only checks that a result references the
  boss, not that damage_through > 0), persisting 3 DAMAGE
  ``BreakBarContribution`` rows — 3 distinct (actor, DAMAGE) pairs (3 base
  units), each pair's effect_type the encounter's first occurrence (+3
  novelty bonus) -> 6 raw depletion -> break bar 10 -> 4 (not asserted;
  crucially still > 0, so the vulnerability window stays closed and round 2's
  damage math is unaffected). Also two NPC attacks are resolved directly via
  ``_resolve_npc_action`` (proven pattern — see
  ``test_defense_sourcing.DefenseCheckSourcingTests``) against a fixed
  ``defense_check_fn`` (``success_level=0`` -> ``DEFENSE_FULL_MULTIPLIER``
  1.0, isolating ``opponent.damage_multiplier`` as the only variable): the
  flat entry (``base_damage=12``) establishes the pre-enrage damage baseline
  (``12``), and the ``conditions_applied`` entry (``base_damage=8``) proves
  enemy-NPC condition application onto a PC (see the DoD-wording-discrepancy
  note below).
- Round 2: PC1+PC2 upgrade to the learned combo (``bonus_damage=10``,
  ``bypass_soak=True``); PC3 solo. Combo riders bypass soak entirely
  (``2 x 10 = 20`` damage through); each PC's own technique is still soaked
  to 0. Health 100 -> 80. All 3 PCs still register a DAMAGE row (as round 1);
  the combo also persists its own COMBO row (1 more base unit), and (COMBO,
  effect_type) is a first-ever pair this encounter (+1 novelty bonus) -> 4
  base + 1 novelty + 10 ``bonus_damage`` = 15 raw depletion against
  ``break_bar_current=4`` -> clamped to 0 -> ``vulnerability_rounds_remaining
  = vulnerability_rounds = 2``. No phase transition yet (80% > phase 2's 70%
  trigger), so this vulnerability write survives past round 2 untouched —
  the DoD's "vulnerability window opens" beat is asserted right here.
- Round 3: vulnerability decremented 2 -> 1 at the top of the round (still
  active for this round's own actions) -> soak is fully bypassed
  (``_effective_soak_for_opponent`` returns 0 when vulnerable) -> 3 PCs solo
  now deal their full ``10`` raw damage each -> 30 through. Health 80 -> 50
  (50%), crossing phase 2's ``health_trigger_percentage=0.70`` ->
  ``check_and_advance_boss_phase`` transitions 1 -> 2 at the end of this same
  round: reinforcements spawn (``reinforcement_count=2``) and the break bar
  is re-stamped from phase 2's config (``threshold=1``) — which, per
  ``_stamp_break_bar``, *always* resets ``vulnerability_rounds_remaining`` to
  0 regardless of branch. That reset happens only after round 3's own damage
  was already applied, so it doesn't retroactively undo anything asserted at
  round 2.
- Round 4: PC1+PC2 combo again (``2 x 10 = 20`` bypass-soak damage; PC3 solo
  vs phase 2's ``soak_value=20`` -> 0). Health 50 -> 30 (30%), crossing phase
  3's ``health_trigger_percentage=0.30`` -> transition 2 -> 3: enrage
  (``damage_multiplier=2.50``) is stamped, and the break bar resets again
  (phase 3's own ``threshold=1``). ``assess_break_bar`` also runs earlier in
  this same round (phase 2's bar is unvulnerable entering round 4, since
  round 3's phase transition reset ``vulnerability_rounds_remaining`` to 0)
  and would break phase 2's 1-unit bar on its own — but that write is
  immediately overwritten by the phase-3 transition's ``_stamp_break_bar``
  call later the same round, so it's not separately observable.
- Round 5: no combo — the DAMAGE feed alone (3 actors, none novel — all 3
  effect_types were already established in round 1) chips phase 3's tiny bar
  from 1 -> 0 (3 raw units, clamped) -> ``vulnerability_rounds_remaining =
  2`` (a *second* window, opened in the final phase — nothing will transition
  again to reset it, since phase 3 is the last authored phase). A second
  direct ``_resolve_npc_action`` call with the same flat entry now applies
  ``int(12 * 2.50) = 30`` damage — 2.5x the round-1 baseline of 12,
  demonstrating the enrage delta via a real damage comparison, not just a
  field read.
- Round 6: vulnerability decremented 2 -> 1 (still active this round) -> 3
  PCs solo-attack unsoaked (phase 3's ``soak_value=10`` is bypassed) ->
  ``3 x 10 = 30`` damage through, exactly zeroing the boss's remaining 30
  health -> ``OpponentStatus.DEFEATED``. Because the boss dies mid
  action-resolution, ``assess_break_bar``/``_check_boss_transitions`` (which
  both filter ``status=ACTIVE``) never run again for it that round, so
  ``vulnerability_rounds_remaining`` is left exactly as the top-of-round
  decrement set it: 1 (> 0) — proving the kill landed *inside* the
  vulnerability window, not merely after a health check happened to cross 0.

DoD-wording discrepancy (documented per the task instructions rather than
forced into a wrong assertion): the issue's beat 5 says "condition applied to
the boss (enemy-NPC condition application proof via
``ThreatPoolEntry.conditions_applied``)". Reading the resolution path
(``_resolve_npc_action_on_target`` in ``world/combat/services.py``) shows
``conditions_applied`` conditions from an NPC's threat entry land on the *PC*
target of that NPC's attack, never on the NPC/boss itself — there is no code
path that lets a PC's incoming damage apply a threat-entry condition back
onto the attacking boss. Task 1's own spec text is accurate here ("enemy-NPC
condition application is provable via the resolution path"); only beat 5's
"to the boss" phrasing is imprecise. This test proves the mechanism as it
actually works: an NPC (boss) attack with ``conditions_applied`` lands that
condition on the targeted PC.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from world.combat.constants import OpponentStatus, OpponentTier
from world.combat.factories import BossFightScenarioFactory
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import _resolve_npc_action, resolve_round, upgrade_action_to_combo
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.conditions.models import ConditionInstance
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _offense_check_fn(*args: object, **kwargs: object) -> MagicMock:
    """Fixed success_level=1 -> DamageSuccessLevelMultiplier's 1.00 row."""
    return MagicMock(success_level=1)


def _defense_check_fn(*args: object, **kwargs: object) -> MagicMock:
    """Fixed success_level=0 -> DEFENSE_FULL_MULTIPLIER (1.0), isolating enrage."""
    return MagicMock(success_level=0)


class BossFightJourneyTest(TestCase):
    """3-PC party vs a factory-composed boss: the full break-bar/phase/enrage journey."""

    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )

    def setUp(self) -> None:
        super().setUp()
        self.scenario = BossFightScenarioFactory.create(num_pcs=3)
        self.encounter = self.scenario.encounter
        self.opponent = self.scenario.opponent
        self.participants = self.scenario.participants
        self.techniques = self.scenario.techniques
        self.combo = self.scenario.combo

    def _declare_round(
        self, round_number: int, *, combo_pcs: tuple[int, ...] = ()
    ) -> list[CombatRoundAction]:
        """Declare one solo/combo focused action per PC for the given round.

        ``resolve_round`` always transitions the encounter to BETWEEN_ROUNDS
        (or COMPLETED) on return, so every round after the first must reopen
        DECLARING before actions can be resolved again.
        """
        if round_number > 1:
            self.encounter.refresh_from_db()
            self.encounter.round_number = round_number
            self.encounter.status = RoundStatus.DECLARING
            self.encounter.save(update_fields=["round_number", "status"])
        actions = []
        for i, (participant, technique) in enumerate(
            zip(self.participants, self.techniques, strict=True)
        ):
            action = CombatRoundAction.objects.create(
                participant=participant,
                round_number=round_number,
                focused_category=technique.action_category,
                focused_action=technique,
                focused_opponent_target=self.opponent,
            )
            if i in combo_pcs:
                upgrade_action_to_combo(action, self.combo)
            actions.append(action)
        return actions

    def _resolve(self) -> object:
        return resolve_round(
            self.encounter,
            offense_check_fn=_offense_check_fn,
        )

    def test_boss_fight_journey(self) -> None:  # noqa: PLR0915 - one linear journey walk
        """Walk every DoD beat in order: mitigation -> break -> vuln -> phase 2 ->
        phase 3 (enrage) -> re-break -> win inside the reopened vulnerability window.
        """
        # --- Round 1: solo spam. Damage fully soaked while the guard is unbroken. ---
        self._declare_round(1)
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 100, "phase-1 soak should fully mitigate solo hits")
        self.assertEqual(self.opponent.current_phase, 1)

        # Baseline enrage measurement (opponent.damage_multiplier is still 1.0):
        # a direct NPC attack via the flat threat entry, forced to a fixed
        # success_level=0 defense roll so only the enrage multiplier varies.
        baseline_action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            round_number=1,
            threat_entry=self.scenario.flat_entry,
        )
        baseline_action.targets.add(self.participants[2])
        _resolve_npc_action(
            self.opponent,
            baseline_action,
            defense_check_type=None,
            defense_check_fn=_defense_check_fn,
        )
        pc3_sheet = self.participants[2].character_sheet
        pc3_vitals = CharacterVitals.objects.get(character_sheet=pc3_sheet)
        baseline_damage = 100 - pc3_vitals.health
        self.assertEqual(baseline_damage, 12, "pre-enrage NPC hit should be flat base_damage")

        # Enemy-NPC condition application: the boss's Venom Bite entry
        # (conditions_applied=[condition_template]) landing on a PC target.
        condition_action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            round_number=1,
            threat_entry=self.scenario.condition_entry,
        )
        condition_action.targets.add(self.participants[0])
        _resolve_npc_action(
            self.opponent,
            condition_action,
            defense_check_type=None,
            defense_check_fn=_defense_check_fn,
        )

        # --- Round 2: combo lands. Break bar hits 0; vulnerability window opens. ---
        self._declare_round(2, combo_pcs=(0, 1))
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.break_bar_current, 0)
        self.assertGreater(self.opponent.vulnerability_rounds_remaining, 0)
        self.assertEqual(self.opponent.health, 80)
        self.assertEqual(self.opponent.current_phase, 1, "phase-2 trigger not yet crossed")

        # --- Round 3: vulnerable — soak bypassed. Phase 2 transition: adds spawn. ---
        self._declare_round(3)
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 50)
        self.assertEqual(self.opponent.current_phase, 2)
        reinforcement_count = self.opponent.encounter.opponents.filter(
            tier=OpponentTier.MOOK,
            name=self.scenario.reinforcement_template.name,
        ).count()
        self.assertEqual(reinforcement_count, 2, "phase-2 transition should spawn its adds")

        # --- Round 4: combo again crosses phase 3's trigger. Enrage stamped. ---
        self._declare_round(4, combo_pcs=(0, 1))
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 30)
        self.assertEqual(self.opponent.current_phase, 3)
        self.assertEqual(self.opponent.damage_multiplier, Decimal("2.50"))

        # Enrage proof via a real damage comparison against the round-1 baseline.
        enrage_action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            round_number=4,
            threat_entry=self.scenario.flat_entry,
        )
        enrage_action.targets.add(self.participants[2])
        _resolve_npc_action(
            self.opponent,
            enrage_action,
            defense_check_type=None,
            defense_check_fn=_defense_check_fn,
        )
        pc3_vitals.refresh_from_db()
        enraged_damage = (100 - baseline_damage) - pc3_vitals.health
        self.assertEqual(enraged_damage, 30, "enraged hit should be 2.50x the base_damage")
        expected_enraged = int(self.scenario.flat_entry.base_damage * Decimal("2.50"))
        self.assertEqual(enraged_damage, expected_enraged)

        # Enemy-NPC condition application (round 1's Venom Bite hit PC1 — see the
        # module docstring's DoD-wording-discrepancy note: conditions_applied
        # flows NPC-attack -> PC target, never PC/boss-ward, so this proves the
        # mechanism as it actually works rather than forcing the issue's literal
        # "to the boss" phrasing).
        pc1_character = self.participants[0].character_sheet.character
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=pc1_character,
                condition=self.scenario.condition_template,
            ).exists(),
            "the boss's conditions_applied threat entry should land its condition on the PC target",
        )

        # --- Round 5: re-break phase 3's bar via the distinct-chip path (no combo
        # needed) -> a second, final vulnerability window opens. ---
        self._declare_round(5)
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.break_bar_current, 0)
        self.assertEqual(self.opponent.vulnerability_rounds_remaining, 2)
        self.assertEqual(self.opponent.current_phase, 3, "no further phase to transition into")

        # --- Round 6: vulnerable again — the party finishes the boss off. ---
        self._declare_round(6)
        self._resolve()

        self.opponent.refresh_from_db()
        self.assertEqual(self.opponent.health, 0)
        self.assertEqual(self.opponent.status, OpponentStatus.DEFEATED)
        self.assertGreater(
            self.opponent.vulnerability_rounds_remaining,
            0,
            "the killing blow should have landed while still inside the vulnerability window",
        )
