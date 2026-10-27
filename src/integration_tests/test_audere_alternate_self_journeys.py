"""Journeys for the self a character becomes when she surges into Audere (#4731).

Staff flag one alternate self per character as her Audere self. Accepting the surge
puts her in it; when the fight ends and Audere ends, an AUTOMATIC self drops away on
its own, while a TALKED_DOWN self stays, holding a behavior-altering condition that
blocks `form revert` until she breaks free of it. Another alternate self already worn
is never swapped out. Names are invented.

The emergence runs on the accept's commit (``transaction.on_commit``), so every accept
here sits inside ``captureOnCommitCallbacks(execute=True)``, which runs the callbacks the
way the real commit would.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB
from rest_framework import status

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.constants import BreakFreeMode
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import remove_condition
from world.forms.constants import AlternateSelfRevertKind
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, FormType
from world.magic.audere import PendingAudereOffer
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    ResonanceFactory,
    ensure_canonical_affinities,
)
from world.magic.services.acting_aura import acting_aura
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


class _AudereSelfJourney(ResonanceCacheIsolationMixin, JourneyCase):
    """A played character with an open Audere offer and the gate authored."""

    def setUp(self) -> None:
        super().setUp()
        self.gate = build_audere_gate_fixture(tier_suffix=type(self).__name__)
        self.room = self.make_room("The Lantern")
        self.character = self.make_player("Ysmay", room=self.room)
        self.sheet = self.character.sheet_data
        self.celestial, _primal, self.abyssal = ensure_canonical_affinities()
        CharacterAuraFactory(
            character=self.sheet,
            celestial=Decimal("80.00"),
            primal=Decimal("0.00"),
            abyssal=Decimal("20.00"),
        )
        CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)
        CharacterEngagement.objects.create(
            character=self.sheet,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=ContentType.objects.get_for_model(ObjectDB),
            source_id=self.character.pk,
        )
        ConditionInstanceFactory(
            target=self.character,
            condition=self.gate.soulfray_template,
            current_stage=self.gate.soulfray_stage,
        )
        self.offer = PendingAudereOffer.objects.create(
            character_sheet=self.sheet,
            fired_intensity=20,
            soulfray_stage_order=self.gate.soulfray_stage.stage_order,
        )
        self.resonance = ResonanceFactory(affinity=self.abyssal)
        true_form = CharacterFormFactory(character=self.sheet, name="True", form_type=FormType.TRUE)
        CharacterFormStateFactory(character=self.sheet, active_form=true_form)

    def _flag(self, **kwargs):
        return AlternateSelfFactory(
            character=self.sheet,
            display_name="The Ashen Ysmay",
            resonance=self.resonance,
            emerges_at_audere=True,
            **kwargs,
        )

    def _worn(self):
        row = ActiveAlternateSelf.objects.filter(character=self.sheet).first()
        return None if row is None else row.alternate_self

    def _accept(self) -> str:
        """Type ``accept surge`` and let the accept commit."""
        with self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.character, "accept surge")
        return self.said(self.character)

    def _end_the_fight(self) -> None:
        """End a fight she took part in.

        No player command ends a fight: the round resolver calls
        ``cleanup_completed_encounter`` when one side is out, and staging a whole
        fight to that point would bury what this journey is about.
        """
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        cleanup_completed_encounter(encounter)

    def _audere_held(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.character, condition__name="Audere", resolved_at__isnull=True
        ).exists()


class AnAutomaticSelfComesAndGoesWithAudere(_AudereSelfJourney):
    def test_accept_by_telnet_wears_the_self_and_the_fight_ending_drops_it(self) -> None:
        alt = self._flag()
        self._accept()
        self.assertTold(self.character, "The surge takes hold.")
        self.assertTold(self.character, "You assume The Ashen Ysmay.")
        self.assertEqual(self._worn(), alt)
        self.assertTrue(self._audere_held())
        self.assertEqual(acting_aura(self.sheet).percent_for(self.abyssal), Decimal(100))

        self._end_the_fight()

        self.assertIsNone(self._worn())
        self.assertFalse(self._audere_held())
        self.assertEqual(acting_aura(self.sheet).percent_for(self.abyssal), Decimal(20))

    def test_accept_over_the_web_does_the_same(self) -> None:
        alt = self._flag()
        self.watch(self.character)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api(self.account_of(self.character)).post(
                "/api/magic/audere/respond/",
                {"offer_id": self.offer.pk, "accept": True},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertTrue(response.json()["accepted"])
        self.assertTold(self.character, "You assume The Ashen Ysmay.")
        self.assertEqual(self._worn(), alt)

        self._end_the_fight()
        self.assertIsNone(self._worn())

    def test_no_flagged_self_means_nothing_changes(self) -> None:
        AlternateSelfFactory(character=self.sheet, resonance=self.resonance)
        self._accept()
        self.assertNotTold(self.character, "You assume")
        self.assertTrue(self._audere_held())
        self.assertIsNone(self._worn())

    def test_audere_that_ran_out_mid_fight_still_drops_the_self_at_the_end(self) -> None:
        """A round duration strips the Audere condition without ``end_audere``."""
        alt = self._flag()
        self._accept()
        self.assertEqual(self._worn(), alt)
        remove_condition(self.character, ConditionTemplate.get_by_name("Audere"))
        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), alt)

        self._end_the_fight()
        self.assertIsNone(self._worn())


class ATalkedDownSelfStaysUntilSheBreaksFree(_AudereSelfJourney):
    def setUp(self) -> None:
        super().setUp()
        behavior = ConditionCategoryFactory(name="Ashen Fury", alters_behavior=True)
        self.fury = ConditionTemplateFactory(
            name="Ashen Fury",
            category=behavior,
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(),
            break_free_difficulty=10,
        )
        self.alt = self._flag(
            revert_kind=AlternateSelfRevertKind.TALKED_DOWN, emergence_condition=self.fury
        )

    def test_she_stays_transformed_until_the_fury_is_broken(self) -> None:
        self._accept()
        self.assertEqual(self._worn(), self.alt)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.character, condition=self.fury, resolved_at__isnull=True
            ).exists()
        )

        self._end_the_fight()
        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), self.alt)

        refused = self.telnet(self.character, "form revert")
        self.assertIn("You can't revert while not in control of yourself.", refused)
        self.assertEqual(self._worn(), self.alt)

        with force_check_outcome(CheckOutcomeFactory(name="Broke Free", success_level=2)):
            self.telnet(self.character, "breakfree")
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.character, condition=self.fury, resolved_at__isnull=True
            ).exists()
        )

        self.assertIn("You revert to your true self.", self.telnet(self.character, "form revert"))
        self.assertIsNone(self._worn())


class ABrokenSelfDoesNotStopTheSurge(_AudereSelfJourney):
    def test_a_persona_she_does_not_own_leaves_audere_accepted(self) -> None:
        self._flag(persona=PersonaFactory())
        self._accept()
        self.assertTold(self.character, "The surge takes hold.")
        self.assertNotTold(self.character, "You assume")
        self.assertTrue(self._audere_held())
        self.assertFalse(PendingAudereOffer.objects.filter(pk=self.offer.pk).exists())
        self.assertIsNone(self._worn())


class ADifferentSelfAlreadyWornIsNotSwapped(_AudereSelfJourney):
    def test_accept_succeeds_and_keeps_the_worn_self(self) -> None:
        self._flag()
        other = AlternateSelfFactory(character=self.sheet, display_name="The Quiet Ysmay")
        ActiveAlternateSelf.objects.update_or_create(
            character=self.sheet, defaults={"alternate_self": other}
        )
        self._accept()
        self.assertNotTold(self.character, "You assume")
        self.assertTrue(self._audere_held())
        self.assertEqual(self._worn(), other)

        self._end_the_fight()
        self.assertEqual(self._worn(), other)
