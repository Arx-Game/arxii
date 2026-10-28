"""Journeys for Audere at an earlier Soulfray stage with control, and Soulfray's anima-0
stage (#4740, slice 4 of #4727).

Ysmay fights a Hollow Hound. The Soulfray ladder is Fraying (severity 1), Tearing (10)
and Ripping (50); the Audere offer asks for Ripping and a Major intensity (15).

- Her Opening Spark (intensity 20, control 30) is typed as a ``cast`` in the round.
  With ``control_per_stage_earlier`` at 25, her 30 control is one full step, so the
  offer opens at Tearing; ``accept surge`` then holds, because the offer remembers the
  control it fired with. A step of 31 (no full step), or 0 (off), leaves Tearing short.
  A step of 1 would take her 30 stages earlier, and stops at Fraying.
- Her Ember Lash (intensity 10, control 5, anima cost 10, so 15 anima a cast) drives a
  big Soulfray hit: with the severity scale at 100, a cast that leaves her 5 of 100
  anima adds 84 severity. Ripping is the anima-0 stage, so with anima left she stops at
  severity 49, in Tearing; a cast that empties her reaches Ripping.
- Staff see an intensity tier that lowers control on the Required content dashboard,
  and the tier's admin page refuses a negative control modifier.

The cast is typed through telnet, but the round is resolved by calling ``resolve_round``
directly: no player seam resolves a round (the round ends on a timer or a GM), and the
offence roll is pinned there so the cast lands.

Expected values are the rows built here, not anything the code computes.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.urls import reverse

from integration_tests.harness import JourneyCase
from integration_tests.test_refused_admin_saves_journeys import RefusedAdminSaveCase
from world.combat.constants import ActionCategory, OpponentTier, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.services import add_participant, begin_declaration_phase, resolve_round
from world.conditions.factories import (
    ConditionInstanceFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance, ConditionStage
from world.magic.audere import PendingAudereOffer
from world.magic.constants import AUDERE_SEED_TEMPLATE_NAME
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterGiftFactory,
    EffectTypeFactory,
    IntensityTierFactory,
    TechniqueFactory,
)
from world.magic.models import (
    CharacterAnima,
    CharacterTechnique,
    IntensityTier,
    SoulfrayConfig,
    Technique,
)
from world.magic.seeds_cast import ensure_technique_cast_content
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

FRAYING_SEVERITY = 1
TEARING_SEVERITY = 10
RIPPING_SEVERITY = 50
SPARK_CONTROL = 30
SPARK_INTENSITY = 20
SURGE_PROMPT = f"[surge] Intensity surge (fired: {SPARK_INTENSITY})"
ONE_STAGE_EARLIER = "Your control lets you break through one Soulfray stage earlier than usual."
TWO_STAGES_EARLIER = "Your control lets you break through 2 Soulfray stages earlier than usual."
CONTROL_LINE_START = "Your control lets you break through"


def _clean_cast(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands the cast."""
    return MagicMock(success_level=2)


class _AFightWithAFrayedSoul(JourneyCase):
    """Ysmay in round 1 against a Hollow Hound, with the Audere gate authored."""

    def setUp(self) -> None:
        super().setUp()
        self.gate = build_audere_gate_fixture(tier_suffix=type(self).__name__)
        stages = list(
            ConditionStage.objects.filter(condition=self.gate.soulfray_template).order_by(
                "stage_order"
            )
        )
        self.fraying, self.tearing, self.ripping = stages
        for stage, severity in zip(
            stages, (FRAYING_SEVERITY, TEARING_SEVERITY, RIPPING_SEVERITY), strict=True
        ):
            stage.severity_threshold = severity
            stage.save(update_fields=["severity_threshold"])
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        self.action_template = ensure_technique_cast_content()

        self.room = self.make_room("The Ash Yard")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterVitals.objects.create(character_sheet=self.sheet, health=500, max_health=500)

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            risk_level=RiskLevel.MODERATE,
            room=self.room,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.hound = CombatOpponentFactory(
            encounter=self.encounter,
            name="Hollow Hound",
            tier=OpponentTier.MOOK,
            health=5000,
            max_health=5000,
            threat_pool=pool,
        )
        add_participant(self.encounter, self.sheet)
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

    def knows(self, name: str, **stats: int) -> Technique:
        technique = TechniqueFactory(
            name=name,
            effect_type=EffectTypeFactory(name=f"{name} effect", base_power=5),
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
            **stats,
        )
        CharacterGiftFactory(character=self.sheet, gift=technique.gift)
        CharacterTechnique.objects.create(character=self.sheet, technique=technique)
        return technique

    def frayed_at(self, stage: ConditionStage, severity: int) -> ConditionInstance:
        return ConditionInstanceFactory(
            target=self.ysmay,
            condition=self.gate.soulfray_template,
            current_stage=stage,
            severity=severity,
            rounds_remaining=None,
        )

    def cast_in_the_round(self, technique: Technique) -> str:
        told = self.telnet(self.ysmay, f"cast {technique.name} at {self.hound.name} soulfray")
        self.assertNotIn("Could not", told)
        resolve_round(self.encounter, offense_check_fn=_clean_cast)
        return told

    def prompts(self) -> str:
        """What she reads when she asks the game which prompts are waiting for her."""
        return self.telnet(self.ysmay, "accept")

    def offer(self) -> PendingAudereOffer | None:
        return PendingAudereOffer.objects.filter(character_sheet=self.sheet).first()

    def soulfray(self) -> ConditionInstance:
        return ConditionInstance.objects.select_related("current_stage").get(
            target=self.ysmay, condition=self.gate.soulfray_template
        )


class _HighControlOpensAudere(_AFightWithAFrayedSoul):
    def setUp(self) -> None:
        super().setUp()
        CharacterAnimaFactory(character=self.sheet, current=100, maximum=100)
        self.spark = self.knows(
            "Opening Spark", intensity=SPARK_INTENSITY, control=SPARK_CONTROL, anima_cost=3
        )

    def step(self, control: int) -> None:
        self.gate.threshold.control_per_stage_earlier = control
        self.gate.threshold.save(update_fields=["control_per_stage_earlier"])


class HighControlOpensAudereAStageEarlier(_HighControlOpensAudere):
    def test_the_offer_opens_at_tearing_and_the_surge_holds_on_accept(self) -> None:
        self.step(25)
        self.frayed_at(self.tearing, TEARING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertIn(f"{SURGE_PROMPT}. {ONE_STAGE_EARLIER}", self.prompts())
        self.assertEqual(self.offer().soulfray_stage_order, self.tearing.stage_order)

        told = self.telnet(self.ysmay, "accept surge")

        self.assertIn("The surge takes hold.", told)
        self.assertIsNone(self.offer())
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.ysmay, condition__name=AUDERE_SEED_TEMPLATE_NAME
            ).exists()
        )

    def test_control_short_of_a_full_step_waits_for_ripping(self) -> None:
        self.step(SPARK_CONTROL + 1)
        self.frayed_at(self.tearing, TEARING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertNotIn("[surge]", self.prompts())
        self.assertIsNone(self.offer())

    def test_a_step_of_zero_changes_nothing(self) -> None:
        self.step(0)
        self.frayed_at(self.tearing, TEARING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertNotIn("[surge]", self.prompts())
        self.assertIsNone(self.offer())

    def test_at_ripping_the_offer_opens_whatever_the_step(self) -> None:
        self.step(0)
        self.frayed_at(self.ripping, RIPPING_SEVERITY)

        self.cast_in_the_round(self.spark)

        told = self.prompts()
        self.assertIn(SURGE_PROMPT, told)
        self.assertNotIn(CONTROL_LINE_START, told)
        self.assertEqual(self.offer().soulfray_stage_order, self.ripping.stage_order)


class ControlStepsBackAlongTheLadderNotTheNumbers(_HighControlOpensAudere):
    """Staff number the ladder 10, 20, 30. One step of control is one stage, Tearing,
    not stage order 29."""

    def setUp(self) -> None:
        super().setUp()
        for stage, order in ((self.ripping, 30), (self.tearing, 20), (self.fraying, 10)):
            stage.stage_order = order
            stage.save(update_fields=["stage_order"])
        self.step(25)

    def test_one_step_opens_the_offer_at_tearing(self) -> None:
        self.frayed_at(self.tearing, TEARING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertIn(f"{SURGE_PROMPT}. {ONE_STAGE_EARLIER}", self.prompts())
        self.assertEqual(self.offer().soulfray_stage_order, 20)

    def test_fraying_is_still_short(self) -> None:
        self.frayed_at(self.fraying, FRAYING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertNotIn("[surge]", self.prompts())


class ControlNeverAsksBelowTheFirstStage(_HighControlOpensAudere):
    """A step of 1 is 30 stages earlier for her 30 control; the ladder starts at Fraying."""

    def setUp(self) -> None:
        super().setUp()
        self.step(1)

    def test_fraying_is_enough(self) -> None:
        self.frayed_at(self.fraying, FRAYING_SEVERITY)

        self.cast_in_the_round(self.spark)

        self.assertIn(f"{SURGE_PROMPT}. {TWO_STAGES_EARLIER}", self.prompts())
        self.assertEqual(self.offer().soulfray_stage_order, self.fraying.stage_order)

    def test_with_no_soulfray_at_all_there_is_no_offer(self) -> None:
        self.cast_in_the_round(self.spark)

        self.assertNotIn("[surge]", self.prompts())
        self.assertIsNone(self.offer())


class SoulfraysDangerStageNeedsAnimaAtZero(_AFightWithAFrayedSoul):
    """Ripping is the anima-0 stage. Ember Lash costs 15 anima a cast.

    The game tells her nothing about her Soulfray stage here: the round sends her no
    line about it and no telnet command reads it back. So these journeys assert the
    stage and her anima as stored.
    """

    def setUp(self) -> None:
        super().setUp()
        config = SoulfrayConfig.objects.get()
        config.severity_scale = 100
        config.anima_zero_stage = self.ripping
        config.full_clean()
        config.save()
        self.lash = self.knows("Ember Lash", intensity=10, control=5, anima_cost=10)
        self.frayed_at(self.fraying, FRAYING_SEVERITY)

    def anima_left(self) -> int:
        return CharacterAnima.objects.get(character=self.sheet).current

    def test_with_anima_left_a_big_hit_stops_in_tearing(self) -> None:
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=100)

        self.cast_in_the_round(self.lash)

        self.assertEqual(self.anima_left(), 5)
        soulfray = self.soulfray()
        self.assertEqual(soulfray.current_stage, self.tearing)
        self.assertEqual(soulfray.severity, RIPPING_SEVERITY - 1)

    def test_a_cast_that_empties_her_reaches_ripping(self) -> None:
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=100)

        self.cast_in_the_round(self.lash)

        self.assertEqual(self.anima_left(), 0)
        self.assertEqual(self.soulfray().current_stage, self.ripping)

    def test_with_no_anima_zero_stage_the_same_hit_reaches_ripping(self) -> None:
        config = SoulfrayConfig.objects.get()
        config.anima_zero_stage = None
        config.save(update_fields=["anima_zero_stage"])
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=100)

        self.cast_in_the_round(self.lash)

        self.assertEqual(self.anima_left(), 5)
        self.assertEqual(self.soulfray().current_stage, self.ripping)


class StaffSeeAnIntensityTierThatLowersControl(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def test_the_dashboard_lists_the_tier_and_its_value(self) -> None:
        IntensityTierFactory(name="Searing", threshold=30, control_modifier=-4)
        IntensityTierFactory(name="Steady", threshold=40, control_modifier=2)

        page = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn("Intensity tiers never lower control", body)
        self.assertIn("Searing: -4", body)
        self.assertNotIn("Steady", body)

    def test_with_no_negative_tier_the_row_is_clear(self) -> None:
        IntensityTierFactory(name="Steady", threshold=40, control_modifier=0)

        page = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn("Intensity tiers never lower control", body)
        self.assertNotIn("Steady", body)


class TheTierAdminRefusesANegativeControlModifier(RefusedAdminSaveCase):
    def test_a_negative_value_is_refused_and_the_row_keeps_its_value(self) -> None:
        tier = IntensityTierFactory(name="Searing", threshold=30, control_modifier=0)
        url = reverse("admin:arxii_intensitytier_change", args=[tier.pk])
        data = self.change_post(url)
        data["control_modifier"] = "-4"

        refused = self.client.post(url, data)

        self.assertEqual(refused.status_code, 200)
        self.assertIn("control_modifier", refused.context["adminform"].form.errors)
        self.assertEqual(IntensityTier.objects.get(pk=tier.pk).control_modifier, 0)
