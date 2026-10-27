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
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.urls import reverse
from evennia.objects.models import ObjectDB
from rest_framework import status

from integration_tests.harness import JourneyCase
from integration_tests.test_refused_admin_saves_journeys import RefusedAdminSaveCase
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatEncounter
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
from world.forms.models import ActiveAlternateSelf, AlternateSelf, FormType
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
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory


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

    def _end_the_fight(self) -> CombatEncounter:
        """End a fight she took part in.

        No player command ends a fight: the round resolver calls
        ``cleanup_completed_encounter`` when one side is out, and staging a whole
        fight to that point would bury what this journey is about.
        """
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        cleanup_completed_encounter(encounter)
        return encounter

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


class _ATalkedDownSelf(_AudereSelfJourney):
    """Her flagged self must be talked down: it holds an Ashen Fury condition."""

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


class ATalkedDownSelfStaysUntilSheBreaksFree(_ATalkedDownSelf):
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


class AFriendRalliesHerOutOfTheFury(_ATalkedDownSelf):
    """Hobb talks her down: his rally backs her break-free, and once the fury is broken
    `form revert` works."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.hobb)

    def _fury_held(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.character, condition=self.fury, resolved_at__isnull=True
        ).exists()

    def test_the_rally_backs_her_break_free_and_she_reverts(self) -> None:
        self._accept()
        self._end_the_fight()
        refused = self.telnet(self.character, "form revert")
        self.assertIn("You can't revert while not in control of yourself.", refused)

        with patch("world.checks.services.random.randint", return_value=95):
            rallied = self.telnet(self.hobb, "rally Ysmay")
        self.assertIn(
            "You rally Ysmay, granting them +5 to their next attempt to break free.", rallied
        )
        self.assertTrue(self._fury_held())
        self.assertEqual(self._worn(), self.alt)

        with force_check_outcome(CheckOutcomeFactory(name="Broke Free", success_level=2)):
            freed = self.telnet(self.character, "breakfree")
        self.assertIn("You shatter the effect gripping your mind!", freed)
        self.assertFalse(self._fury_held())

        self.assertIn("You revert to your true self.", self.telnet(self.character, "form revert"))
        self.assertIsNone(self._worn())


class ABlockedRevertDoesNotStopTheFightEnding(_AudereSelfJourney):
    """An automatic self wants to drop at fight's end, but an unrelated charm holds her."""

    def test_the_fight_ends_and_she_stays_in_the_self_with_the_refusal_logged(self) -> None:
        alt = self._flag()
        self._accept()
        self.assertEqual(self._worn(), alt)
        charm = ConditionTemplateFactory(
            name="Honeyed Words",
            category=ConditionCategoryFactory(name="Charm", alters_behavior=True),
        )
        ConditionInstanceFactory(target=self.character, condition=charm)
        self.assertFalse(self.sheet.in_control)

        with self.assertLogs("world.forms.services", level="INFO") as logged:
            self._end_the_fight()

        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), alt)
        # end_audere and the encounter cleanup each try the revert; both are refused.
        self.assertEqual(
            set(logged.output),
            {
                "INFO:world.forms.services:Audere ended but Ysmay is not in control; "
                "alternate self The Ashen Ysmay stays until reverted."
            },
        )


class StaffAuthorTheAudereSelfInTheAdmin(RefusedAdminSaveCase):
    """Staff flag a character's alternate self and set how it ends, on the stock admin page."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.fury = ConditionTemplateFactory(
            name="Ashen Fury",
            category=ConditionCategoryFactory(name="Ashen Fury", alters_behavior=True),
        )
        self.first = AlternateSelfFactory(character=self.sheet, display_name="The Ashen Ysmay")
        self.url = reverse("admin:arxii_alternateself_change", args=[self.first.pk])

    def test_the_change_form_shows_the_three_fields(self) -> None:
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        form = page.context["adminform"].form
        self.assertEqual(form.fields["emerges_at_audere"].label, "Emerges at audere")
        self.assertEqual(form.fields["revert_kind"].label, "Revert kind")
        self.assertEqual(form.fields["emergence_condition"].label, "Emergence condition")
        for name in ("emerges_at_audere", "revert_kind", "emergence_condition"):
            self.assertContains(page, f'name="{name}"')

    def test_staff_flag_a_talked_down_self_with_a_condition_and_the_row_holds_it(self) -> None:
        data = self.change_post(self.url)
        data["emerges_at_audere"] = "on"
        data["revert_kind"] = AlternateSelfRevertKind.TALKED_DOWN
        data["emergence_condition"] = str(self.fury.pk)

        saved = self.client.post(self.url, data)

        self.assertEqual(saved.status_code, 302, saved.content[:2000])
        row = AlternateSelf.objects.get(pk=self.first.pk)
        self.assertTrue(row.emerges_at_audere)
        self.assertEqual(row.revert_kind, "talked_down")
        self.assertEqual(row.emergence_condition, self.fury)

    def test_a_second_flagged_self_on_the_same_character_is_refused_with_a_form_error(
        self,
    ) -> None:
        AlternateSelf.objects.filter(pk=self.first.pk).update_with_reason(
            reason="flag the first self without the admin", emerges_at_audere=True
        )
        second = AlternateSelfFactory(character=self.sheet, display_name="The Quiet Ysmay")
        url = reverse("admin:arxii_alternateself_change", args=[second.pk])
        data = self.change_post(url)
        data["emerges_at_audere"] = "on"

        refused = self.client.post(url, data)

        self.assertEqual(refused.status_code, 200)
        self.assertContains(
            refused, "Constraint \u201cone_audere_alternate_self_per_character\u201d is violated."
        )
        self.assertFalse(AlternateSelf.objects.get(pk=second.pk).emerges_at_audere)
        self.assertFalse(
            AlternateSelf.objects.filter(pk=second.pk, emerges_at_audere=True).exists()
        )


class TheDatabaseRefusesAnUnendableSelf(JourneyCase):
    """Whatever staff or a script does, the rows cannot describe a self that never ends
    or an automatic self that a condition holds in place."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.fury = ConditionTemplateFactory(
            name="Ashen Fury",
            category=ConditionCategoryFactory(name="Ashen Fury", alters_behavior=True),
        )

    def test_a_talked_down_self_without_a_condition_is_refused(self) -> None:
        alt = AlternateSelfFactory(character=self.sheet)
        with self.assertRaises(IntegrityError) as ctx, transaction.atomic():
            AlternateSelf.objects.filter(pk=alt.pk).update_with_reason(
                reason="a journey writing past clean() to reach the database constraint",
                revert_kind=AlternateSelfRevertKind.TALKED_DOWN,
            )
        self.assertIn("alternate_self_talked_down_needs_condition", str(ctx.exception))

    def test_an_automatic_self_with_a_condition_is_refused(self) -> None:
        alt = AlternateSelfFactory(character=self.sheet)
        with self.assertRaises(IntegrityError) as ctx, transaction.atomic():
            AlternateSelf.objects.filter(pk=alt.pk).update_with_reason(
                reason="a journey writing past clean() to reach the database constraint",
                emergence_condition=self.fury,
            )
        self.assertIn("alternate_self_talked_down_needs_condition", str(ctx.exception))
