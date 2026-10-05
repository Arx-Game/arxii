"""Display of power: a casting press, terms eased by morale, and the view fields (#4147)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.checks.social_target import SocialDifficulty
from world.combat.constants import FALTER_MORALE_THRESHOLD, SpectacleKind
from world.combat.models import SpectacleRecord
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueCapabilityRequirementFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import CharacterAnima
from world.magic.types.techniques import SoulfrayWarning
from world.standoffs.factories import StandoffApproachFactory, StandoffTermsFactory
from world.standoffs.services.verbs import standoff_press, terms_difficulty
from world.standoffs.services.view import build_standoff_view
from world.standoffs.tests.test_verbs import CHECK, SOCIAL, VerbBase, forced

CAST_ANIMA = 6


class TermsEaseByMoraleTests(VerbBase):
    def _extra_bands(self) -> int:
        terms = StandoffTermsFactory()
        with patch(SOCIAL, return_value=SocialDifficulty(difficulty=0)) as graded:
            terms_difficulty(
                self.group, self.participant.character_sheet, terms, config=self.config
            )
        return graded.call_args.kwargs["extra_bands"]

    def _set_morale(self, value: int) -> None:
        for member in self.members:
            member.morale = value
            member.save(update_fields=["morale"])

    def test_a_steady_group_gets_no_ease(self) -> None:
        self.assertEqual(self._extra_bands(), 0)

    def test_a_faltering_group_is_easier_to_bargain_with(self) -> None:
        self._set_morale(FALTER_MORALE_THRESHOLD)
        self.assertEqual(morale_state_for(self.members[0]), OpponentMoraleState.FALTER)
        self.assertEqual(self._extra_bands(), -self.config.terms_ease_faltering)

    def test_a_broken_group_is_easier_than_a_faltering_one(self) -> None:
        self._set_morale(0)
        self.assertEqual(morale_state_for(self.members[0]), OpponentMoraleState.BREAK)
        self.assertEqual(self._extra_bands(), -self.config.terms_ease_broken)

    def test_the_worst_member_decides(self) -> None:
        self.members[0].morale = 0
        self.members[0].save(update_fields=["morale"])
        self.assertEqual(self._extra_bands(), -self.config.terms_ease_broken)


class DisplayPressBase(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = self.participant.character_sheet
        self.approach = StandoffApproachFactory(casts_technique=True)
        self.technique = TechniqueFactory(anima_cost=CAST_ANIMA * 5, intensity=1, control=1)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        self.anima = CharacterAnimaFactory(character=self.sheet, current=50, maximum=50)

    def _spent(self) -> int:
        return 50 - CharacterAnima.objects.get(pk=self.anima.pk).current


class DisplayPressTests(DisplayPressBase):
    def test_a_success_spends_anima_shakes_the_group_and_eases_terms(self) -> None:
        before = [m.morale for m in self.members]
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach, self.technique)
        self.group.refresh_from_db()
        self.assertTrue(result.success)
        self.assertEqual(self.group.terms_ease, 1)
        self.assertGreater(self._spent(), 0)
        for member, old in zip(self.members, before, strict=True):
            member.refresh_from_db()
            self.assertLessEqual(member.morale, old)

    def test_an_ordinary_cast_that_earns_no_display_still_demoralizes_when_authored(self) -> None:
        self.approach.damages_morale = True
        self.approach.save(update_fields=["damages_morale"])
        before = self.members[0].morale
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach, self.technique)
        self.members[0].refresh_from_db()
        self.assertTrue(result.success)
        self.assertLess(self.members[0].morale, before)
        self.assertEqual(SpectacleRecord.objects.count(), 0)

    def test_an_ultimate_display_is_credited_as_a_spectacle(self) -> None:
        ultimate = UltimateTechniqueFactory(anima_cost=CAST_ANIMA * 5, intensity=1, control=1)
        CharacterTechniqueFactory(character=self.sheet, technique=ultimate)
        before = [m.morale for m in self.members]
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach, ultimate)
        records = SpectacleRecord.objects.filter(kind=SpectacleKind.ULTIMATE)
        self.assertEqual({r.opponent_id for r in records}, {m.pk for m in self.members})
        self.assertTrue(result.morale_line)
        for member, old in zip(self.members, before, strict=True):
            member.refresh_from_db()
            self.assertLess(member.morale, old)

    def test_a_failed_display_changes_nothing_but_the_cost(self) -> None:
        with patch(CHECK, return_value=forced(-1)):
            result = standoff_press(self.participant, self.group, self.approach, self.technique)
        self.group.refresh_from_db()
        self.assertFalse(result.success)
        self.assertEqual(self.group.terms_ease, 0)
        self.assertEqual(result.morale_line, "")


class DisplayRefusalTests(DisplayPressBase):
    def test_a_casting_approach_without_a_technique_is_refused(self) -> None:
        result = standoff_press(self.participant, self.group, self.approach)
        self.assertFalse(result.success)
        self.assertIsNone(result.success_level)
        self.assertEqual(self._spent(), 0)

    def test_a_technique_the_actor_does_not_know_is_refused(self) -> None:
        stranger = TechniqueFactory(anima_cost=CAST_ANIMA * 5)
        result = standoff_press(self.participant, self.group, self.approach, stranger)
        self.assertFalse(result.success)
        self.assertIsNone(result.success_level)
        self.assertEqual(self._spent(), 0)

    def test_a_non_casting_approach_refuses_a_technique(self) -> None:
        plain = StandoffApproachFactory()
        result = standoff_press(self.participant, self.group, plain, self.technique)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "That approach does not cast a technique.")
        self.assertEqual(self._spent(), 0)

    def test_a_known_technique_that_cannot_be_performed_is_refused(self) -> None:
        TechniqueCapabilityRequirementFactory(technique=self.technique, minimum_value=1)
        result = standoff_press(self.participant, self.group, self.approach, self.technique)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You cannot perform that technique right now.")
        self.assertIsNone(result.success_level)
        self.assertEqual(self._spent(), 0)

    def test_a_namesake_of_a_known_technique_is_refused(self) -> None:
        namesake = TechniqueFactory(name=self.technique.name.upper(), anima_cost=CAST_ANIMA * 5)
        result = standoff_press(self.participant, self.group, self.approach, namesake)
        self.assertEqual(result.message, "Choose one of your techniques to display.")
        self.assertEqual(self._spent(), 0)

    def test_the_readied_ultimate_may_be_displayed_without_being_known(self) -> None:
        ultimate = UltimateTechniqueFactory(anima_cost=CAST_ANIMA * 5, intensity=1, control=1)
        readied = SimpleNamespace(technique_id=ultimate.pk, technique=ultimate)
        with (
            patch("world.standoffs.services.verbs.readied_ultimate", return_value=readied),
            patch(CHECK, return_value=forced(1)),
        ):
            result = standoff_press(self.participant, self.group, self.approach, ultimate)
        self.assertTrue(result.success)
        self.assertGreater(self._spent(), 0)


WARNING = SoulfrayWarning(
    stage_name="Fraying", stage_description="Your soul is fraying.", has_death_risk=False
)
SOULFRAY_GATE = "world.magic.services.techniques.get_soulfray_warning"


class DisplaySoulfrayTests(DisplayPressBase):
    def test_soulfray_refuses_with_the_warning_and_spends_nothing(self) -> None:
        with patch(SOULFRAY_GATE, return_value=WARNING), patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach, self.technique)
        self.group.refresh_from_db()
        self.assertFalse(result.success)
        self.assertIsNone(result.success_level)
        self.assertEqual(result.soulfray_warning, WARNING)
        self.assertIn("Your soul is fraying.", result.message)
        self.assertEqual(self.group.terms_ease, 0)
        self.assertEqual(self._spent(), 0)

    def test_accepting_the_risk_casts(self) -> None:
        with patch(SOULFRAY_GATE, return_value=WARNING), patch(CHECK, return_value=forced(1)):
            result = standoff_press(
                self.participant,
                self.group,
                self.approach,
                self.technique,
                confirm_soulfray_risk=True,
            )
        self.assertTrue(result.success)
        self.assertIsNone(result.soulfray_warning)
        self.assertGreater(self._spent(), 0)


class DisplayViewTests(DisplayPressBase):
    def test_the_view_exposes_morale_casting_and_display_techniques(self) -> None:
        for member in self.members:
            member.morale = 0
            member.save(update_fields=["morale"])
        view = build_standoff_view(self.encounter, self.sheet)
        self.assertEqual(view.groups[0].morale_state, OpponentMoraleState.BREAK)
        by_id = {a.approach_id: a for a in view.approaches}
        self.assertTrue(by_id[self.approach.pk].casts_technique)
        self.assertEqual(
            [(t.technique_id, t.name) for t in view.display_techniques],
            [(self.technique.pk, self.technique.name)],
        )

    def test_a_steady_group_reads_steady(self) -> None:
        view = build_standoff_view(self.encounter, self.sheet)
        self.assertEqual(view.groups[0].morale_state, OpponentMoraleState.STEADY)


class DisplayRepeatRuleTests(DisplayPressBase):
    def test_a_repeated_display_never_falls_back_to_ordinary_morale_damage(self) -> None:
        self.approach.damages_morale = True
        self.approach.save(update_fields=["damages_morale"])
        ultimate = UltimateTechniqueFactory(anima_cost=CAST_ANIMA, intensity=1, control=1)
        CharacterTechniqueFactory(character=self.sheet, technique=ultimate)
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach, ultimate)
        records = SpectacleRecord.objects.count()
        morale = [m.morale for m in self.members]
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach, ultimate)
        self.assertEqual(result.morale_line, "")
        self.assertEqual(SpectacleRecord.objects.count(), records)
        for member, old in zip(self.members, morale, strict=True):
            member.refresh_from_db()
            self.assertEqual(member.morale, old)


class DisplayTechniqueQueryTests(DisplayPressBase):
    def _count(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            build_standoff_view(self.encounter, self.sheet)
        return len(ctx)

    def test_query_count_does_not_grow_with_technique_count(self) -> None:
        self._count()
        one = self._count()
        for _ in range(3):
            CharacterTechniqueFactory(character=self.sheet, technique=TechniqueFactory())
        self.assertEqual(len(build_standoff_view(self.encounter, self.sheet).display_techniques), 4)
        self.assertEqual(self._count(), one)

    def test_a_technique_listed_twice_appears_once(self) -> None:
        with patch(
            "world.magic.services.ultimates.readied_ultimate",
            return_value=type("K", (), {"technique": self.technique})(),
        ):
            view = build_standoff_view(self.encounter, self.sheet)
        self.assertEqual([t.technique_id for t in view.display_techniques], [self.technique.pk])


class DisplayActionDispatchTests(DisplayPressBase):
    def _press(self, **kwargs: int) -> object:
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="standoff_press")
        payload = {"group_id": self.group.pk, "approach_id": self.approach.pk, **kwargs}
        return dispatch_player_action(self.sheet.character, ref, payload).detail

    def test_a_known_technique_is_cast(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            detail = self._press(technique_id=self.technique.pk)
        self.assertTrue(detail.success)
        self.assertGreater(self._spent(), 0)

    def test_soulfray_refusal_carries_the_warning_and_confirm_passes_through(self) -> None:
        with patch(SOULFRAY_GATE, return_value=WARNING), patch(CHECK, return_value=forced(1)):
            refused = self._press(technique_id=self.technique.pk)
            self.assertFalse(refused.success)
            self.assertEqual(
                refused.data["soulfray_warning"],
                {
                    "stage_name": "Fraying",
                    "stage_description": "Your soul is fraying.",
                    "has_death_risk": False,
                },
            )
            self.assertEqual(self._spent(), 0)
            accepted = self._press(technique_id=self.technique.pk, confirm_soulfray_risk=True)
        self.assertTrue(accepted.success)
        self.assertGreater(self._spent(), 0)

    def test_an_unknown_technique_id_is_refused(self) -> None:
        detail = self._press(technique_id=999999)
        self.assertFalse(detail.success)
        self.assertEqual(detail.message, "No such technique.")
        self.assertEqual(self._spent(), 0)
