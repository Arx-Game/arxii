"""StakeRewardLine ITEM/CLUE/CODEX sinks: FK shape, clean() rules, PROTECT (#3566)."""

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
from world.codex.factories import CodexEntryFactory
from world.items.factories import ItemTemplateFactory
from world.stories.constants import StakeResolutionColumn, StakeRewardSink
from world.stories.factories import StakeResolutionFactory, StakeRewardLineFactory
from world.stories.models import StakeRewardLine


class RewardLineShapeTests(TestCase):
    def setUp(self) -> None:
        self.resolution = StakeResolutionFactory(column=StakeResolutionColumn.WIN)
        self.template = ItemTemplateFactory(name="Signet of the Baron", value=250)
        self.clue = ClueFactory()  # CODEX target by default
        self.entry = CodexEntryFactory()

    def test_item_line_requires_the_template_and_pins_amount(self) -> None:
        line = StakeRewardLine(
            resolution=self.resolution,
            sink=StakeRewardSink.ITEM,
            amount=250,
            item_template=self.template,
        )
        line.full_clean()

        with self.assertRaises(ValidationError) as ctx:
            StakeRewardLine(
                resolution=self.resolution, sink=StakeRewardSink.ITEM, amount=250
            ).full_clean()
        self.assertIn("item_template", ctx.exception.message_dict)

        with self.assertRaises(ValidationError) as ctx:
            StakeRewardLine(
                resolution=self.resolution,
                sink=StakeRewardSink.ITEM,
                amount=10,
                item_template=self.template,
            ).full_clean()
        self.assertIn("amount", ctx.exception.message_dict)

    def test_clue_line_requires_a_resolvable_target_kind(self) -> None:
        StakeRewardLine(
            resolution=self.resolution, sink=StakeRewardSink.CLUE, amount=50, clue=self.clue
        ).full_clean()

        item_clue = ClueFactory(
            target_kind=ClueTargetKind.ITEM,
            target_codex_entry=None,
            target_item_template=self.template,
        )
        with self.assertRaises(ValidationError) as ctx:
            StakeRewardLine(
                resolution=self.resolution,
                sink=StakeRewardSink.CLUE,
                amount=50,
                clue=item_clue,
            ).full_clean()
        self.assertIn("clue", ctx.exception.message_dict)

    def test_codex_line_requires_the_entry(self) -> None:
        StakeRewardLine(
            resolution=self.resolution,
            sink=StakeRewardSink.CODEX,
            amount=40,
            codex_entry=self.entry,
        ).full_clean()

        with self.assertRaises(ValidationError):
            StakeRewardLine(
                resolution=self.resolution, sink=StakeRewardSink.CODEX, amount=40
            ).full_clean()

    def test_foreign_fk_on_the_wrong_sink_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            StakeRewardLine(
                resolution=self.resolution,
                sink=StakeRewardSink.MONEY,
                amount=10,
                clue=self.clue,
            ).full_clean()
        self.assertIn("clue", ctx.exception.message_dict)

    def test_protect_blocks_deleting_a_referenced_template(self) -> None:
        StakeRewardLineFactory(
            resolution=self.resolution,
            sink=StakeRewardSink.ITEM,
            amount=250,
            item_template=self.template,
        )
        with self.assertRaises(ProtectedError):
            self.template.delete()
