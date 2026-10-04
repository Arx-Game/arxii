"""What a read may tell its reader: regard detail only when it applies or was shared."""

from world.standoffs.constants import RevealKind
from world.standoffs.factories import RegardRuleFactory, StandoffRevealFactory
from world.standoffs.models import StandoffSparkShare
from world.standoffs.services.describe import HIDDEN_REGARD_LINE, describe_reveals
from world.standoffs.tests.test_verbs import VerbBase

NOT_ME = {"leaf": "has_species", "params": {"species_id": 999999}}


class DescribeRevealsTests(VerbBase):
    def _lines(self, rule) -> list[str]:
        reveal = StandoffRevealFactory(group=self.group, kind=RevealKind.REGARD, regard_rule=rule)
        return describe_reveals(self.group, [reveal], self.participant.character_sheet)

    def test_a_rule_that_matches_the_reader_gives_its_detail(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template, rule={}, revealed_text="PLACEHOLDER detail"
        )
        self.assertEqual(self._lines(rule), ["PLACEHOLDER detail"])

    def test_a_rule_about_someone_else_gives_no_detail(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template, rule=NOT_ME, revealed_text="PLACEHOLDER detail"
        )
        self.assertEqual(self._lines(rule), [HIDDEN_REGARD_LINE])

    def test_a_shared_spark_opens_the_detail(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template, rule=NOT_ME, revealed_text="PLACEHOLDER detail"
        )
        StandoffSparkShare.objects.create(
            group=self.group, character_sheet=self.participant.character_sheet, regard_rule=rule
        )
        self.assertEqual(self._lines(rule), ["PLACEHOLDER detail"])
