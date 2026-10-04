"""The per-viewer standoff payload: what each participant may see, and nothing more."""

from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import (
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.combat.tests.test_views import CombatEncounterViewSetTestBase
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import ApplicationFactory
from world.species.factories import SpeciesFactory
from world.standoffs.constants import DriveStrength, RevealKind
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffApproachFactory,
    StandoffGroupFactory,
    StandoffRevealFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import (
    StandoffApproach,
    StandoffConfig,
    StandoffGroup,
    StandoffSparkShare,
    StandoffTerms,
)
from world.standoffs.services.describe import HIDDEN_REGARD_LINE
from world.standoffs.services.state import open_standoff
from world.standoffs.services.view import build_standoff_view
from world.standoffs.tests.test_verbs import VerbBase

CHART = "world.mechanics.services.chart_has_success_outcomes"
PREVIEW = "world.standoffs.services.view.preview_check_difficulty"


class ViewBase(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.species = SpeciesFactory()
        self.sheet_a = CharacterSheetFactory(character=CharacterFactory(), species=self.species)
        self.sheet_b = CharacterSheetFactory(character=CharacterFactory(), species=SpeciesFactory())
        self.part_a = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet_a
        )
        self.part_b = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet_b
        )
        self.rule = RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": self.species.pk}},
            spark_text="PLACEHOLDER spark A",
            revealed_text="PLACEHOLDER detail A",
        )

    def view_for(self, sheet):
        return build_standoff_view(self.encounter, sheet)


class SparkPrivacyTests(ViewBase):
    def test_own_spark_shown_to_its_owner_only(self) -> None:
        view_a = self.view_for(self.sheet_a)
        view_b = self.view_for(self.sheet_b)
        self.assertEqual([s.text for s in view_a.sparks], ["PLACEHOLDER spark A"])
        self.assertFalse(view_a.sparks[0].shared)
        self.assertEqual(view_b.sparks, [])
        self.assertEqual(view_b.shared_sparks, [])

    def test_shared_spark_reaches_the_other_participant_as_spark_text_only(self) -> None:
        StandoffSparkShare.objects.create(
            group=self.group, character_sheet=self.sheet_a, regard_rule=self.rule
        )
        view_a = self.view_for(self.sheet_a)
        view_b = self.view_for(self.sheet_b)
        self.assertTrue(view_a.sparks[0].shared)
        self.assertEqual(view_a.shared_sparks, [])
        self.assertEqual([s.text for s in view_b.shared_sparks], ["PLACEHOLDER spark A"])
        self.assertNotIn("detail", repr(view_b))

    def test_none_after_the_fight_starts(self) -> None:
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["round_number"])
        self.assertIsNone(self.view_for(self.sheet_a))


class HiddenInformationTests(ViewBase):
    def setUp(self) -> None:
        super().setUp()
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        self.drive = CreatureDriveFactory(
            creature_template=self.template, strength=DriveStrength.MAJOR
        )

    def test_unrevealed_things_count_but_are_never_named(self) -> None:
        group = self.view_for(self.sheet_a).groups[0]
        self.assertIsNone(group.cause)
        self.assertEqual(group.drives, [])
        self.assertEqual(group.revealed_regard, [])
        # cause + drive + A's matching regard rule
        self.assertEqual(group.hidden_count, 3)
        # relevant to the party, so B's count includes A's rule but never names it
        self.assertEqual(self.view_for(self.sheet_b).groups[0].hidden_count, 3)

    def test_revealed_cause_and_drive_are_named(self) -> None:
        StandoffRevealFactory(group=self.group, kind=RevealKind.CAUSE)
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=self.drive)
        group = self.view_for(self.sheet_b).groups[0]
        self.assertEqual(group.cause, "Predation")
        self.assertEqual(
            [(d.label, d.strength) for d in group.drives], [(self.drive.property.name, "Major")]
        )
        self.assertEqual(group.hidden_count, 1)  # A's unread regard rule

    def test_regard_detail_goes_to_the_matched_viewer_until_shared(self) -> None:
        StandoffRevealFactory(group=self.group, kind=RevealKind.REGARD, regard_rule=self.rule)
        self.assertEqual(
            self.view_for(self.sheet_a).groups[0].revealed_regard, ["PLACEHOLDER detail A"]
        )
        self.assertEqual(
            self.view_for(self.sheet_b).groups[0].revealed_regard, [HIDDEN_REGARD_LINE]
        )
        StandoffSparkShare.objects.create(
            group=self.group, character_sheet=self.sheet_a, regard_rule=self.rule
        )
        self.assertEqual(
            self.view_for(self.sheet_b).groups[0].revealed_regard, ["PLACEHOLDER detail A"]
        )

    def test_hidden_drive_is_never_named_in_levers_but_still_counts_in_the_grade(self) -> None:
        approach = StandoffApproachFactory()
        ApplicationFactory(capability=approach.capability, target_property=self.drive.property)
        with patch(PREVIEW, return_value=0) as preview:
            hidden = self.view_for(self.sheet_b).approaches[0]
            self.assertEqual(hidden.levers, [])
            self.assertTrue(preview.called)
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=self.drive)
        with patch(PREVIEW, return_value=0):
            revealed = self.view_for(self.sheet_b).approaches[0]
        self.assertEqual(revealed.levers, [self.drive.property.name])


class LeverLeakTests(ViewBase):
    def test_a_shared_spark_without_a_read_does_not_expose_detail_in_levers(self) -> None:
        self.rule.difficulty_shift_bands = 1
        self.rule.save(update_fields=["difficulty_shift_bands"])
        StandoffApproachFactory()
        # What a press does after it shifts: share the spark. No REGARD reveal exists.
        StandoffSparkShare.objects.create(
            group=self.group, character_sheet=self.sheet_a, regard_rule=self.rule
        )
        with patch(PREVIEW, return_value=0):
            before = self.view_for(self.sheet_a).approaches[0].levers
        self.assertNotIn("PLACEHOLDER detail A", before)
        StandoffRevealFactory(group=self.group, kind=RevealKind.REGARD, regard_rule=self.rule)
        with patch(PREVIEW, return_value=0):
            after = self.view_for(self.sheet_a).approaches[0].levers
        self.assertIn("PLACEHOLDER detail A", after)


class QueryBoundTests(ViewBase):
    """Queries follow the number of groups, never the number of approaches or terms."""

    def setUp(self) -> None:
        super().setUp()
        self.check_type = CheckTypeFactory()
        template2 = CreatureTemplateFactory(tier=OpponentTier.MOOK, cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=template2, level=2)
        StandoffGroupFactory(encounter=self.encounter, creature_template=template2)
        self.config.terms_check_type = self.check_type
        self.config.save()
        for _ in range(2):
            StandoffApproachFactory(check_type=self.check_type)
            StandoffTermsFactory()

    def _count(self) -> int:
        self.view_for(self.sheet_a)  # warm caches
        with CaptureQueriesContext(connection) as ctx:
            view = self.view_for(self.sheet_a)
        self.assertEqual(len(view.approaches), 2 * StandoffApproach.objects.count())
        self.assertEqual(len(view.terms), 2 * StandoffTerms.objects.count())
        return len(ctx)

    def test_more_approaches_and_terms_add_no_queries(self) -> None:
        self.assertEqual(StandoffGroup.objects.filter(encounter=self.encounter).count(), 2)
        base = self._count()
        StandoffApproachFactory(check_type=self.check_type)
        StandoffTermsFactory()
        self.assertEqual(self._count(), base)


class GradeAndTermsTests(ViewBase):
    def test_grade_uses_the_roll_modifiers_and_the_shared_banding(self) -> None:
        approach = StandoffApproachFactory()
        with (
            patch(PREVIEW, return_value=4) as preview,
            patch(CHART, return_value=True),
            patch(
                "world.standoffs.services.view.collect_check_modifiers",
                return_value=SimpleNamespace(total=7),
            ),
        ):
            view = self.view_for(self.sheet_b)
        self.assertEqual(view.approaches[0].grade, DifficultyIndicator.EASY.value)
        self.assertEqual(preview.call_args.args[3], 7)  # the roll's own modifier total
        self.assertEqual(view.approaches[0].approach_id, approach.pk)

    def test_terms_listed_only_when_their_required_drive_is_revealed(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template)
        open_terms = StandoffTermsFactory()
        gated = StandoffTermsFactory(required_drive=drive.property)
        with patch(PREVIEW, return_value=0):
            names = [t.name for t in self.view_for(self.sheet_b).terms]
            self.assertEqual(names, [open_terms.name])
            StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=drive)
            names = [t.name for t in self.view_for(self.sheet_b).terms]
        self.assertEqual(set(names), {open_terms.name, gated.name})

    def test_owner_options_is_empty(self) -> None:
        self.assertEqual(self.view_for(self.sheet_a).owner_options, [])


class EncounterApiTests(CombatEncounterViewSetTestBase):
    def setUp(self) -> None:
        seed_scaling_defaults()
        self.template = CreatureTemplateFactory(tier=OpponentTier.MOOK, cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=self.template, level=2)
        StandoffConfig.load()
        open_standoff(self.encounter)

    def _get(self, account):
        client = APIClient()
        client.force_authenticate(user=account)
        return client.get(f"/api/combat/{self.encounter.pk}/")

    def test_a_participant_gets_their_standoff_block(self) -> None:
        response = self._get(self.player_account)
        self.assertEqual(response.status_code, 200)
        standoff = response.data["standoff"]
        self.assertEqual(len(standoff["groups"]), 1)
        self.assertEqual(standoff["owner_options"], [])

    def test_a_non_participant_gets_none(self) -> None:
        self.assertIsNone(self._get(self.gm_account).data["standoff"])

    def test_none_once_the_fight_has_started(self) -> None:
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["round_number"])
        self.assertIsNone(self._get(self.player_account).data["standoff"])
