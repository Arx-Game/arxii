"""#3554: authored outcome lines on Technique and ThreatPoolEntry validate their placeholders."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.combat.factories import ThreatPoolEntryFactory, ThreatPoolFactory
from world.magic.factories import TechniqueFactory


class OutcomeNarrationFieldValidationTest(TestCase):
    def test_technique_rejects_line_without_target(self) -> None:
        technique = TechniqueFactory(hit_narration="{actor} swings wide")
        with self.assertRaises(ValidationError) as ctx:
            technique.clean()
        assert "hit_narration" in ctx.exception.message_dict

    def test_technique_accepts_both_placeholders_and_blank(self) -> None:
        technique = TechniqueFactory(
            hit_narration="{actor} hurls a spear of rime at {target}", miss_narration=""
        )
        technique.clean()

    def test_threat_entry_rejects_line_without_actor(self) -> None:
        entry = ThreatPoolEntryFactory(
            pool=ThreatPoolFactory(), miss_narration="claws rake {target}"
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.clean()
        assert "miss_narration" in ctx.exception.message_dict

    def test_threat_entry_accepts_both_placeholders(self) -> None:
        entry = ThreatPoolEntryFactory(
            pool=ThreatPoolFactory(), hit_narration="{actor} rakes {target} with its claws"
        )
        entry.clean()
