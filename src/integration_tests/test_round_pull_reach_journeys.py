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
  "combat pulls" line and its roll no "Combat pull" line (before the fix it had both);
  the Shadow Step contribution the pull rode in with gets both (before, it got neither).
- Through the check: a thread on the stat Shadow Step's check rolls reaches its cast.
"""

from __future__ import annotations

from unittest.mock import patch

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks import services as checks_services
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckTypeTrait
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
from world.combat.models import ClashContribution, CombatPull, CombatRoundAction
from world.combat.services import resolve_round
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
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
from world.mechanics.constants import POWER_CATEGORY_NAME
from world.mechanics.factories import CharacterEngagementFactory, ModifierTargetFactory
from world.mechanics.models import ModifierCategory
from world.mechanics.services import create_distinction_modifiers
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
        for kind in (TargetKind.TECHNIQUE, TargetKind.TRAIT):
            ThreadPullEffectFactory(
                target_kind=kind,
                resonance=self.resonance,
                tier=1,
                min_thread_level=0,
                effect_kind=EffectKind.FLAT_BONUS,
                flat_bonus_amount=FLAT_BONUS,
            )
            ThreadPullEffectFactory(
                target_kind=kind,
                resonance=self.resonance,
                tier=1,
                min_thread_level=10,
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
        self.also_pulled: list = []

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
            "pull_thread_ids": [thread.pk for thread in self.pulled],
        }

    @property
    def pulled(self) -> list:
        """The threads her pull names, in the order the client sends them."""
        return [self.thread, *self.also_pulled]

    def thread_on_the_stat_of(self, technique) -> None:
        """Swap her thread for one on the stat ``technique``'s check rolls (a TRAIT thread).

        It relates to a cast only through the check that cast rolls, so it reaches the
        cast only when the cast's check is carried from declaration to resolution.
        """
        stat = CheckTypeTrait.objects.get(check_type=technique.action_template.check_type).trait
        self.thread = ThreadFactory(
            owner=self.ysmay.sheet_data,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=stat,
            level=10,
            name="Steady Strand",
        )

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

    def resolve(self, *techniques) -> dict[int, list[int]]:
        """Resolve the round; return the "Combat pull" roll lines per technique rolled.

        The lines are the contributions handed to the modifier seam (the round's casts
        reach it through ``world.combat.services``, a clash contribution through
        ``world.checks.services``) for each technique's check. Each of ``techniques``
        must have rolled, so an empty list means "rolled, with no pull line".
        """
        lines: dict[int, list[int]] = {}
        real_collect = checks_services.collect_check_modifiers

        def collect(sheet, rolled_check_type, **kwargs):
            lines.setdefault(rolled_check_type.pk, []).extend(
                line.value
                for line in kwargs.get("extra_contributions") or ()
                if line.source_label == "Combat pull"
            )
            return real_collect(sheet, rolled_check_type, **kwargs)

        with (
            patch.object(combat_services, "collect_check_modifiers", side_effect=collect),
            patch.object(checks_services, "collect_check_modifiers", side_effect=collect),
        ):
            resolve_round(self.encounter)
        rolled = {}
        for technique in techniques:
            check_pk = technique.action_template.check_type.pk
            self.assertIn(check_pk, lines, f"{technique.name}'s roll never reached the seam.")
            rolled[technique.pk] = lines[check_pk]
        return rolled

    def ledger(self, interaction_id: int | None) -> list[dict]:
        """The power ledger the combat log's outcome panel shows her for one entry."""
        self.assertIsNotNone(interaction_id, "Her action left no log entry.")
        response = self.api(self.account_of(self.ysmay)).get(
            "/api/combat/action-outcome-details/",
            {"action_interaction_ids": str(interaction_id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        ledger = response.data[0]["power_ledger"]
        self.assertIsNotNone(ledger, "Her power ledger is not shown to her.")
        self.assertIn(PowerStage.BASE, [row["stage"] for row in ledger["entries"]])
        return ledger["entries"]

    def cast_ledger(self) -> list[dict]:
        action = CombatRoundAction.objects.get(
            participant__character_sheet=self.ysmay.sheet_data, round_number=1
        )
        return self.ledger(action.interaction_id)

    def contribution_ledger(self) -> list[dict]:
        return self.ledger(
            ClashContribution.objects.get(character=self.ysmay.sheet_data).interaction_id
        )

    @staticmethod
    def pull_ledger_rows(entries: list[dict]) -> list[int]:
        return [row["amount"] for row in entries if row["stage"] == PowerStage.COMBAT_PULL]

    # -- the journeys --------------------------------------------------------------

    def test_a_pull_boosts_a_cast_of_the_technique_its_thread_is_on(self) -> None:
        self.cast(self.shadow_step, with_pull=True)
        self.assertTrue(CombatPull.objects.filter(threads__resonance=self.resonance).exists())

        rolled = self.resolve(self.shadow_step)

        self.assertEqual(self.pull_ledger_rows(self.cast_ledger()), [INTENSITY_BUMP])
        self.assertEqual(rolled[self.shadow_step.pk], [FLAT_BONUS])

    def test_a_pull_never_boosts_a_cast_its_threads_do_not_relate_to(self) -> None:
        """The pull rides her Shadow Step clash contribution: that gets it, Ember Lash not."""
        self.cast(self.ember_lash, with_pull=False)
        self.clash_with_pull(self.shadow_step)
        self.assertTrue(CombatPull.objects.filter(threads__resonance=self.resonance).exists())

        rolled = self.resolve(self.ember_lash, self.shadow_step)

        self.assertEqual(self.pull_ledger_rows(self.cast_ledger()), [])
        self.assertEqual(rolled[self.ember_lash.pk], [])
        self.assertEqual(self.pull_ledger_rows(self.contribution_ledger()), [INTENSITY_BUMP])
        self.assertEqual(rolled[self.shadow_step.pk], [FLAT_BONUS])

    def test_a_pull_on_the_stat_a_cast_rolls_boosts_that_cast(self) -> None:
        self.thread_on_the_stat_of(self.shadow_step)
        self.cast(self.shadow_step, with_pull=True)

        rolled = self.resolve(self.shadow_step)

        self.assertEqual(self.pull_ledger_rows(self.cast_ledger()), [INTENSITY_BUMP])
        self.assertEqual(rolled[self.shadow_step.pk], [FLAT_BONUS])

    def test_a_distinction_bonus_on_the_pull_follows_any_related_thread(self) -> None:
        """A distinction's resonance bonus rides the pull as a whole (+6 here).

        The pull names her Shadow Step thread first (the bonus is filed under it) and a
        relationship thread second, which is in every cast's action. Ember Lash is not
        Shadow Step, but the relationship thread relates to it, so the bonus reaches
        Ember Lash's roll; the Shadow Step thread's own +2 does not.
        """
        power = ModifierCategory.objects.get_or_create(name=POWER_CATEGORY_NAME)[0]
        target = ModifierTargetFactory(
            category=power, name="power_shadow", target_resonance=self.resonance
        )
        instinct = DistinctionFactory(name="Shade-touched")
        DistinctionEffectFactory(distinction=instinct, target=target, value_per_rank=6)
        create_distinction_modifiers(
            CharacterDistinctionFactory(
                character=self.ysmay.sheet_data, distinction=instinct, rank=1
            )
        )
        self.also_pulled = [
            ThreadFactory(
                owner=self.ysmay.sheet_data,
                resonance=self.resonance,
                as_track_thread=True,
                name="Bond Strand",
            )
        ]
        self.cast(self.ember_lash, with_pull=False)
        self.clash_with_pull(self.shadow_step)

        rolled = self.resolve(self.ember_lash, self.shadow_step)

        self.assertEqual(rolled[self.ember_lash.pk], [6])
        self.assertEqual(rolled[self.shadow_step.pk], [FLAT_BONUS + 6])
