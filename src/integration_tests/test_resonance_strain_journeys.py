"""Burning resonance when she strains (#4736, slice 7 of #4672).

Ysmay pulls a thread on her technique skill and burns resonance from it to push harder.
The ceiling is half her runtime intensity (StrainConfig.burn_per_intensity 0.50, a
technique of intensity 20, so 10); a strain check picks how much of the request she
reaches (StrainBurnReach: Critical Failure 0%, Failure 25%, Partial 50%, Success 75%,
Critical Success 100%); she is debited only what she reached, and is told so.

Hand-worked numbers used below (StrainConfig curve 10 per point for the first 5 points,
then 9): 4 strain units give 40 power, 6 give 59. A pull costs 1 resonance. Corruption
(tier 1 coefficient 10, Abyssal coefficient 10, Primal 2, Celestial 0):
- a hasty fall of 4 Celestial points at the 1.50 Fall rate is valued 6 Abyssal; the
  tick is ceil(6 x 1.0 x 1.0 x 2.0 hasty) = 12 on the burned Celestial resonance;
- a Celestial caster burning 4 Abyssal raw beside a 1-point pull: ceil(5 x 1.0) = 5.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from actions.factories import ActionTemplateFactory
from commands import pending_actions
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import PathFactory
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
from world.combat.models import ClashContribution, CombatPull, StrainBurnReach
from world.combat.services import resolve_round
from world.combat.services.encounter.config import get_strain_config
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.constants import EffortLevel
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
    ensure_conversion_pairs,
)
from world.magic.models import CharacterResonance
from world.magic.services.strain import strain_to_intensity
from world.magic.services.threads import weave_thread
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.models import Scene
from world.skills.factories import SkillFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CharacterTraitValue, CheckOutcome, PointConversionRange, TraitType
from world.traits.services import ensure_canonical_check_outcome
from world.vitals.models import CharacterVitals

REACH = {
    "Critical Failure": 0,
    "Failure": 25,
    "Partial Success": 50,
    "Success": 75,
    "Critical Success": 100,
}


class _BurningResonance(JourneyCase):
    """The world every burn journey shares: a Path technique, a strain check, reach rows."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.celestial, self.primal, self.abyssal = ensure_conversion_pairs()
        self.skill = SkillFactory()
        self.path = PathFactory(technique_skill=self.skill)
        self.lantern = self.make_room("The Lantern")
        SceneFactory(room=self.lantern)

        cast_check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=cast_check, trait=StatTraitFactory(), weight=1)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            intensity=20,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=cast_check),
            clash_capable=True,
        )

        self.strain_check = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.strain_check, trait=StatTraitFactory(), weight=1)
        config = get_strain_config()
        config.strain_check_type = self.strain_check
        config.save()
        for name in CANONICAL_OUTCOME_LEVELS:
            StrainBurnReach.objects.create(
                outcome_tier=ensure_canonical_check_outcome(name), reach_percent=REACH[name]
            )
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
        self.skill_unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT, unlock_trait=self.skill.trait
        )
        # The scene's anti-spam memory is process-wide and keyed by sheet pk.
        pending_actions._LAST_ACTED.clear()
        self.addCleanup(pending_actions._LAST_ACTED.clear)

    def caster(self, name: str, *, aura: str | None = None):
        """A caster on the Path who knows the technique; ``aura`` is her dominant affinity."""
        character = self.make_player(name, room=self.lantern)
        sheet = character.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        CharacterTechniqueFactory(character=sheet, technique=self.technique)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterTraitValue.objects.create(character=sheet, trait=self.skill.trait, value=10)
        if aura is not None:
            percents = {"celestial": "0", "primal": "0", "abyssal": "0", aura: "100"}
            CharacterAuraFactory(character=sheet, **percents)
        return character

    def thread_for(self, character, resonance, *, balance: int = 10):
        """A thread on her technique skill at ``resonance``, with ``balance`` to spend."""
        sheet = character.sheet_data
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=balance, lifetime_earned=balance
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=resonance,
            tier=1,
            flat_bonus_amount=2,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        CharacterThreadWeavingUnlockFactory(character=sheet, unlock=self.skill_unlock)
        return weave_thread(
            sheet, TargetKind.TRAIT, self.skill.trait, resonance, name=f"{resonance.name} Strand"
        )

    @staticmethod
    def balance(character, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=character.sheet_data, resonance=resonance
        ).balance

    @staticmethod
    def corruption(character, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=character.sheet_data, resonance=resonance
        ).corruption_current

    def cast_line(self, thread, burn: int) -> str:
        return (
            f"cast {self.technique.name} pull={thread.name} "
            f"resonance={thread.resonance.name} burn={burn}"
        )

    def cast_with_outcome(self, character, line: str, outcome_name: str) -> tuple[str, list[int]]:
        """Type ``line`` with the strain check forced to ``outcome_name``.

        The strain check is the cast's first roll, so it takes the forced outcome.

        Returns what she was told and the strain units each curve call received.
        """
        units: list[int] = []

        def curve(*, strain_commitment: int, config) -> int:
            units.append(strain_commitment)
            return strain_to_intensity(strain_commitment=strain_commitment, config=config)

        outcome = CheckOutcome.objects.get(name=outcome_name)
        with (
            force_check_outcome(outcome),
            patch("world.magic.services.techniques.strain_to_intensity", side_effect=curve),
            self.captureOnCommitCallbacks(execute=True),
        ):
            told = self.telnet(character, line)
        # The burn line is sent on commit, after the command's own reply.
        told = self.said(character)
        return told, units


class BurningResonanceOutOfCombat(_BurningResonance):
    """Review focus 1-4 on the scene cast, typed by telnet."""

    def test_burn_reaches_a_share_and_strains_harder_with_no_engagement(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)

        told, units = self.cast_with_outcome(ysmay, self.cast_line(thread, 6), "Success")

        self.assertIn(f"You burn 4 of 6 {resonance.name} resonance.", told)
        self.assertEqual(self.balance(ysmay, resonance), 10 - 1 - 4)
        self.assertEqual(units, [4])
        self.assertFalse(CharacterEngagement.objects.filter(character=ysmay.sheet_data).exists())

    def test_burn_is_capped_by_the_intensity_ceiling(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance, balance=30)

        told, units = self.cast_with_outcome(ysmay, self.cast_line(thread, 50), "Critical Success")

        self.assertIn(f"You burn 10 of 50 {resonance.name} resonance.", told)
        self.assertEqual(self.balance(ysmay, resonance), 30 - 1 - 10)
        self.assertEqual(units, [10])

    def test_burn_never_overdraws_the_balance(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance, balance=5)

        told, _units = self.cast_with_outcome(ysmay, self.cast_line(thread, 50), "Critical Success")

        self.assertIn(f"You burn 4 of 50 {resonance.name} resonance.", told)
        self.assertEqual(self.balance(ysmay, resonance), 0)

    def test_a_worse_roll_never_reaches_more(self) -> None:
        reached = {}
        for index, outcome in enumerate(("Critical Failure", "Failure", "Success")):
            caster = self.caster(f"Caster{index}")
            resonance = ResonanceFactory(affinity=self.primal)
            thread = self.thread_for(caster, resonance)
            self.cast_with_outcome(caster, self.cast_line(thread, 8), outcome)
            reached[outcome] = 10 - 1 - self.balance(caster, resonance)

        self.assertEqual(reached, {"Critical Failure": 0, "Failure": 2, "Success": 6})

    def test_a_botch_burns_nothing_and_says_so(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)

        told, units = self.cast_with_outcome(ysmay, self.cast_line(thread, 6), "Critical Failure")

        self.assertIn(f"You burn 0 of 6 {resonance.name} resonance.", told)
        self.assertEqual(self.balance(ysmay, resonance), 9)
        self.assertEqual(units, [])

    def test_burn_without_a_pull_is_refused(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        self.thread_for(ysmay, resonance)

        told = self.telnet(ysmay, f"cast {self.technique.name} burn=3")

        self.assertIn("Burning resonance needs a thread pull in the same action.", told)
        self.assertEqual(self.balance(ysmay, resonance), 10)

    def test_burn_with_no_strain_check_designated_is_refused(self) -> None:
        config = get_strain_config()
        config.strain_check_type = None
        config.save()
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)

        told = self.telnet(ysmay, self.cast_line(thread, 3))

        self.assertIn("No check is set up for pushing hard yet", told)
        self.assertEqual(self.balance(ysmay, resonance), 10)

    def test_abyssal_caster_burning_celestial_falls_hastily(self) -> None:
        ysmay = self.caster("Ysmay", aura="abyssal")
        resonance = ResonanceFactory(affinity=self.celestial)
        thread = self.thread_for(ysmay, resonance)

        told, units = self.cast_with_outcome(ysmay, self.cast_line(thread, 6), "Success")

        self.assertIn(
            f"You burn 4 of 6 {resonance.name} resonance; it falls at the pair rate to 6.", told
        )
        self.assertEqual(units, [6])
        self.assertEqual(self.balance(ysmay, resonance), 5)
        self.assertEqual(self.corruption(ysmay, resonance), 12)

    def test_celestial_caster_burning_abyssal_burns_raw(self) -> None:
        ysmay = self.caster("Ysmay", aura="celestial")
        resonance = ResonanceFactory(affinity=self.abyssal)
        thread = self.thread_for(ysmay, resonance)

        told, units = self.cast_with_outcome(ysmay, self.cast_line(thread, 6), "Success")

        self.assertIn(f"You burn 4 of 6 {resonance.name} resonance.", told)
        self.assertNotIn("pair rate", told)
        self.assertEqual(units, [4])
        self.assertEqual(self.corruption(ysmay, resonance), 5)

    def test_celestial_burning_its_own_resonance_costs_only_the_resonance(self) -> None:
        ysmay = self.caster("Ysmay", aura="celestial")
        resonance = ResonanceFactory(affinity=self.celestial)
        thread = self.thread_for(ysmay, resonance)

        self.cast_with_outcome(ysmay, self.cast_line(thread, 6), "Success")

        self.assertEqual(self.balance(ysmay, resonance), 5)
        self.assertEqual(self.corruption(ysmay, resonance), 0)


class BurningResonanceOnTheWeb(_BurningResonance):
    """The web cast endpoint, the pull preview, and the combat declaration kwargs."""

    def test_web_cast_burns_with_the_pull(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)
        scene = Scene.objects.get(location_id=self.lantern.pk, is_active=True)
        self.watch(ysmay)

        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.api(self.account_of(ysmay)).post(
                "/api/action-requests/cast/",
                {
                    "scene": scene.pk,
                    "initiator_persona": ysmay.sheet_data.primary_persona.pk,
                    "technique_id": self.technique.pk,
                    "pull": {
                        "resonance_id": resonance.pk,
                        "tier": 1,
                        "thread_ids": [thread.pk],
                        "burn": 6,
                    },
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.balance(ysmay, resonance), 5)
        self.assertTold(ysmay, f"You burn 4 of 6 {resonance.name} resonance.")

    def test_pull_preview_shows_the_burn_ceiling_and_value(self) -> None:
        ysmay = self.caster("Ysmay", aura="abyssal")
        resonance = ResonanceFactory(affinity=self.celestial)
        thread = self.thread_for(ysmay, resonance, balance=8)

        response = self.api(self.account_of(ysmay)).post(
            "/api/magic/thread-pull-preview/",
            {
                "character_sheet_id": ysmay.sheet_data.pk,
                "resonance_id": resonance.pk,
                "tier": 1,
                "thread_ids": [thread.pk],
                "technique_id": self.technique.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        burn = response.data["burn"]
        # Ceiling 10 from intensity, capped by the 7 left after the pull's cost.
        self.assertEqual(burn["ceiling"], 7)
        self.assertEqual(Decimal(burn["strain_units_per_point"]), Decimal("1.50"))
        self.assertTrue(burn["hasty_fall"])
        self.assertTrue(burn["available"])

    def test_scene_cast_refuses_a_bad_burn_cleanly(self) -> None:
        ysmay = self.caster("Ysmay")
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)
        scene = Scene.objects.get(location_id=self.lantern.pk, is_active=True)
        client = self.api(self.account_of(ysmay))

        for bad in (-1, 2**31, "lots", [3], True):
            response = client.post(
                "/api/action-requests/cast/",
                {
                    "scene": scene.pk,
                    "initiator_persona": ysmay.sheet_data.primary_persona.pk,
                    "technique_id": self.technique.pk,
                    "pull": {
                        "resonance_id": resonance.pk,
                        "tier": 1,
                        "thread_ids": [thread.pk],
                        "burn": bad,
                    },
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400, (bad, response.data))
            self.assertIn("burn", response.data["pull"])
        self.assertEqual(self.balance(ysmay, resonance), 10)


class BurningResonanceInCombat(_BurningResonance):
    """Review focus 5 and the one-action ruling, by telnet and the web dispatch endpoint."""

    def setUp(self) -> None:
        super().setUp()
        ClashConfigFactory()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.lantern
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        self.clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            status=ClashStatus.ACTIVE,
            started_round=1,
        )

    def fighter(self, name: str = "Ysmay"):
        character = self.caster(name)
        CombatParticipantFactory(encounter=self.encounter, character_sheet=character.sheet_data)
        engagement = CharacterEngagementFactory(character=character.sheet_data)
        return character, engagement

    def dispatch(self, character, ref: dict, kwargs: dict):
        """POST a declaration through the web dispatch endpoint, as the client does."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.api(self.account_of(character)).post(
                f"/api/actions/characters/{character.pk}/dispatch/",
                {"ref": ref, "kwargs": kwargs},
                format="json",
            )

    def focused_ref(self) -> dict:
        return {"backend": "combat", "technique_id": self.technique.pk, "action_slot": "focused"}

    def focused_kwargs(self, thread=None, **extra) -> dict:
        kwargs = {
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target_id": self.opponent.pk,
        }
        if thread is not None:
            kwargs |= {
                "pull_resonance_id": thread.resonance.pk,
                "pull_tier": 1,
                "pull_thread_ids": [thread.pk],
            }
        return kwargs | extra

    def resolve_watching_the_curve(self) -> list[int]:
        """Resolve the round with every roll a Success; return each curve call's units."""
        rolled = MagicMock(success_level=2, outcome=CheckOutcome.objects.get(name="Success"))
        units: list[int] = []

        def curve(*, strain_commitment: int, config) -> int:
            units.append(strain_commitment)
            return strain_to_intensity(strain_commitment=strain_commitment, config=config)

        with (
            patch("world.checks.services.perform_check", return_value=rolled),
            patch("world.magic.services.techniques.strain_to_intensity", side_effect=curve),
        ):
            resolve_round(self.encounter)
        return units

    def test_web_combat_refuses_a_bad_or_lone_burn_cleanly(self) -> None:
        ysmay, _engagement = self.fighter()
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)

        for bad in ("3", [3], 1.5, True, -1, 2**31):
            response = self.dispatch(
                ysmay, self.focused_ref(), self.focused_kwargs(thread, pull_burn=bad)
            )
            self.assertEqual(response.status_code, 400, (bad, response.data))
            self.assertEqual(
                response.data["detail"], "A burn must be a whole number of resonance, 0 or more."
            )
        lone = self.dispatch(ysmay, self.focused_ref(), self.focused_kwargs(pull_burn=3))
        self.assertEqual(lone.status_code, 400, lone.data)
        self.assertEqual(
            lone.data["detail"], "Burning resonance needs a thread pull in the same action."
        )
        self.assertEqual(self.balance(ysmay, resonance), 10)
        self.assertFalse(CombatPull.objects.exists())

    def test_web_focused_cast_burns_at_declaration_and_strains_at_resolution(self) -> None:
        ysmay, engagement = self.fighter()
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)
        self.watch(ysmay)

        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            response = self.dispatch(
                ysmay, self.focused_ref(), self.focused_kwargs(thread, pull_burn=6)
            )

        self.assertEqual(response.status_code, 200, response.data)
        pull = CombatPull.objects.get(participant__character_sheet=ysmay.sheet_data)
        self.assertEqual((pull.resonance_burned, pull.burn_strain_units), (4, 4))
        self.assertEqual(self.balance(ysmay, resonance), 5)
        self.assertTold(ysmay, f"You burn 4 of 6 {resonance.name} resonance.")

        before = engagement.intensity_modifier
        self.assertEqual(self.resolve_watching_the_curve(), [4])
        engagement.refresh_from_db()
        # Half of the 40 power the 4 burned units bought feeds her engagement.
        self.assertEqual(engagement.intensity_modifier - before, 20)

    def test_a_burn_strains_only_the_action_it_was_declared_with(self) -> None:
        """A focused cast's burn never strains her clash contribution in the same round."""
        ysmay, engagement = self.fighter()
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)

        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            cast = self.dispatch(
                ysmay, self.focused_ref(), self.focused_kwargs(thread, pull_burn=6)
            )
        self.assertEqual(cast.status_code, 200, cast.data)
        clash = self.dispatch(
            ysmay,
            {
                "backend": "combat",
                "clash_id": self.clash.pk,
                "clash_action_slot": ClashActionSlot.FOCUSED,
            },
            {"technique_id": self.technique.pk},
        )
        self.assertEqual(clash.status_code, 200, clash.data)

        before = engagement.intensity_modifier
        units = self.resolve_watching_the_curve()

        # Both resolved through the cast pipeline; the burn's 4 units reached one of them.
        contribution = ClashContribution.objects.get(character=ysmay.sheet_data)
        self.assertEqual(contribution.anima_committed, 0)
        self.assertEqual(units, [4])
        engagement.refresh_from_db()
        self.assertEqual(engagement.intensity_modifier - before, 20)

    def test_clash_burn_is_debited_at_declaration_and_strains_the_contribution(self) -> None:
        ysmay, engagement = self.fighter()
        sheet = ysmay.sheet_data
        resonance = ResonanceFactory(affinity=self.primal)
        thread = self.thread_for(ysmay, resonance)
        line = (
            f"clash {self.opponent.name} with {self.technique.name} pull={thread.name} "
            f"resonance={resonance.name} burn=6"
        )

        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            told = self.telnet(ysmay, line)

        self.assertIn(f"You burn 4 of 6 {resonance.name} resonance.", self.said(ysmay))
        self.assertEqual(
            CombatPull.objects.get(participant__character_sheet=sheet).resonance_burned, 4
        )
        self.assertEqual(self.balance(ysmay, resonance), 5)
        self.assertNotIn("Traceback", told)

        before = engagement.intensity_modifier
        self.assertEqual(self.resolve_watching_the_curve(), [4])
        engagement.refresh_from_db()
        self.assertEqual(engagement.intensity_modifier - before, 20)
