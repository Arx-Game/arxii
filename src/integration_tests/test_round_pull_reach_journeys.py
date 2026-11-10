"""A thread pull boosts only the uses its threads relate to (#5066 slice 1).

Ysmay knows two techniques: Shadow Step and Ember Lash. She has one thread, woven on
Shadow Step, whose tier-1 pull adds 2 to the roll (a flat bonus) and 3 to the power (an
intensity bump). A pull lasts the round, but the maintainer ruled (decision 14 of #5066)
that it boosts only what it relates to: a thread on Shadow Step reaches a cast of Shadow
Step, never a cast of Ember Lash.

Both rounds are declared the way the web client sends them (``dispatch``), resolved by
``resolve_round``, and read back the way the combat log's outcome panel reads them
(``GET /api/combat/action-outcome-details/``, whose power ledger is her cast's own). The
roll's flat bonus is the labelled "Combat pull" line the offense roll's modifier breakdown
carries; nothing persists that breakdown, so the journey reads it as the resolver hands it
to the modifier seam.

- Related: she casts Shadow Step and pulls the thread with it. The cast's ledger shows
  "combat pulls" +3 and its roll carries "Combat pull" +2.
- Unrelated: she casts Ember Lash and puts the same pull on a clash contribution with
  Shadow Step (as the client sends it when a clash is chosen). Ember Lash's ledger has no
  "combat pulls" line and its roll no "Combat pull" line. Before the fix it had both.
"""

from __future__ import annotations

from unittest.mock import patch

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat import services as combat_services
from world.combat.constants import ActionCategory, ClashActionSlot, ClashStatus, OpponentTier
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatPull, CombatRoundAction
from world.combat.services import resolve_round
from world.fatigue.constants import EffortLevel
from world.magic.constants import EffectKind, PowerStage, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.services import ensure_canonical_check_outcome
from world.vitals.models import CharacterVitals

FLAT_BONUS = 2
INTENSITY_BUMP = 3


class APullBoostsOnlyWhatItRelatesTo(JourneyCase):
    """Decision 14 of #5066: a round's pull reaches a use only through related threads."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        for name in CANONICAL_OUTCOME_LEVELS:  # a clash round grades its result on these
            ensure_canonical_check_outcome(name)
        ClashConfigFactory()
        room = self.make_room("The Ashen Court")
        SceneFactory(room=room)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=room
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=500,
            max_health=500,
            threat_pool=pool,
        )

        self.ysmay = self.make_player("Ysmay", room=room)
        sheet = self.ysmay.sheet_data
        CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        CharacterEngagementFactory(character=sheet)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )

        self.shadow_step = self.technique("Shadow Step")
        self.ember_lash = self.technique("Ember Lash")
        for technique in (self.shadow_step, self.ember_lash):
            CharacterTechniqueFactory(character=sheet, technique=technique)

        self.resonance = ResonanceFactory()
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=FLAT_BONUS,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=1,
            min_thread_level=1,
            as_intensity_bump=True,
            intensity_bump_amount=INTENSITY_BUMP,
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=self.resonance, balance=10, lifetime_earned=10
        )
        self.thread = ThreadFactory(
            owner=sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.shadow_step,
            # Stored x10: shows as level 1, so both tier-1 rows apply at a x1 multiplier.
            level=10,
            name="Shadow Strand",
        )

    @staticmethod
    def technique(name: str):
        """A clash-capable technique rolled on its own check, one stat of its own."""
        check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check, trait=StatTraitFactory(), weight=1)
        return TechniqueFactory(
            name=name,
            gift=GiftFactory(),
            intensity=10,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check),
            clash_capable=True,
        )

    # -- the web client's declarations ------------------------------------------

    def dispatch(self, ref: dict, kwargs: dict) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api(self.account_of(self.ysmay)).post(
                f"/api/actions/characters/{self.ysmay.pk}/dispatch/",
                {"ref": ref, "kwargs": kwargs},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)

    def pull_kwargs(self) -> dict:
        return {
            "pull_resonance_id": self.resonance.pk,
            "pull_tier": 1,
            "pull_thread_ids": [self.thread.pk],
        }

    def cast(self, technique, *, with_pull: bool) -> None:
        kwargs = {
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target_id": self.opponent.pk,
            "confirm_soulfray_risk": True,
        }
        if with_pull:
            kwargs |= self.pull_kwargs()
        self.dispatch(
            {"backend": "combat", "technique_id": technique.pk, "action_slot": "focused"},
            kwargs,
        )

    def clash_with_pull(self, technique) -> None:
        clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )
        self.dispatch(
            {
                "backend": "combat",
                "clash_id": clash.pk,
                "clash_action_slot": ClashActionSlot.FOCUSED,
            },
            {"technique_id": technique.pk, "strain_commitment": 0, **self.pull_kwargs()},
        )

    # -- what the round did --------------------------------------------------------

    def resolve(self, technique) -> tuple[list[dict], list[int]]:
        """Resolve the round; return her cast's ledger rows and its roll's pull lines.

        The ledger is read from the outcome panel's endpoint. The pull lines are the
        "Combat pull" contributions handed to the modifier seam for ``technique``'s roll.
        """
        check_type = technique.action_template.check_type
        pull_lines: list[int] = []
        real_collect = combat_services.collect_check_modifiers

        def collect(sheet, rolled_check_type, **kwargs):
            if rolled_check_type == check_type:
                pull_lines.extend(
                    line.value
                    for line in kwargs.get("extra_contributions") or ()
                    if line.source_label == "Combat pull"
                )
            return real_collect(sheet, rolled_check_type, **kwargs)

        with patch.object(combat_services, "collect_check_modifiers", side_effect=collect):
            resolve_round(self.encounter)

        action = CombatRoundAction.objects.get(
            participant__character_sheet=self.ysmay.sheet_data, round_number=1
        )
        self.assertIsNotNone(action.interaction_id, "Her cast left no log entry.")
        response = self.api(self.account_of(self.ysmay)).get(
            "/api/combat/action-outcome-details/",
            {"action_interaction_ids": str(action.interaction_id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        ledger = response.data[0]["power_ledger"]
        self.assertIsNotNone(ledger, "Her cast's power ledger is not shown to her.")
        return ledger["entries"], pull_lines

    @staticmethod
    def pull_ledger_rows(entries: list[dict]) -> list[int]:
        return [row["amount"] for row in entries if row["stage"] == PowerStage.COMBAT_PULL]

    # -- the journeys --------------------------------------------------------------

    def test_a_pull_boosts_a_cast_of_the_technique_its_thread_is_on(self) -> None:
        self.cast(self.shadow_step, with_pull=True)
        self.assertTrue(CombatPull.objects.filter(resonance=self.resonance).exists())

        entries, pull_lines = self.resolve(self.shadow_step)

        self.assertEqual(self.pull_ledger_rows(entries), [INTENSITY_BUMP])
        self.assertEqual(pull_lines, [FLAT_BONUS])

    def test_a_pull_never_boosts_a_cast_its_threads_do_not_relate_to(self) -> None:
        self.cast(self.ember_lash, with_pull=False)
        self.clash_with_pull(self.shadow_step)
        self.assertTrue(CombatPull.objects.filter(resonance=self.resonance).exists())

        entries, pull_lines = self.resolve(self.ember_lash)

        self.assertEqual(self.pull_ledger_rows(entries), [])
        self.assertEqual(pull_lines, [])
