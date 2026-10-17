"""Named NPCs as standoff groups and the language gate (#4373, slice 3 of #4121)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.conditions.factories import ConditionTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.mechanics.models import ObjectProperty
from world.npc_services.factories import NpcRegardFactory
from world.scenes.services import active_persona_for_sheet
from world.species.factories import make_language_with_target
from world.standoffs.constants import (
    REFUSAL_NO_LANGUAGE,
    REFUSAL_NO_SHARED_LANGUAGE,
    DriveStrength,
    StandoffGroupState,
)
from world.standoffs.factories import (
    StandoffApproachFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig
from world.standoffs.services.gm_view import build_gm_standoff_view, build_standoff_summary
from world.standoffs.services.language import group_languages, language_refusal
from world.standoffs.services.placement import placement_profile, stamp_opponent
from world.standoffs.services.profile import PERSONA_DRIVE_STRENGTH, group_drives
from world.standoffs.services.state import active_members, attack_line, open_standoff
from world.standoffs.services.verbs import (
    press_difficulty,
    standoff_press,
    standoff_read,
    standoff_terms,
    terms_difficulty,
)
from world.standoffs.services.view import build_standoff_view
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"


def forced(level: int) -> SimpleNamespace:
    outcome = CheckOutcomeFactory(name=f"Named tier {level}", success_level=level)
    return SimpleNamespace(success_level=level, outcome=outcome, chart=None)


def speak(sheet: object, language: object, value: int = 40) -> None:
    """Give ``sheet`` trained fluency in ``language``."""
    CharacterTraitValueFactory(character=sheet, trait=language.trait, value=value)


class NamedNPCBase(TestCase):
    """A sellsword template group of two and a named NPC (a persona) on the same template."""

    def setUp(self) -> None:
        # setUp, not setUpTestData: tests mutate groups, opponents and the config.
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.sheet = self.participant.character_sheet
        self.template = CreatureTemplateFactory(tier=OpponentTier.MOOK, cause=CauseKind.NONE)
        self.sellswords = [
            CombatOpponentFactory(encounter=self.encounter, creature_template=self.template)
            for _ in range(2)
        ]
        self.npc_sheet = CharacterSheetFactory()
        self.persona = self.npc_sheet.primary_persona
        self.prudent = PropertyFactory(name="Prudent (test)")
        self.persona.properties.add(self.prudent)
        self.npc = CombatOpponentFactory(
            encounter=self.encounter,
            creature_template=self.template,
            persona=self.persona,
            name=self.persona.name,
        )
        self.config = StandoffConfig.load()
        self.config.read_check_type = CheckTypeFactory()
        self.config.terms_check_type = CheckTypeFactory()
        self.config.pass_condition = ConditionTemplateFactory()
        self.config.regard_per_band = 100
        self.config.regard_max_bands = 2
        self.config.save()
        groups = open_standoff(self.encounter)
        self.company = next(g for g in groups if g.persona_id is None)
        self.named = next(g for g in groups if g.persona_id is not None)


class NamedGroupTests(NamedNPCBase):
    def test_a_named_npc_is_its_own_group(self) -> None:
        self.assertEqual(self.named.persona, self.persona)
        self.assertEqual(self.named.creature_template, self.template)
        self.assertEqual(active_members(self.named), [self.npc])
        self.assertCountEqual(active_members(self.company), self.sellswords)

    def test_the_group_is_named_by_the_persona(self) -> None:
        self.assertEqual(self.named.name, self.persona.name)
        self.assertEqual(self.named.referent, self.persona.name)
        self.assertEqual(self.company.referent, f"the {self.template.name}")

    def test_drives_come_from_the_persona_properties(self) -> None:
        drives = group_drives(self.named)
        self.assertEqual([d.property_id for d in drives], [self.prudent.pk])
        self.assertEqual(drives[0].strength, PERSONA_DRIVE_STRENGTH)

    def test_nothing_is_stamped_on_the_npc_character(self) -> None:
        stamp_opponent(self.npc, placement_profile(self.template, persona=self.persona))
        self.assertFalse(
            ObjectProperty.objects.filter(object_id=self.npc.objectdb_id).exists(),
            "a named NPC's own character must never carry standoff drives",
        )

    def test_attack_line_names_the_npc(self) -> None:
        self.assertEqual(attack_line([self.named]), f"{self.persona.name} attacks!")
        self.assertEqual(
            attack_line([self.company, self.named]),
            f"The {self.template.name} and {self.persona.name} attack!",
        )

    def test_the_named_group_can_be_read_pressed_and_settled(self) -> None:
        approach = StandoffApproachFactory()
        terms = StandoffTermsFactory()
        with patch(CHECK, return_value=forced(2)):
            read = standoff_read(self.participant, self.named)
        self.assertTrue(read.success)
        self.assertEqual([r.drive_id for r in read.revealed], [self.prudent.pk])
        with patch(CHECK, return_value=forced(1)):
            pressed = standoff_press(self.participant, self.named, approach)
        self.assertTrue(pressed.success)
        with patch(CHECK, return_value=forced(1)):
            settled = standoff_terms(self.participant, self.named, terms)
        self.assertTrue(settled.settled)
        self.named.refresh_from_db()
        self.company.refresh_from_db()
        self.assertEqual(self.named.state, StandoffGroupState.SETTLED)
        self.assertEqual(self.company.state, StandoffGroupState.OPEN)

    def test_onlooker_summary_names_the_npc(self) -> None:
        names = [group.name for group in build_standoff_summary(self.encounter).groups]
        self.assertIn(self.persona.name, names)


class RegardTests(NamedNPCBase):
    def _regard(self, value: int) -> None:
        NpcRegardFactory(
            holder_persona=self.persona,
            target_persona=active_persona_for_sheet(self.sheet),
            value=value,
        )

    def test_dislike_hardens_a_press_and_terms(self) -> None:
        approach = StandoffApproachFactory()
        terms = StandoffTermsFactory()
        neutral_press = press_difficulty(self.named, self.sheet, approach).difficulty
        neutral_terms = terms_difficulty(self.named, self.sheet, terms).difficulty
        self._regard(-150)
        self.assertGreater(
            press_difficulty(self.named, self.sheet, approach).difficulty, neutral_press
        )
        self.assertGreater(
            terms_difficulty(self.named, self.sheet, terms).difficulty, neutral_terms
        )

    def _base(self, group: object, approach: object) -> int:
        """The caller-supplied base the press hands the shared difficulty function."""
        from world.checks.social_target import social_target_difficulty

        with patch(
            "world.standoffs.services.verbs.social_target_difficulty",
            wraps=social_target_difficulty,
        ) as shared:
            press_difficulty(group, self.sheet, approach)
        return shared.call_args.kwargs["base_difficulty"]

    def test_favor_eases_and_is_capped(self) -> None:
        from world.scenes.action_constants import DIFFICULTY_BAND_STEP

        approach = StandoffApproachFactory()
        self.assertEqual(self._base(self.named, approach), 0)
        regard = NpcRegardFactory(
            holder_persona=self.persona,
            target_persona=active_persona_for_sheet(self.sheet),
            value=200,
        )
        self.assertEqual(self._base(self.named, approach), -2 * DIFFICULTY_BAND_STEP)
        regard.value = 900
        regard.save(update_fields=["value"])
        self.assertEqual(
            self._base(self.named, approach),
            -2 * DIFFICULTY_BAND_STEP,
            "regard_max_bands caps the shift",
        )

    def test_template_groups_have_no_regard(self) -> None:
        approach = StandoffApproachFactory()
        before = press_difficulty(self.company, self.sheet, approach).difficulty
        self._regard(-500)
        self.assertEqual(press_difficulty(self.company, self.sheet, approach).difficulty, before)

    def test_the_viewer_sees_the_direction_and_the_gm_sees_the_value(self) -> None:
        StandoffApproachFactory()
        self._regard(-150)
        view = build_standoff_view(self.encounter, self.sheet)
        named_levers = [
            lever.text
            for approach in view.approaches
            if approach.group_id == self.named.pk
            for lever in approach.levers
        ]
        self.assertIn(f"{self.persona.name}'s regard for you: harder", named_levers)
        self.assertNotIn("-150", " ".join(named_levers))
        gm_group = next(
            g for g in build_gm_standoff_view(self.encounter).groups if g.group_id == self.named.pk
        )
        self.assertTrue(gm_group.is_named_npc)
        self.assertEqual([(r.regard, r.label) for r in gm_group.regards], [(-150, "negative")])


class LanguageGateTests(NamedNPCBase):
    def setUp(self) -> None:
        super().setUp()
        self.common, _target = make_language_with_target("Riverland test common")
        self.verbal = StandoffApproachFactory(is_verbal=True)
        self.gesture = StandoffApproachFactory(is_verbal=False)
        self.terms = StandoffTermsFactory()

    def _template_speaks(self) -> None:
        self.template.language = self.common
        self.template.save(update_fields=["language"])

    def test_a_shared_language_lets_the_verbal_approach_through(self) -> None:
        self._template_speaks()
        speak(self.sheet, self.common)
        self.assertEqual(language_refusal(self.company, self.sheet, verbal=True), "")
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.company, self.verbal)
        self.assertTrue(result.success)

    def test_no_shared_language_refuses_verbal_approaches_and_terms_without_a_roll(self) -> None:
        self._template_speaks()
        with patch(CHECK) as roll:
            pressed = standoff_press(self.participant, self.company, self.verbal)
            named = standoff_terms(self.participant, self.company, self.terms)
        roll.assert_not_called()
        self.assertEqual(pressed.message, REFUSAL_NO_SHARED_LANGUAGE)
        self.assertEqual(named.message, REFUSAL_NO_SHARED_LANGUAGE)

    def test_gestures_and_reads_need_no_language(self) -> None:
        self._template_speaks()
        speak(self.npc_sheet, self.common)
        with patch(CHECK, return_value=forced(1)):
            self.assertTrue(standoff_press(self.participant, self.company, self.gesture).success)
            self.assertTrue(standoff_read(self.participant, self.named).success)

    def test_a_group_with_no_language_cannot_be_talked_to_but_takes_terms(self) -> None:
        self.assertEqual(
            language_refusal(self.company, self.sheet, verbal=True), REFUSAL_NO_LANGUAGE
        )
        self.assertEqual(language_refusal(self.company, self.sheet, verbal=False), "")

    def test_the_view_lists_refused_entries_with_the_reason(self) -> None:
        self._template_speaks()
        view = build_standoff_view(self.encounter, self.sheet)
        by_id = {a.approach_id: a for a in view.approaches if a.group_id == self.company.pk}
        self.assertEqual(by_id[self.verbal.pk].refusal, REFUSAL_NO_SHARED_LANGUAGE)
        self.assertEqual(by_id[self.gesture.pk].refusal, "")
        self.assertTrue(by_id[self.verbal.pk].grade, "a refused approach still shows its grade")
        terms = [t for t in view.terms if t.group_id == self.company.pk]
        self.assertEqual({t.refusal for t in terms}, {REFUSAL_NO_SHARED_LANGUAGE})

    def test_a_named_npc_understands_its_character_languages(self) -> None:
        self.assertEqual(group_languages(self.named), [])
        speak(self.npc_sheet, self.common)
        self.assertEqual(group_languages(self.named), [self.common])
        self.assertEqual(
            language_refusal(self.named, self.sheet, verbal=True), REFUSAL_NO_SHARED_LANGUAGE
        )
        speak(self.sheet, self.common, value=5)
        self.assertEqual(language_refusal(self.named, self.sheet, verbal=True), "")

    def test_the_gm_sees_what_each_group_speaks(self) -> None:
        self._template_speaks()
        speak(self.npc_sheet, self.common)
        speaks = {g.group_id: g.speaks for g in build_gm_standoff_view(self.encounter).groups}
        self.assertEqual(speaks[self.company.pk], [self.common.name])
        self.assertEqual(speaks[self.named.pk], [self.common.name])


class PersonaDriveStrengthTests(TestCase):
    def test_persona_drives_pull_at_the_documented_strength(self) -> None:
        self.assertEqual(PERSONA_DRIVE_STRENGTH, DriveStrength.MAJOR)


class CreatureLanguageSentinelTests(TestCase):
    """The Required content dashboard lists standoff creatures with no language (#4373)."""

    def test_nothing_is_missing_until_an_approach_is_verbal(self) -> None:
        from web.admin.tuning.required_content import _probe_standoff_creature_languages

        CreatureTemplateFactory(name="Sentinel mute (test)", cause=CauseKind.ORDERS)
        self.assertTrue(_probe_standoff_creature_languages().present)
        StandoffApproachFactory(is_verbal=True)
        result = _probe_standoff_creature_languages()
        self.assertFalse(result.present)
        self.assertIn("Sentinel mute (test)", result.missing)
