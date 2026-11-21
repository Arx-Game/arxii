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
* A caster with no thread on the Gift works it in the Gift's own first resonance.
"""

from __future__ import annotations

import math

from django.urls import reverse

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ensure_canonical_affinities,
)
from world.magic.models import Affinity, CharacterAnima, CharacterResonance, ThreadResonance
from world.magic.specialization.services import provision_latent_gift_thread
from world.scenes.action_constants import ConsentDecision
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


def _corruption_template(resonance) -> None:
    """The condition a resonance's corruption lives in, as the accrual service finds it."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})", has_progression=True, corruption_resonance=resonance
    )
    for order, threshold in enumerate([50, 200, 500, 1000, 1500], start=1):
        ConditionStageFactory(condition=template, stage_order=order, severity_threshold=threshold)


class WorkingACastInAChosenResonance(JourneyCase):
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
            CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
        if on_thread:
            # Warmth is listed first, so it leads the thread.
            provision_latent_gift_thread(sheet, self.gift, resonances=[self.warmth, self.ruin])
        return character

    def corruption(self, character) -> dict[str, int]:
        rows = CharacterResonance.objects.filter(character_sheet=character.sheet_data)
        return {row.resonance.name: row.corruption_current for row in rows}

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
        full = self.corruption(hobb)["Ruin"] - hobb_before
        light = self.corruption(ysmay)["Ruin"] - ysmay_before
        self.assertGreaterEqual(full, 1)
        self.assertGreaterEqual(light, 1)
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

    def test_a_caster_with_no_thread_on_the_gift_casts_in_the_gifts_first_resonance(self) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.ruin)
        technique = self._technique(gift)
        hobb = self.caster("Hobb", primal="40", abyssal="60", on_thread=False)
        grant_technique(hobb.sheet_data.primary_persona, technique)
        before = self.corruption(hobb)

        response = self.cast(hobb, technique=technique)

        self.assertEqual(response.status_code, 201, response.data)
        after = self.corruption(hobb)
        self.assertGreaterEqual(after["Ruin"] - before["Ruin"], 1)
        self.assertEqual(after["Warmth"], before["Warmth"])

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
        after = self.corruption(ysmay)
        self.assertGreaterEqual(after["Ruin"] - before["Ruin"], 1)
        self.assertEqual(after["Warmth"], before["Warmth"])

    def test_a_chosen_resonance_the_thread_lost_meanwhile_falls_back_to_the_default(self) -> None:
        ysmay, hobb, request = self._ask_hobb_to_accept_a_cast_in_ruin()
        ThreadResonance.objects.get(thread__owner=ysmay.sheet_data, resonance=self.ruin).delete()
        ysmay.threads.invalidate()
        before = self.corruption(ysmay)

        response = self._hobb_accepts(hobb, request)

        # She is not left unable to cast: it resolves in Warmth, which adds no corruption.
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.corruption(ysmay), before)
