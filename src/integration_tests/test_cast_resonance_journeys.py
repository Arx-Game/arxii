"""A cast is worked in one resonance, and its corruption follows that resonance (#5231).

Ysmay is mostly Primal (80 Primal, 20 Abyssal, settled the same). Her Gift's thread holds a
Primal resonance, which leads, and an Abyssal one. She casts a benign technique on herself
through the web cast endpoint, naming the resonance to work it in. Hand-worked from the
spec's starting numbers (Abyssal corruption coefficient 10, Primal 0, tier 1 coefficient 10;
light part 10 percent below an Abyssal share of 50, all of it from there):

* Worked in her Primal resonance, a cast adds no corruption to any resonance she holds.
* Worked in her Abyssal resonance, the same cast adds a tenth of what it adds a caster who is
  60 percent Abyssal, rounded up, and that is at least 1.
* A resonance the Gift's thread holds no row for is refused before anything is charged.
* A caster with no thread on the Gift works it in the Gift's first resonance in the order
  Primal, Celestial, Abyssal, so nobody is corrupted by a default she did not pick.
* A cast that stops at the Soulfray warning and is confirmed keeps every choice she made.

What each journey asserts the player was told or shown: the cast endpoint's power ledger (it
opens on the "channeled intensity" line), the castable list's default entry, the declaration's
reply ("You ready your action for this round." on telnet, "Action declared for round
resolution." on the web), the Soulfray warning and its confirmation, and the combat log's
power ledger for the resolved round.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from django.urls import reverse
from django.utils import timezone

from actions.factories import ActionTemplateFactory
from commands import pending_actions
from integration_tests.harness import JourneyCase
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ActionCategory, OpponentTier, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatPull, CombatRoundAction
from world.combat.services import add_participant, begin_declaration_phase, resolve_round
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    SoulfrayTemplateFactory,
)
from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    EffectTypeFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ensure_canonical_affinities,
    ensure_soulfray_config,
)
from world.magic.models import (
    Affinity,
    CharacterAnima,
    CharacterResonance,
    Thread,
    ThreadResonance,
)
from world.magic.seeds_cast import ensure_technique_cast_content
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import provision_latent_gift_thread
from world.scenes.action_constants import ConsentDecision
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneActionRequest
from world.scenes.tests.cast_test_helpers import (
    attach_behavior_altering_condition,
    grant_technique,
)
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

CAST_URL = "/api/action-requests/cast/"
NOT_ON_THREAD = "That resonance is not part of this Gift's thread."
DECLARED_ON_TELNET = "You ready your action for this round."
DECLARED_ON_THE_WEB = "Action declared for round resolution."
SOULFRAY_WARNING = "Your soul frays at the edges."
BASE_LEDGER_LINE = "channeled intensity"


def _clean_cast(*args: object, **kwargs: object) -> MagicMock:
    """An offence roll at success level 2, which lands the cast."""
    return MagicMock(success_level=2, outcome=None)


def _corruption_template(resonance) -> None:
    """The condition a resonance's corruption lives in, as the accrual service finds it."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})", has_progression=True, corruption_resonance=resonance
    )
    for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
        ConditionStageFactory(condition=template, stage_order=order, severity_threshold=threshold)


def _soulfray_warning_up(character) -> None:
    """Soulfray's first stage on ``character``, so a cast stops at the warning."""
    template = SoulfrayTemplateFactory(has_progression=True)
    ensure_soulfray_config()
    stage = ConditionStageFactory(
        condition=template,
        stage_order=1,
        name="Fraying",
        description=SOULFRAY_WARNING,
        severity_threshold=1,
    )
    ConditionInstanceFactory(
        target=character,
        condition=template,
        current_stage=stage,
        severity=1,
        rounds_remaining=None,
    )


def _author_a_tier_one_pull(resonance) -> None:
    """A tier 1 pull costs 1 resonance and, on a technique thread paid by ``resonance``, adds
    3 to the power (an intensity bump) at the multiplier of one rung."""
    ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=0)
    ThreadPullEffectFactory(
        target_kind=TargetKind.TECHNIQUE,
        resonance=resonance,
        tier=1,
        min_thread_level=0,
        as_intensity_bump=True,
        intensity_bump_amount=3,
    )


def _strand_on(sheet, resonance, technique) -> Thread:
    """A one-word thread woven on ``technique`` that ``resonance`` pays for; level 10 reads as
    one rung. One word, because telnet's ``pull=`` reads a thread by its name."""
    return ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_trait=None,
        target_technique=technique,
        level=10,
        name="Strand",
    )


class _AYsmayWithATwoResonanceGift(JourneyCase):
    """Ysmay's Gift holds a Primal and an Abyssal resonance; she picks which to cast in."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        Affinity.objects.clear_cache()
        _celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.warmth = ResonanceFactory(name="Warmth", affinity=self.primal)
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.stray = ResonanceFactory(name="Stray", affinity=self.primal)
        _corruption_template(self.ruin)
        self.gift = GiftFactory()
        self.technique = self._technique(self.gift)
        self.room = self.make_room("The Lantern")
        self.scene = SceneFactory(room=self.room)

    @staticmethod
    def _technique(gift):
        """A self-targeted benign technique whose control clears its intensity: no mishap."""
        return TechniqueFactory(
            gift=gift,
            intensity=20,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )

    def caster(self, name: str, *, primal: str, abyssal: str, on_thread: bool = True):
        """A caster whose true aura is ``primal`` / ``abyssal`` and who knows the technique."""
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CharacterAuraFactory(character=sheet, celestial="0", primal=primal, abyssal=abyssal)
        grant_technique(sheet.primary_persona, self.technique)
        for resonance in (self.warmth, self.ruin, self.stray):
            CharacterResonanceFactory(character_sheet=sheet, resonance=resonance, balance=10)
        if on_thread:
            # Warmth is listed first, so it leads the thread.
            provision_latent_gift_thread(sheet, self.gift, resonances=[self.warmth, self.ruin])
        return character

    def corruption(self, character) -> dict[str, int]:
        rows = CharacterResonance.objects.filter(character_sheet=character.sheet_data)
        return {row.resonance.name: row.corruption_current for row in rows}

    @staticmethod
    def balance(character, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=character.sheet_data, resonance=resonance
        ).balance

    def assertShownTheBaseLine(self, ledger: dict) -> None:  # noqa: N802 - unittest style
        """The power ledger she is shown opens on the base line, the cast's channeled intensity."""
        self.assertEqual(ledger["entries"][0]["source_label"], BASE_LEDGER_LINE)

    def castable_options(self, character, technique=None) -> list[dict]:
        """The technique's resonance options in the scene's castable list, as the panel reads."""
        technique = technique or self.technique
        response = self.api(self.account_of(character)).get(
            "/api/action-requests/castable-techniques/",
            {"initiator_persona": character.sheet_data.primary_persona.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = next(row for row in response.json() if row["id"] == technique.pk)
        return row["resonance_options"]


class WorkingACastInAChosenResonance(_AYsmayWithATwoResonanceGift):
    """She casts through the web cast endpoint, on her own or at another player."""

    def cast(self, character, technique=None, **body):
        technique = technique or self.technique
        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return self.api(self.account_of(character)).post(
                CAST_URL,
                {
                    "scene": self.scene.pk,
                    "initiator_persona": character.sheet_data.primary_persona.pk,
                    "technique_id": technique.pk,
                    **body,
                },
                format="json",
            )

    def test_a_cast_worked_in_her_primal_resonance_adds_no_corruption(self) -> None:
        ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        before = self.corruption(ysmay)

        response = self.cast(ysmay, preferred_resonance_id=self.warmth.pk)

        self.assertEqual(response.status_code, 201, response.data)
        # What she is shown of the cast: its power ledger, which opens on the base line.
        self.assertShownTheBaseLine(response.json()["result"]["power_ledger"])
        # Worked in Warmth (Primal, coefficient 0), the cast adds nothing to any resonance.
        self.assertEqual(self.corruption(ysmay), before)

    def test_a_cast_with_no_choice_is_worked_in_the_default_the_list_names(self) -> None:
        ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        before = self.corruption(ysmay)

        # The list she picks from names Warmth, which leads her Gift's thread, as the default.
        options = self.castable_options(ysmay)
        self.assertEqual(
            [(option["name"], option["is_default"]) for option in options],
            [("Warmth", True), ("Ruin", False)],
        )
        response = self.cast(ysmay)

        self.assertEqual(response.status_code, 201, response.data)
        # Worked in that default, a cast adds no corruption: it was not worked in Ruin.
        self.assertEqual(self.corruption(ysmay), before)

    def test_a_cast_worked_in_her_abyssal_resonance_adds_a_tenth_rounded_up(self) -> None:
        ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        hobb = self.caster("Hobb", primal="40", abyssal="60")
        ysmay_before = self.corruption(ysmay)["Ruin"]
        hobb_before = self.corruption(hobb)["Ruin"]

        ysmay_response = self.cast(ysmay, preferred_resonance_id=self.ruin.pk)
        hobb_response = self.cast(hobb, preferred_resonance_id=self.ruin.pk)

        self.assertEqual(ysmay_response.status_code, 201, ysmay_response.data)
        self.assertEqual(hobb_response.status_code, 201, hobb_response.data)
        for response in (ysmay_response, hobb_response):
            self.assertShownTheBaseLine(response.json()["result"]["power_ledger"])
        full = self.corruption(hobb)["Ruin"] - hobb_before
        light = self.corruption(ysmay)["Ruin"] - ysmay_before
        # Hand-worked: intensity 20 at coefficients of 1.0 (Abyssal 10 tenths, tier 1 10
        # tenths) is 20 for Hobb, who is past the line of 50. Ysmay at 20 percent Abyssal takes
        # the light 10 percent: 20 x 10 / 100 = 2.
        self.assertEqual(full, 20)
        self.assertEqual(light, 2)
        self.assertEqual(light, math.ceil(full / 10))

    def test_a_resonance_not_on_the_gifts_thread_is_refused_and_nothing_is_charged(self) -> None:
        ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        anima_before = CharacterAnima.objects.get(character=ysmay.sheet_data).current
        before = self.corruption(ysmay)

        response = self.cast(ysmay, preferred_resonance_id=self.stray.pk)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["detail"], NOT_ON_THREAD)
        self.assertEqual(
            CharacterAnima.objects.get(character=ysmay.sheet_data).current, anima_before
        )
        self.assertEqual(self.corruption(ysmay), before)

    def test_a_caster_with_no_thread_on_a_gift_that_lists_only_an_abyssal_resonance_casts_in_it(
        self,
    ) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.ruin)
        technique = self._technique(gift)
        hobb = self.caster("Hobb", primal="40", abyssal="60", on_thread=False)
        grant_technique(hobb.sheet_data.primary_persona, technique)
        before = self.corruption(hobb)

        response = self.cast(hobb, technique=technique)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertShownTheBaseLine(response.json()["result"]["power_ledger"])
        # Ruin is the only resonance the Gift lists, so it is the default: 20 x (10/10) x (10/10),
        # in full for a caster 60 percent Abyssal.
        after = self.corruption(hobb)
        self.assertEqual(after["Ruin"] - before["Ruin"], 20)
        self.assertEqual(after["Warmth"], before["Warmth"])

    def test_a_caster_with_no_thread_on_the_gift_casts_in_its_primal_resonance_first(self) -> None:
        # The Gift lists Ruin (Abyssal) and Warmth (Primal), which sorts Ruin first by affinity
        # name. With no thread of hers on it, the default is the first in the order Primal,
        # Celestial, Abyssal: Warmth, so Hobb, 60 percent Abyssal, is not corrupted by a
        # default she did not pick.
        gift = GiftFactory()
        gift.resonances.add(self.ruin, self.warmth)
        technique = self._technique(gift)
        hobb = self.caster("Hobb", primal="40", abyssal="60", on_thread=False)
        grant_technique(hobb.sheet_data.primary_persona, technique)
        before = self.corruption(hobb)

        # With no thread there is nothing to choose between: the list holds the default alone.
        options = self.castable_options(hobb, technique)
        self.assertEqual([(o["name"], o["is_default"]) for o in options], [("Warmth", True)])
        response = self.cast(hobb, technique=technique)

        self.assertEqual(response.status_code, 201, response.data)
        self.assertShownTheBaseLine(response.json()["result"]["power_ledger"])
        self.assertEqual(self.corruption(hobb), before)

    def _ask_hobb_to_accept_a_cast_in_ruin(self):
        """Ysmay asks to cast a consent-gated technique on Hobb, worked in Ruin."""
        self.seed_social_engagement()
        technique = self._technique(self.gift)
        attach_behavior_altering_condition(technique)
        ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        hobb = self.caster("Hobb", primal="40", abyssal="60")
        grant_technique(ysmay.sheet_data.primary_persona, technique)
        response = self.cast(
            ysmay,
            technique=technique,
            target_persona=hobb.sheet_data.primary_persona.pk,
            preferred_resonance_id=self.ruin.pk,
        )
        self.assertEqual(response.status_code, 201, response.data)
        # She is told the cast waits for Hobb, and the request holds the choice she named.
        self.assertEqual(response.data["status"], "pending")
        (request,) = SceneActionRequest.objects.filter(technique=technique)
        return ysmay, hobb, request

    def _hobb_accepts(self, hobb, request):
        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return self.api(self.account_of(hobb)).post(
                reverse("sceneactionrequest-respond", kwargs={"pk": request.pk}),
                {"decision": ConsentDecision.ACCEPT},
                format="json",
            )

    def test_a_consent_gated_cast_is_worked_in_the_resonance_she_chose_when_it_resolves(
        self,
    ) -> None:
        ysmay, hobb, request = self._ask_hobb_to_accept_a_cast_in_ruin()
        self.assertEqual(request.cast_resonance, self.ruin)
        before = self.corruption(ysmay)

        response = self._hobb_accepts(hobb, request)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "resolved")
        self.assertShownTheBaseLine(response.data["result"]["power_ledger"])
        # Worked in Ruin it adds Ruin corruption (the light tenth of Ysmay's cast, at least 1;
        # the two-caster comparison above works the exact figure) and none to Warmth.
        after = self.corruption(ysmay)
        self.assertGreaterEqual(after["Ruin"] - before["Ruin"], 1)
        self.assertEqual(after["Warmth"], before["Warmth"])

    def test_a_chosen_resonance_the_thread_lost_meanwhile_falls_back_to_the_default(self) -> None:
        ysmay, hobb, request = self._ask_hobb_to_accept_a_cast_in_ruin()
        ThreadResonance.objects.get(thread__owner=ysmay.sheet_data, resonance=self.ruin).delete()
        ysmay.threads.invalidate()
        before = self.corruption(ysmay)

        response = self._hobb_accepts(hobb, request)

        # She is not left unable to cast: it resolves, in Warmth, which adds no corruption.
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "resolved")
        self.assertShownTheBaseLine(response.data["result"]["power_ledger"])
        self.assertEqual(self.corruption(ysmay), before)


class WorkingACombatCastInAChosenResonance(_AYsmayWithATwoResonanceGift):
    """In a fight, the resonance she names when she declares is the one her cast is worked in.

    Ysmay (80 Primal, 20 Abyssal) declares a strike at Gristle from telnet, naming a
    resonance with ``variant=``; the round resolves later, and the cast is worked in the
    resonance she named. Worked in Ruin it adds corruption to Ruin, worked in Warmth it adds
    none, the same as a cast outside a fight.
    """

    def setUp(self) -> None:
        super().setUp()
        self.strike = TechniqueFactory(
            name="Ember Lash",
            gift=self.gift,
            intensity=20,
            control=40,
            anima_cost=1,
            effect_type=EffectTypeFactory(name="Ember Lash effect", base_power=5),
            action_category=ActionCategory.PHYSICAL,
            action_template=ensure_technique_cast_content(),
        )
        self.ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        grant_technique(self.ysmay.sheet_data.primary_persona, self.strike)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            risk_level=RiskLevel.MODERATE,
            room=self.room,
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        self.gristle = CombatOpponentFactory(
            encounter=self.encounter,
            name="Gristle",
            tier=OpponentTier.MOOK,
            health=5000,
            max_health=5000,
            threat_pool=pool,
        )
        add_participant(self.encounter, self.ysmay.sheet_data)
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

    def declared(self) -> CombatRoundAction:
        return CombatRoundAction.objects.get(
            participant__character_sheet=self.ysmay.sheet_data,
            round_number=self.encounter.round_number,
        )

    def read_the_ledger(self, declared: CombatRoundAction) -> dict:
        """The power ledger the combat log shows her for the round's cast, as the web reads it."""
        declared.refresh_from_db()
        self.assertIsNotNone(declared.interaction_id, "Her action left no log entry.")
        response = self.api(self.account_of(self.ysmay)).get(
            "/api/combat/action-outcome-details/",
            {"action_interaction_ids": str(declared.interaction_id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data[0]["power_ledger"]

    def declare_and_resolve(self, resonance) -> CombatRoundAction:
        told = self.telnet(self.ysmay, f"cast Ember Lash at Gristle variant={resonance.name}")
        self.assertIn(DECLARED_ON_TELNET, told)
        declared = self.declared()
        resolve_round(self.encounter, offense_check_fn=_clean_cast)
        # The resolved round's log shows the cast's power ledger, which opens on the base line.
        self.assertShownTheBaseLine(self.read_the_ledger(declared))
        return declared

    def test_a_combat_cast_worked_in_her_abyssal_resonance_corrupts_and_one_in_her_primal_does_not(
        self,
    ) -> None:
        before = self.corruption(self.ysmay)

        declared = self.declare_and_resolve(self.ruin)

        self.assertEqual(declared.cast_resonance, self.ruin)
        # Worked in Ruin, a cast of intensity 20 adds at least the light tenth (2) to Ruin only.
        after_ruin = self.corruption(self.ysmay)
        self.assertGreaterEqual(after_ruin["Ruin"] - before["Ruin"], 1)
        self.assertEqual(after_ruin["Warmth"], before["Warmth"])

        self.encounter.refresh_from_db()
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        declared = self.declare_and_resolve(self.warmth)

        self.assertEqual(declared.cast_resonance, self.warmth)
        self.assertEqual(self.corruption(self.ysmay), after_ruin)

    def test_a_resonance_not_on_the_thread_is_refused_at_declaration(self) -> None:
        anima_before = CharacterAnima.objects.get(character=self.ysmay.sheet_data).current

        told = self.telnet(self.ysmay, f"cast Ember Lash at Gristle variant={self.stray.name}")

        self.assertIn(NOT_ON_THREAD, told)
        self.assertFalse(CombatRoundAction.objects.exists())
        self.assertEqual(
            CharacterAnima.objects.get(character=self.ysmay.sheet_data).current, anima_before
        )

    def test_a_named_resonance_the_retired_thread_no_longer_holds_casts_in_the_default(
        self,
    ) -> None:
        # The Gift lists Ruin (Abyssal) and Warmth (Primal). She names Ruin while her thread
        # holds it; the thread is retired before the round resolves. With no thread the default
        # is the Gift's first in the order Primal, Celestial, Abyssal: Warmth. The cast goes
        # off without a refusal and adds no corruption: she is not corrupted by a default she
        # did not pick.
        self.gift.resonances.add(self.ruin, self.warmth)
        told = self.telnet(self.ysmay, f"cast Ember Lash at Gristle variant={self.ruin.name}")
        self.assertIn(DECLARED_ON_TELNET, told)
        self.assertEqual(self.declared().cast_resonance, self.ruin)
        before = self.corruption(self.ysmay)
        for thread in Thread.objects.filter(
            owner=self.ysmay.sheet_data, target_kind=TargetKind.GIFT, target_gift=self.gift
        ):
            thread.retired_at = timezone.now()
            thread.save(update_fields=["retired_at"])
        self.ysmay.threads.invalidate()

        resolve_round(self.encounter, offense_check_fn=_clean_cast)

        self.assertEqual(self.corruption(self.ysmay), before)
        self.assertNotIn("not part of this Gift's thread", self.said(self.ysmay))
        self.assertShownTheBaseLine(self.read_the_ledger(self.declared()))

    # -- the web client's declarations ------------------------------------------

    def dispatch(self, technique=None, slot="focused", **kwargs):
        technique = technique or self.strike
        with self.captureOnCommitCallbacks(execute=True):
            return self.api(self.account_of(self.ysmay)).post(
                f"/api/actions/characters/{self.ysmay.pk}/dispatch/",
                {
                    "ref": {
                        "backend": "combat",
                        "technique_id": technique.pk,
                        "action_slot": slot,
                    },
                    "kwargs": {
                        "effort_level": "medium",
                        "focused_opponent_target_id": self.gristle.pk,
                        **kwargs,
                    },
                },
                format="json",
            )

    def test_a_web_declaration_is_worked_in_the_resonance_she_chose_or_in_the_default(self) -> None:
        before = self.corruption(self.ysmay)

        # Round 1: she names Ruin. The declaration says it is recorded for the round.
        response = self.dispatch(preferred_resonance_id=self.ruin.pk)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["message"], DECLARED_ON_THE_WEB)
        self.assertEqual(self.declared().cast_resonance, self.ruin)
        resolve_round(self.encounter, offense_check_fn=_clean_cast)
        after_ruin = self.corruption(self.ysmay)
        self.assertGreaterEqual(after_ruin["Ruin"] - before["Ruin"], 1)
        self.assertEqual(after_ruin["Warmth"], before["Warmth"])

        # Round 2: she names none. The cast is worked in the default, Warmth, which adds none.
        self.encounter.refresh_from_db()
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        response = self.dispatch()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["message"], DECLARED_ON_THE_WEB)
        self.assertIsNone(self.declared().cast_resonance)
        resolve_round(self.encounter, offense_check_fn=_clean_cast)
        self.assertEqual(self.corruption(self.ysmay), after_ruin)

    def test_a_resonance_not_on_the_thread_is_refused_from_the_web_and_nothing_is_charged(
        self,
    ) -> None:
        sheet = self.ysmay.sheet_data
        _author_a_tier_one_pull(self.ruin)
        strand = _strand_on(sheet, self.ruin, self.strike)
        anima_before = CharacterAnima.objects.get(character=sheet).current
        self.assertEqual(self.balance(self.ysmay, self.ruin), 10)

        response = self.dispatch(
            preferred_resonance_id=self.stray.pk,
            pull_resonance_id=self.ruin.pk,
            pull_tier=1,
            pull_thread_ids=[strand.pk],
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["detail"], NOT_ON_THREAD)
        self.assertFalse(CombatRoundAction.objects.exists())
        self.assertFalse(CombatPull.objects.exists())
        self.assertEqual(CharacterAnima.objects.get(character=sheet).current, anima_before)
        # The pull was refused before it was charged: her Ruin balance is the 10 she had, as the
        # identity-mapped row she reads and as the database holds it.
        self.assertEqual(self.balance(self.ysmay, self.ruin), 10)
        self.assertEqual(
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=self.ruin)
            .values_list("balance", flat=True)
            .get(),
            10,
        )

    def test_a_resonance_the_web_names_that_does_not_exist_reads_not_found(self) -> None:
        for named in (987654, "ruin"):
            with self.subTest(named=named):
                response = self.dispatch(preferred_resonance_id=named)

                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["detail"], "Resonance not found.")
                self.assertFalse(CombatRoundAction.objects.exists())

    def test_a_different_declaration_in_the_same_round_drops_the_resonance_of_the_cast(
        self,
    ) -> None:
        self.assertEqual(self.dispatch(preferred_resonance_id=self.ruin.pk).status_code, 200)

        fled = self.web(self.ysmay, "combat_flee")

        self.assertTrue(fled.deferred)
        self.assertIsNone(self.declared().cast_resonance)

    def test_a_passive_declared_after_the_thread_lost_her_pick_goes_through(self) -> None:
        # She names Ruin for the focused cast; the thread then loses Ruin. Her passive call
        # names no resonance, so it is never refused over one she did not name: the lost pick
        # is dropped and the focused cast will run in the default.
        calm = TechniqueFactory(
            name="Steady Breath",
            gift=GiftFactory(),
            intensity=1,
            control=5,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_category=ActionCategory.MENTAL,
            action_template=ensure_technique_cast_content(),
        )
        grant_technique(self.ysmay.sheet_data.primary_persona, calm)
        self.assertEqual(self.dispatch(preferred_resonance_id=self.ruin.pk).status_code, 200)
        ThreadResonance.objects.get(
            thread__owner=self.ysmay.sheet_data, resonance=self.ruin
        ).delete()
        self.ysmay.threads.invalidate()

        response = self.dispatch(calm, "passive-mental")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["message"], DECLARED_ON_THE_WEB)
        declared = self.declared()
        self.assertEqual(declared.mental_passive, calm)
        self.assertEqual(declared.focused_action, self.strike)
        self.assertIsNone(declared.cast_resonance)

    def test_a_combat_cast_confirmed_at_the_soulfray_warning_keeps_its_strain_and_its_pull(
        self,
    ) -> None:
        # A cast stopped at the Soulfray warning is held whole: nothing is recorded, spent or
        # pulled until she accepts, and the accepted declaration is the one she typed.
        sheet = self.ysmay.sheet_data
        _author_a_tier_one_pull(self.warmth)
        _strand_on(sheet, self.warmth, self.strike)
        _soulfray_warning_up(self.ysmay)
        line = f"cast Ember Lash at Gristle variant={self.ruin.name} strain=2 pull=Strand:Warmth"

        told = self.telnet(self.ysmay, line)

        self.assertIn(SOULFRAY_WARNING, told)
        self.assertIn("accept soulfray", told)
        self.assertFalse(CombatRoundAction.objects.exists())
        self.assertFalse(CombatPull.objects.exists())
        self.assertEqual(self.balance(self.ysmay, self.warmth), 10)

        told = self.telnet(self.ysmay, "accept soulfray")

        self.assertIn("You steel yourself and complete the casting.", told)
        # Kept: the resonance she named, the 2 strain she committed, and the pull, which was
        # charged now (its cost of 1 off her Warmth).
        declared = self.declared()
        self.assertEqual(declared.cast_resonance, self.ruin)
        self.assertEqual(declared.strain_commitment, 2)
        self.assertTrue(CombatPull.objects.filter(participant=declared.participant).exists())
        self.assertEqual(self.balance(self.ysmay, self.warmth), 9)


class ACastStoppedAtTheSoulfrayWarning(_AYsmayWithATwoResonanceGift):
    """Ysmay casts Quiet Flame from telnet with Soulfray's first stage on her and confirms.

    She types every choice a cast takes: the Ruin form of her Gift's thread (a Ruin variant,
    unlocked at thread level 30, adds 10 to the technique's intensity), the base form, casting
    openly, 2 strain and a pull of her Strand thread paid by Warmth. Hand-worked:

    * Nothing is charged or cast while the warning stands.
    * Base form: Quiet Flame's own intensity of 20, not the Ruin form's 30. Worked in Ruin at
      80 percent Primal and 20 percent Abyssal (the light 10 percent): 20 x (10/10) x (10/10)
      x 10 / 100 = 2 corruption in Ruin; the Ruin form would add 3.
    * Strain: 2 anima on top of a base cost the technique's control (40 over its 20 intensity)
      wipes out, so 50 anima falls to 48. The pull's anima per thread is 0.
    * The pull: it costs 1 of the Warmth that pays, 10 falls to 9.
    """

    def setUp(self) -> None:
        super().setUp()
        self.flame = TechniqueFactory(
            name="Quiet Flame",
            gift=self.gift,
            intensity=20,
            control=40,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        TechniqueVariant.objects.create(
            parent_technique=self.flame,
            resonance=self.ruin,
            unlock_thread_level=30,
            name_override="Ruin Form",
            intensity_delta=10,
        )
        self.ysmay = self.caster("Ysmay", primal="80", abyssal="20")
        sheet = self.ysmay.sheet_data
        grant_technique(sheet.primary_persona, self.flame)
        gift_thread = Thread.objects.get(
            owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        gift_thread.level = 30
        gift_thread.save(update_fields=["level"])
        self.ysmay.threads.invalidate()
        _author_a_tier_one_pull(self.warmth)
        _strand_on(sheet, self.warmth, self.flame)
        _soulfray_warning_up(self.ysmay)
        # The scene's anti-spam memory is process-wide and keyed by sheet pk.
        pending_actions._LAST_ACTED.clear()
        self.addCleanup(pending_actions._LAST_ACTED.clear)

    def type_line(self, line: str) -> str:
        with (
            force_check_outcome(CheckOutcome.objects.get(name="Success")),
            self.captureOnCommitCallbacks(execute=True),
        ):
            return self.telnet(self.ysmay, line)

    def test_a_confirmed_cast_keeps_every_choice_she_made(self) -> None:
        sheet = self.ysmay.sheet_data
        before = self.corruption(self.ysmay)
        anima_before = CharacterAnima.objects.get(character=sheet).current
        self.assertEqual(anima_before, 50)

        told = self.type_line(
            "cast Quiet Flame variant=Ruin strain=2 base openly pull=Strand:Warmth"
        )

        # She is told what the warning says and how to go on, and nothing was charged or cast.
        self.assertIn(SOULFRAY_WARNING, told)
        self.assertIn("accept soulfray", told)
        self.assertFalse(SceneActionRequest.objects.filter(technique=self.flame).exists())
        self.assertEqual(self.corruption(self.ysmay), before)
        self.assertEqual(self.balance(self.ysmay, self.warmth), 10)
        self.assertEqual(CharacterAnima.objects.get(character=sheet).current, 50)

        told = self.type_line("accept soulfray")

        self.assertIn("Your technique resolves.", told)
        after = self.corruption(self.ysmay)
        # The resonance and the base form: Ruin gains the base form's 2, not the Ruin form's 3.
        self.assertEqual(after["Ruin"] - before["Ruin"], 2)
        self.assertEqual(after["Warmth"], before["Warmth"])
        # Strain: 2 anima spent. Pull: 1 Warmth spent.
        self.assertEqual(CharacterAnima.objects.get(character=sheet).current, 48)
        self.assertEqual(self.balance(self.ysmay, self.warmth), 9)
        # Casting openly, and the strain, are on the cast's record.
        request = SceneActionRequest.objects.get(technique=self.flame)
        self.assertTrue(request.cast_openly)
        self.assertEqual(request.strain_commitment, 2)
