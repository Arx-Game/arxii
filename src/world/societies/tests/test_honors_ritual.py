"""The Rite of Honors ritual row + dispatch (#3466 Task 8).

Covers: the seeded ``Ritual`` row (idempotent, ``CONTENT_MODELS``-safe),
``PerformRitualAction`` dispatching a real ``honor_deed`` call end to end, a
refusal surfacing as a failure ``ActionResult`` rather than an unhandled
exception (the ``HonorRefused`` catch added to
``actions/definitions/ritual.py`` alongside this), and the telnet grammar
(``commands.ritual.CmdRitual._resolve_honors_args``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from actions.definitions.ritual import PerformRitualAction
from commands.exceptions import CommandError
from commands.ritual import CmdRitual
from world.character_creation.constants import SHROUDWATCH_ACADEMY_NAME
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import mint_favor_token
from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.models import Ritual
from world.scenes.factories import SceneFactory
from world.societies.constants import DeedKnowledgeSource
from world.societies.factories import (
    LegendEntryFactory,
    LegendEventFactory,
    LegendLevelCalibrationFactory,
    OrganizationFactory,
)
from world.societies.honors import HONORS_SERVICE_PATH
from world.societies.knowledge_services import grant_deed_knowledge
from world.societies.models import LegendHonor
from world.societies.seeds import RITE_OF_HONORS_NAME, ensure_rite_of_honors_ritual


def _sheet_with_persona():
    """A fresh CharacterSheet plus its auto-created PRIMARY persona."""
    sheet = CharacterSheetFactory()
    return sheet, sheet.primary_persona


@override_settings(SEED_SAMPLE_CONTENT=True)
class EnsureRiteOfHonorsRitualTests(TestCase):
    """The seeder: idempotent, correct dispatch shape, hedge-accessible."""

    def test_seed_creates_expected_row(self) -> None:
        rite = ensure_rite_of_honors_ritual()
        assert rite is not None
        assert rite.name == RITE_OF_HONORS_NAME
        assert rite.execution_kind == RitualExecutionKind.SERVICE
        assert rite.service_function_path == HONORS_SERVICE_PATH
        assert rite.participation_rule == ParticipationRule.SINGLE_ACTOR
        # #3001: no Gifted-check anywhere in this rite's framework — it must
        # stay visible to a character with no magical profile at all.
        assert rite.hedge_accessible is True

    def test_seed_is_idempotent(self) -> None:
        first = ensure_rite_of_honors_ritual()
        second = ensure_rite_of_honors_ritual()
        assert first.pk == second.pk
        assert Ritual.objects.filter(name=RITE_OF_HONORS_NAME).count() == 1


class EnsureRiteOfHonorsRitualWithoutSampleContentTests(TestCase):
    """No ``SEED_SAMPLE_CONTENT`` here deliberately (real production default).

    ``magic.ritual`` is a ``CONTENT_MODELS`` entry, so an unauthored row must
    never be invented outside the sample-content escape hatch (#2698) — this
    is what keeps ``world.seeds.tests.test_no_content_slop`` green for this
    seeder, mirroring ``seed_canonical_rituals``'s own siblings.
    """

    def test_no_row_authored_without_sample_content(self) -> None:
        result = ensure_rite_of_honors_ritual()
        assert result is None
        assert not Ritual.objects.filter(name=RITE_OF_HONORS_NAME).exists()


@override_settings(SEED_SAMPLE_CONTENT=True)
class PerformRiteOfHonorsDispatchTests(TestCase):
    """``PerformRitualAction`` dispatching the seeded ritual to ``honor_deed``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rite = ensure_rite_of_honors_ritual()
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def setUp(self) -> None:
        self.honorer_sheet, self.honorer_persona = _sheet_with_persona()
        self.honoree_sheet, self.honoree_persona = _sheet_with_persona()
        self.scene = SceneFactory()
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        mint_favor_token(self.academy, self.honorer_sheet, provenance_note="A deed done")

    def test_perform_ritual_action_creates_one_legend_honor(self) -> None:
        actor = self.honorer_sheet.character
        result = PerformRitualAction().run(
            actor,
            ritual=self.rite,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="A Great Deed",
            journal_body="They fought bravely and won.",
        )
        assert result.success
        assert LegendHonor.objects.count() == 1
        honor = LegendHonor.objects.get()
        assert honor.deed_id == self.deed.pk
        assert honor.honorer_id == self.honorer_persona.pk

    def test_refusal_surfaces_as_failure_action_result_not_a_crash(self) -> None:
        """A ``HonorRefused`` (e.g. honoring the same deed twice) must not propagate.

        Proves the ``HonorRefused`` addition to ``actions/definitions/ritual.py``'s
        caught-exception tuple — without it this raises out of ``dispatch_ritual``
        uncaught, instead of the uniform user-safe failure every other ritual
        refusal gets.
        """
        actor = self.honorer_sheet.character
        first = PerformRitualAction().run(
            actor,
            ritual=self.rite,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="A Great Deed",
            journal_body="They fought bravely and won.",
        )
        assert first.success

        second = PerformRitualAction().run(
            actor,
            ritual=self.rite,
            honoree_persona=self.honoree_persona,
            deed=self.deed,
            journal_title="A Great Deed, Again",
            journal_body="Retelling it.",
        )
        assert not second.success
        assert "already honored" in second.message.lower()
        # The refusal must not have minted a second LegendHonor.
        assert LegendHonor.objects.count() == 1


def _make_cmd(caller: object, args: str) -> CmdRitual:
    cmd = CmdRitual()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"ritual {args}"
    return cmd


@override_settings(SEED_SAMPLE_CONTENT=True)
class RiteOfHonorsTelnetGrammarTests(TestCase):
    """``ritual Rite of Honors honoree=<name> deed=<id> title=<text> body=<text>``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.rite = ensure_rite_of_honors_ritual()
        cls.academy = OrganizationFactory(name=SHROUDWATCH_ACADEMY_NAME)
        cls.calibration = LegendLevelCalibrationFactory(
            level=0, honor_hares_required=1, honor_value_added=10, deed_title_threshold=100
        )

    def setUp(self) -> None:
        self.honorer_sheet, self.honorer_persona = _sheet_with_persona()
        self.honoree_sheet, self.honoree_persona = _sheet_with_persona()
        self.scene = SceneFactory()
        self.event = LegendEventFactory(base_value=100, scene=self.scene)
        self.deed = LegendEntryFactory(
            persona=self.honoree_persona, event=self.event, base_value=20, earned_at_level=0
        )
        grant_deed_knowledge(
            deed=self.deed, personas=[self.honorer_persona], source=DeedKnowledgeSource.WITNESSED
        )
        mint_favor_token(self.academy, self.honorer_sheet, provenance_note="A deed done")
        self.character = self.honorer_sheet.character
        self.character.msg = MagicMock()

    def test_resolves_honoree_and_deed_from_flat_tokens(self) -> None:
        args = (
            f"Rite of Honors honoree={self.honoree_persona.name} deed={self.deed.pk} "
            "title=A Great Deed body=They fought bravely and won"
        )
        cmd = _make_cmd(self.character, args)
        kwargs = cmd.resolve_action_args()
        assert kwargs["ritual"] == self.rite
        assert kwargs["honoree_persona"] == self.honoree_persona
        assert kwargs["deed"] == self.deed
        assert kwargs["journal_title"] == "A Great Deed"
        assert kwargs["journal_body"] == "They fought bravely and won"

    def test_end_to_end_via_func_creates_legend_honor(self) -> None:
        args = (
            f"Rite of Honors honoree={self.honoree_persona.name} deed={self.deed.pk} "
            "title=A Great Deed body=They fought bravely and won"
        )
        cmd = _make_cmd(self.character, args)
        cmd.func()
        assert LegendHonor.objects.count() == 1

    def test_unknown_honoree_name_raises_command_error(self) -> None:
        args = f"Rite of Honors honoree=NoSuchPersonAtAll deed={self.deed.pk} title=T body=B"
        cmd = _make_cmd(self.character, args)
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_non_numeric_deed_raises_command_error(self) -> None:
        args = f"Rite of Honors honoree={self.honoree_persona.name} deed=notanumber title=T body=B"
        cmd = _make_cmd(self.character, args)
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_missing_body_raises_usage_error(self) -> None:
        args = f"Rite of Honors honoree={self.honoree_persona.name} deed={self.deed.pk} title=T"
        cmd = _make_cmd(self.character, args)
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()
