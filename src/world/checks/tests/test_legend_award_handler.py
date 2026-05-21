"""Tests for the _legend_award effect handler."""

from unittest.mock import MagicMock

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.covenants.factories import make_engaged_member
from world.mechanics.effect_handlers import apply_all_effects, apply_effect
from world.scenes.factories import PersonaFactory
from world.societies.exceptions import LegendAwardParticipantMissingError
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import CovenantLegendCredit, LegendEntry, LegendEvent


def _make_legend_effect(consequence, source_type, *, template=""):
    """Helper: create a saved LEGEND_AWARD ConsequenceEffect."""
    return ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=source_type,
        legend_description_template=template,
    )


class LegendAwardHandlerCreateEventTests(TestCase):
    """Handler creates LegendEvent + LegendEntry rows for each participant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="HandlerTestChar")
        cls.source_type = LegendSourceTypeFactory()
        cls.persona_a = PersonaFactory()
        cls.persona_b = PersonaFactory()

    def _make_context(self, participants=None, beat=None, scene=None, story=None):
        return ResolutionContext(
            character=self.character,
            participants=participants,
            beat=beat,
            scene=scene,
            story=story,
        )

    def test_creates_legend_event_and_entries(self) -> None:
        """Handler creates 1 LegendEvent and 1 LegendEntry per participant."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type, template="The battle was won.")
        context = self._make_context(participants=[self.persona_a, self.persona_b])

        result = apply_effect(effect, context)

        assert result.applied is True
        assert result.effect_type == EffectType.LEGEND_AWARD
        assert isinstance(result.created_instance, LegendEvent)

        event = result.created_instance
        assert event.base_value == 10
        assert event.source_type == self.source_type
        assert LegendEntry.objects.filter(event=event).count() == 2

    def test_applied_effect_description_contains_participant_count(self) -> None:
        """Applied description mentions participant count."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type, template="Deed done.")
        context = self._make_context(participants=[self.persona_a])

        result = apply_effect(effect, context)

        assert "1 participant" in result.description

    def test_routes_via_apply_all_effects(self) -> None:
        """apply_all_effects routes LEGEND_AWARD through the handler."""
        consequence = ConsequenceFactory()
        _make_legend_effect(consequence, self.source_type, template="Deed via pool.")
        context = self._make_context(participants=[self.persona_a])

        results = apply_all_effects(consequence, context)

        assert len(results) == 1
        assert results[0].applied is True
        assert results[0].effect_type == EffectType.LEGEND_AWARD


class LegendAwardHandlerParticipantMissingTests(TestCase):
    """Handler raises LegendAwardParticipantMissingError when context.participants is absent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="MissingParticipantChar")
        cls.source_type = LegendSourceTypeFactory()

    def test_none_participants_raises_error(self) -> None:
        """context.participants=None raises LegendAwardParticipantMissingError."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type)
        context = ResolutionContext(character=self.character, participants=None)

        with self.assertRaises(LegendAwardParticipantMissingError):
            apply_effect(effect, context)

    def test_empty_participants_raises_error(self) -> None:
        """context.participants=[] raises LegendAwardParticipantMissingError."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type)
        context = ResolutionContext(character=self.character, participants=[])

        with self.assertRaises(LegendAwardParticipantMissingError):
            apply_effect(effect, context)


class LegendAwardDescriptionFallbackTests(TestCase):
    """Handler selects description via template → beat text → generic fallback chain."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = ObjectDB.objects.create(db_key="DescFallbackChar")
        cls.source_type = LegendSourceTypeFactory()
        cls.persona = PersonaFactory()

    def _make_context(self, beat=None):
        return ResolutionContext(
            character=self.character,
            participants=[self.persona],
            beat=beat,
        )

    def test_explicit_template_wins_over_beat(self) -> None:
        """Non-blank legend_description_template is used as description."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(
            consequence, self.source_type, template="She slew the dragon with one blow."
        )
        beat = MagicMock()
        beat.player_resolution_text = "different text"
        context = self._make_context(beat=beat)

        apply_effect(effect, context)

        event = LegendEvent.objects.order_by("-pk").first()
        assert event is not None
        assert "She slew the dragon with one blow." in event.description

    def test_description_falls_back_to_beat_player_resolution_text(self) -> None:
        """Blank template → use beat.player_resolution_text."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type, template="")
        beat = MagicMock()
        beat.player_resolution_text = "The hero strikes down the dragon."
        context = self._make_context(beat=beat)

        apply_effect(effect, context)

        event = LegendEvent.objects.order_by("-pk").first()
        assert event is not None
        assert "The hero strikes down the dragon." in event.description

    def test_description_falls_back_to_generic_when_no_beat(self) -> None:
        """Blank template AND beat=None → description = 'Legendary deed'."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type, template="")
        context = self._make_context(beat=None)

        apply_effect(effect, context)

        event = LegendEvent.objects.order_by("-pk").first()
        assert event is not None
        assert "Legendary deed" in event.description

    def test_beat_with_blank_resolution_text_falls_back_to_generic(self) -> None:
        """beat present but player_resolution_text is blank → 'Legendary deed'."""
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, self.source_type, template="")
        beat = MagicMock()
        beat.player_resolution_text = ""
        context = self._make_context(beat=beat)

        apply_effect(effect, context)

        event = LegendEvent.objects.order_by("-pk").first()
        assert event is not None
        assert "Legendary deed" in event.description


@tag("postgres")
class LegendAwardHandlerCovenantFanOutTests(TestCase):
    """Covenant fan-out: create_legend_event credits engaged covenant memberships.

    PG-only: queries ``societies_covenantlegendsummary`` (a materialized view).
    On the SQLite inner-loop tier the view doesn't exist; this class is skipped.
    """

    def test_covenant_credit_fans_out_for_engaged_member(self) -> None:
        """A persona with an engaged covenant membership gets a CovenantLegendCredit row."""
        # make_engaged_member creates CharacterSheet + Covenant + engaged CCR in one call.
        membership = make_engaged_member()
        sheet = membership.character_sheet
        # PersonaFactory defaults to ESTABLISHED, which is valid for legend.
        persona = PersonaFactory(character_sheet=sheet)

        character = ObjectDB.objects.create(db_key="FanOutChar")
        source_type = LegendSourceTypeFactory()
        consequence = ConsequenceFactory()
        effect = _make_legend_effect(consequence, source_type, template="Fan-out deed.")
        context = ResolutionContext(
            character=character,
            participants=[persona],
        )

        apply_effect(effect, context)

        # The LegendEntry for this persona should have a credit for the engaged covenant.
        entry = LegendEntry.objects.filter(persona=persona).first()
        assert entry is not None, "LegendEntry was not created for the participant"
        credit_count = CovenantLegendCredit.objects.filter(
            entry=entry, covenant=membership.covenant
        ).count()
        assert credit_count == 1, (
            f"Expected 1 CovenantLegendCredit for the engaged covenant, got {credit_count}"
        )
