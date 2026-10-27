"""Journeys for an alternate self chosen in the Audere ultimate reveal (#4731, #4098).

Each alternate self that carries ultimates is a bond source in the reveal, beside
patrons and companions: its cards appear after the surge, and choosing one readies the
ultimate and puts her in that self. When Audere or the fight ends, an AUTOMATIC self
taken on this way drops away; a TALKED_DOWN self stays, holding a behavior-altering
condition that blocks `form revert` until she breaks free of it. A self she put on
herself beforehand is never reverted by Audere. Choosing a card while another self is
worn swaps them, unless she is not in control. Names are invented.

The self comes out on the choice's commit (``transaction.on_commit``), so every choice
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
from world.covenants.constants import RoleArchetype
from world.forms.constants import AlternateSelfRevertKind
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, AlternateSelf, FormType
from world.forms.services import assume_alternate_self
from world.magic.audere import PendingAudereOffer, end_audere
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    ResonanceFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
    ensure_canonical_affinities,
)
from world.magic.models import KnownUltimate
from world.magic.services.acting_aura import acting_aura
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory

_ULTIMATES_URL = "/api/magic/audere/ultimates/"
_CHOOSE_URL = "/api/magic/audere/ultimates/choose/"


class _AudereSelfJourney(ResonanceCacheIsolationMixin, JourneyCase):
    """A played character in a fight with an open Audere offer and two selves with
    ultimates: The Ashen Ysmay (Abyssal, a Sword ultimate) and The Quiet Ysmay (a
    Shield ultimate). The Plain Ysmay carries none."""

    def setUp(self) -> None:
        super().setUp()
        self.gate = build_audere_gate_fixture(tier_suffix=type(self).__name__)
        threshold = self.gate.threshold
        threshold.sword_reveal_label = "Edge"
        threshold.shield_reveal_label = "Wall"
        threshold.reveal_framing_text = ""
        threshold.save()
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
            engagement_type=EngagementType.COMBAT,
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

        self.cinder_crown = UltimateTechniqueFactory(
            name="Cinder Crown", archetype_alignment=RoleArchetype.SWORD
        )
        self.still_water = UltimateTechniqueFactory(
            name="Still Water", archetype_alignment=RoleArchetype.SHIELD
        )
        self.quiet = AlternateSelfFactory(character=self.sheet, display_name="The Quiet Ysmay")
        self.quiet.ultimate_techniques.add(self.still_water)
        self.plain = AlternateSelfFactory(character=self.sheet, display_name="The Plain Ysmay")

    def _ashen(self, **kwargs) -> AlternateSelf:
        ashen = AlternateSelfFactory(
            character=self.sheet,
            display_name="The Ashen Ysmay",
            resonance=self.resonance,
            **kwargs,
        )
        ashen.ultimate_techniques.add(self.cinder_crown)
        return ashen

    def _worn(self) -> AlternateSelf | None:
        row = ActiveAlternateSelf.objects.filter(character=self.sheet).first()
        return None if row is None else row.alternate_self

    def _surge(self) -> str:
        """Type ``accept surge``; the reveal listing follows the surge line."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.telnet(self.character, "accept surge")

    def _choose(self, number: int) -> str:
        """Type ``accept ultimate <number>`` and let the choice commit."""
        with self.captureOnCommitCallbacks(execute=True):
            self.telnet(self.character, f"accept ultimate {number}")
        return self.said(self.character)

    def _readied(self) -> str | None:
        known = KnownUltimate.objects.filter(character=self.sheet, readied=True).first()
        return None if known is None else known.technique.name

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

    def _charm(self) -> None:
        """An unrelated charm takes her out of control."""
        charm = ConditionTemplateFactory(
            name="Honeyed Words",
            category=ConditionCategoryFactory(name="Charm", alters_behavior=True),
        )
        ConditionInstanceFactory(target=self.character, condition=charm)
        self.assertFalse(self.sheet.in_control)


class EverySelfWithUltimatesIsABondCard(_AudereSelfJourney):
    def test_both_selves_are_listed_and_choosing_one_by_telnet_assumes_it(self) -> None:
        self._ashen()
        listing = self._surge()
        self.assertIn("The surge takes hold.", listing)
        self.assertIn("1) Edge (undiscovered; bond: The Ashen Ysmay)", listing)
        self.assertIn("2) Wall (undiscovered; bond: The Quiet Ysmay)", listing)
        self.assertNotIn("The Plain Ysmay", listing)
        self.assertNotIn("Cinder Crown", listing)
        self.assertIsNone(self._worn())

        chosen = self._choose(2)

        self.assertIn("Still Water", chosen)
        self.assertTold(self.character, "You assume The Quiet Ysmay.")
        self.assertEqual(self._worn(), self.quiet)
        self.assertEqual(self._readied(), "Still Water")

    def test_choosing_the_other_card_over_the_web_assumes_the_other_self(self) -> None:
        ashen = self._ashen()
        self._surge()
        self.watch(self.character)
        client = self.api(self.account_of(self.character))

        state = client.get(_ULTIMATES_URL, {"character_sheet_id": self.sheet.pk})

        self.assertEqual(state.status_code, status.HTTP_200_OK, state.content)
        groups = state.json()["reveal"]["groups"]
        self.assertEqual(
            [(g["source"], g["alternate_self_name"]) for g in groups],
            [("alternate_self", "The Ashen Ysmay"), ("alternate_self", "The Quiet Ysmay")],
        )
        card = groups[0]["cards"][0]
        self.assertEqual((card["kind"], card["label"], card["name"]), ("category", "Edge", ""))

        with self.captureOnCommitCallbacks(execute=True):
            chosen = client.post(
                _CHOOSE_URL,
                {"character_sheet_id": self.sheet.pk, "choice_key": card["choice_key"]},
                format="json",
            )

        self.assertEqual(chosen.status_code, status.HTTP_200_OK, chosen.content)
        self.assertEqual(chosen.json()["name"], "Cinder Crown")
        self.assertTold(self.character, "You assume The Ashen Ysmay.")
        self.assertEqual(self._worn(), ashen)
        self.assertEqual(acting_aura(self.sheet).percent_for(self.abyssal), Decimal(100))

    def test_a_self_with_no_display_name_is_named_by_its_persona_or_generically(
        self,
    ) -> None:
        self.quiet.display_name = ""
        self.quiet.persona = PersonaFactory(name="Wren of the Ash")
        self.quiet.save(update_fields=["display_name", "persona"])
        nameless = AlternateSelfFactory(character=self.sheet, display_name="")
        nameless.ultimate_techniques.add(self.cinder_crown)

        listing = self._surge()

        self.assertIn("(undiscovered; bond: Wren of the Ash)", listing)
        self.assertIn("(undiscovered; bond: an alternate self)", listing)
        self.assertNotIn("bond: )", listing)
        state = self.api(self.account_of(self.character)).get(
            _ULTIMATES_URL, {"character_sheet_id": self.sheet.pk}
        )
        self.assertEqual(
            sorted(g["alternate_self_name"] for g in state.json()["reveal"]["groups"]),
            ["Wren of the Ash", "an alternate self"],
        )

    def test_a_character_whose_selves_carry_no_ultimates_sees_no_self_card(self) -> None:
        self.quiet.ultimate_techniques.clear()
        listing = self._surge()
        self.assertIn("The surge takes hold.", listing)
        self.assertNotIn("Ultimates:", listing)
        self.assertNotIn("bond:", listing)

    def test_a_non_ultimate_technique_row_never_makes_a_card(self) -> None:
        """Rows written past the admin's ultimates-only picker are still not offered."""
        self.quiet.ultimate_techniques.clear()
        self.quiet.ultimate_techniques.add(TechniqueFactory(name="Plain Strike"))
        listing = self._surge()
        self.assertNotIn("bond:", listing)


class AnAutomaticSelfComesAndGoesWithAudere(_AudereSelfJourney):
    def test_audere_ending_drops_the_self(self) -> None:
        """No player command ends Audere outside a fight; ``end_audere`` is the seam the
        encounter cleanup and the Audere round countdown both call."""
        ashen = self._ashen()
        self._surge()
        self._choose(1)
        self.assertEqual(self._worn(), ashen)

        end_audere(self.character)

        self.assertIsNone(self._worn())
        self.assertFalse(self._audere_held())
        self.assertEqual(acting_aura(self.sheet).percent_for(self.abyssal), Decimal(20))

    def test_the_fight_ending_drops_the_self(self) -> None:
        self._ashen()
        self._surge()
        self._choose(1)

        self._end_the_fight()

        self.assertIsNone(self._worn())
        self.assertFalse(self._audere_held())
        self.assertIsNone(self._readied())

    def test_audere_that_ran_out_mid_fight_still_drops_the_self_at_the_end(self) -> None:
        """A round duration strips the Audere condition without ``end_audere``."""
        ashen = self._ashen()
        self._surge()
        self._choose(1)
        remove_condition(self.character, ConditionTemplate.get_by_name("Audere"))
        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), ashen)

        self._end_the_fight()
        self.assertIsNone(self._worn())


class ASelfSheWoreBeforeAudereStays(_AudereSelfJourney):
    """She put on The Quiet Ysmay herself before the surge."""

    def setUp(self) -> None:
        super().setUp()
        assume_alternate_self(self.sheet, self.quiet)

    def test_choosing_the_worn_selfs_card_keeps_it_hers_and_the_fight_end_leaves_it(
        self,
    ) -> None:
        self._surge()
        self._choose(1)
        self.assertNotTold(self.character, "You assume")
        self.assertEqual(self._readied(), "Still Water")
        self.assertEqual(self._worn(), self.quiet)

        self._end_the_fight()

        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), self.quiet)

    def test_choosing_another_selfs_card_swaps_them(self) -> None:
        ashen = self._ashen()
        self._surge()
        self._choose(1)
        self.assertTold(self.character, "You assume The Ashen Ysmay.")
        self.assertEqual(self._worn(), ashen)

        # The chosen self was taken on at Audere, so it drops away; she comes back to
        # her true self, not to the one she wore before.
        self._end_the_fight()
        self.assertIsNone(self._worn())

    def test_a_broken_self_never_takes_her_out_of_the_one_she_wears(self) -> None:
        self._ashen(persona=PersonaFactory())
        self._surge()
        with self.assertLogs("world.forms.services", level="WARNING") as logged:
            self._choose(1)
        self.assertIn("its form or persona is not hers", logged.output[0])
        self.assertNotTold(self.character, "You assume")
        self.assertEqual(self._worn(), self.quiet)

    def test_the_swap_is_refused_while_she_is_not_in_control(self) -> None:
        self._ashen()
        self._surge()
        self._charm()

        self._choose(1)

        self.assertTold(
            self.character,
            "You cannot leave The Quiet Ysmay while not in control of yourself, "
            "so The Ashen Ysmay does not come out.",
        )
        self.assertNotTold(self.character, "You assume")
        self.assertEqual(self._worn(), self.quiet)
        self.assertEqual(self._readied(), "Cinder Crown")


class _ATalkedDownSelf(_AudereSelfJourney):
    """Her Ashen self must be talked down: it holds an Ashen Fury condition."""

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
        self.alt = self._ashen(
            revert_kind=AlternateSelfRevertKind.TALKED_DOWN, emergence_condition=self.fury
        )

    def _fury_held(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.character, condition=self.fury, resolved_at__isnull=True
        ).exists()


class ATalkedDownSelfStaysUntilSheBreaksFree(_ATalkedDownSelf):
    def test_she_stays_transformed_until_the_fury_is_broken(self) -> None:
        self._surge()
        self._choose(1)
        self.assertEqual(self._worn(), self.alt)
        self.assertTrue(self._fury_held())

        self._end_the_fight()
        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), self.alt)

        refused = self.telnet(self.character, "form revert")
        self.assertIn("You can't revert while not in control of yourself.", refused)
        self.assertEqual(self._worn(), self.alt)

        with force_check_outcome(CheckOutcomeFactory(name="Broke Free", success_level=2)):
            self.telnet(self.character, "breakfree")
        self.assertFalse(self._fury_held())

        self.assertIn("You revert to your true self.", self.telnet(self.character, "form revert"))
        self.assertIsNone(self._worn())


class AFriendRalliesHerOutOfTheFury(_ATalkedDownSelf):
    """Hobb talks her down: his rally backs her break-free, and once the fury is broken
    `form revert` works."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.hobb)

    def test_the_rally_backs_her_break_free_and_she_reverts(self) -> None:
        self._surge()
        self._choose(1)
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


class ABrokenSelfDoesNotUndoTheChoice(_AudereSelfJourney):
    def test_a_persona_she_does_not_own_leaves_the_ultimate_readied(self) -> None:
        self._ashen(persona=PersonaFactory())
        self._surge()
        with self.assertLogs("world.forms.services", level="WARNING") as logged:
            self._choose(1)
        self.assertIn("its form or persona is not hers", logged.output[0])
        self.assertNotTold(self.character, "You assume")
        self.assertTrue(self._audere_held())
        self.assertEqual(self._readied(), "Cinder Crown")
        self.assertIsNone(self._worn())


class ABlockedRevertDoesNotStopTheFightEnding(_AudereSelfJourney):
    """An automatic self wants to drop at fight's end, but an unrelated charm holds her."""

    def test_the_fight_ends_and_she_stays_in_the_self_with_the_refusal_logged(self) -> None:
        ashen = self._ashen()
        self._surge()
        self._choose(1)
        self.assertEqual(self._worn(), ashen)
        self._charm()

        with self.assertLogs("world.forms.services", level="INFO") as logged:
            self._end_the_fight()

        self.assertFalse(self._audere_held())
        self.assertEqual(self._worn(), ashen)
        # end_audere and the encounter cleanup each try the revert; both are refused.
        self.assertEqual(
            set(logged.output),
            {
                "INFO:world.forms.services:Audere ended but Ysmay is not in control; "
                "alternate self The Ashen Ysmay stays until reverted."
            },
        )


class StaffAuthorTheAudereSelfInTheAdmin(RefusedAdminSaveCase):
    """Staff give a character's alternate self its ultimates and set how it ends, on the
    stock admin page."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.fury = ConditionTemplateFactory(
            name="Ashen Fury",
            category=ConditionCategoryFactory(name="Ashen Fury", alters_behavior=True),
        )
        self.ultimate = UltimateTechniqueFactory(name="Cinder Crown")
        self.ordinary = TechniqueFactory(name="Plain Strike")
        self.first = AlternateSelfFactory(character=self.sheet, display_name="The Ashen Ysmay")
        self.url = reverse("admin:arxii_alternateself_change", args=[self.first.pk])

    def test_the_change_form_shows_the_three_fields(self) -> None:
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        form = page.context["adminform"].form
        self.assertEqual(form.fields["ultimate_techniques"].label, "Ultimate techniques")
        self.assertEqual(form.fields["revert_kind"].label, "Revert kind")
        self.assertEqual(form.fields["emergence_condition"].label, "Emergence condition")
        offered = set(form.fields["ultimate_techniques"].queryset)
        self.assertIn(self.ultimate, offered)
        self.assertNotIn(self.ordinary, offered)
        for name in ("ultimate_techniques", "revert_kind", "emergence_condition"):
            self.assertContains(page, f'name="{name}"')

    def test_staff_save_a_talked_down_self_with_an_ultimate_and_the_row_holds_it(self) -> None:
        data = self.change_post(self.url)
        data["ultimate_techniques"] = [str(self.ultimate.pk)]
        data["revert_kind"] = AlternateSelfRevertKind.TALKED_DOWN
        data["emergence_condition"] = str(self.fury.pk)

        saved = self.client.post(self.url, data)

        self.assertEqual(saved.status_code, 302, saved.content[:2000])
        row = AlternateSelf.objects.get(pk=self.first.pk)
        self.assertEqual(row.revert_kind, "talked_down")
        self.assertEqual(row.emergence_condition, self.fury)
        self.assertEqual(list(row.ultimate_techniques.all()), [self.ultimate])

    def test_a_technique_that_is_not_an_ultimate_is_refused(self) -> None:
        data = self.change_post(self.url)
        data["ultimate_techniques"] = [str(self.ordinary.pk)]

        refused = self.client.post(self.url, data)

        self.assertEqual(refused.status_code, 200)
        self.assertIn("ultimate_techniques", refused.context["adminform"].form.errors)
        self.assertFalse(AlternateSelf.objects.get(pk=self.first.pk).ultimate_techniques.exists())


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
