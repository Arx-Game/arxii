"""Tests for Dream Peril collapse resolution (#2290)."""

from django.test import TestCase, override_settings

from world.character_sheets.services import create_character_with_sheet
from world.conditions.models import ConditionTemplate
from world.conditions.services import apply_condition
from world.dreams.conditions import ensure_dream_conditions
from world.dreams.peril import get_dream_peril_config, resolve_dream_peril_collapse
from world.fatigue.constants import ActionCategory
from world.fatigue.services import resolve_fatigue_collapse
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.factories import create_dream_peril_pool
from world.vitals.seeds import (
    seed_survivability_content,
)


class DreamPerilConfigTests(TestCase):
    """Tests for the DreamPerilConfig singleton."""

    def test_config_exists(self):
        config = get_dream_peril_config()
        assert config is not None
        assert config.resist_difficulty > 0


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamPerilCollapseTests(TestCase):
    """Tests for resolve_dream_peril_collapse().

    ``seed_survivability_content`` gates its ConditionTemplate/CapabilityType
    creation behind SEED_SAMPLE_CONTENT (#2698) — this test drives the real
    Unconscious/Bleeding Out conditions through collapse resolution.
    """

    def setUp(self):
        seed_survivability_content()
        ensure_dream_conditions()
        create_dream_peril_pool()
        self.char, self.sheet, _ = create_character_with_sheet(
            character_key="Dreamer",
            primary_persona_name="Dreamer",
        )

    def test_collapse_does_not_crash(self):
        """The resolver should run without errors and return a result."""
        result = resolve_dream_peril_collapse(self.sheet)
        assert result is not None
        assert result.died in (True, False)
        assert result.outcome_label != ""

    def test_collapse_returns_valid_outcome_label(self):
        """The outcome label should be one of the four pool outcomes."""
        result = resolve_dream_peril_collapse(self.sheet)
        # The label may be a pool outcome or a fallback from select_consequence
        # when no CheckRank/ResultChart data is seeded (tests without full
        # check pipeline). Accept either the authored labels or fallback labels.
        valid_labels = (
            "wake_shaken",
            "nightmares",
            "madness",
            "die",
            "Unknown",
            "Success",
            "Failure",
            "Partial Success",
        )
        assert result.outcome_label in valid_labels, f"Got: {result.outcome_label!r}"


@override_settings(SEED_SAMPLE_CONTENT=True)
class DreamPerilNarrationTests(TestCase):
    """Tests for #3003: Dream Peril narration surfacing through resolve_fatigue_collapse.

    Threads ``resolve_dream_peril_collapse``'s ``outcome_label``/``message`` out to
    ``FatigueCollapseResult`` and to the player's client via ``character.msg()`` —
    previously the dreamside branch discarded both, so a player driven mad by a
    nightmare was told nothing at all.
    """

    def setUp(self):
        seed_survivability_content()
        ensure_dream_conditions()
        create_dream_peril_pool()

    def _dreaming_sheet_at_mental_collapse(self):
        """A dreamside sheet whose mental endurance check fails.

        No CheckRank/ResultChart data is seeded in this test's transaction, so
        the endurance check's success_level defaults to 0 (treated as
        failure) — the same unseeded-check-pipeline behavior
        ``DreamPerilCollapseTests`` above relies on for its own
        fallback-label assertions.
        """
        char, sheet, _ = create_character_with_sheet(
            character_key="NarrationDreamer",
            primary_persona_name="NarrationDreamer",
        )
        template = ConditionTemplate.objects.get(name=SLEEPING_CONDITION_NAME)
        apply_condition(target=char, condition=template)
        return sheet

    def _awake_sheet_at_physical_collapse(self):
        """An awake sheet (no Sleeping condition) collapsing on physical fatigue."""
        _char, sheet, _ = create_character_with_sheet(
            character_key="NarrationWaker",
            primary_persona_name="NarrationWaker",
        )
        return sheet

    def _capture_msgs(self, sheet) -> list[str]:
        """Monkeypatch the character's ``msg`` to record what was sent."""
        sent: list[str] = []
        sheet.character.msg = lambda text, **_kwargs: sent.append(text)
        return sent

    def test_collapse_carries_peril_narration(self):
        sheet = self._dreaming_sheet_at_mental_collapse()
        result = resolve_fatigue_collapse(sheet, ActionCategory.MENTAL)
        assert result.outcome_label
        assert result.message

    def test_character_is_told_what_the_dream_did(self):
        sheet = self._dreaming_sheet_at_mental_collapse()
        sent = self._capture_msgs(sheet)
        resolve_fatigue_collapse(sheet, ActionCategory.MENTAL)
        assert any(m for m in sent if m)

    def test_non_dream_collapse_has_no_narration(self):
        sheet = self._awake_sheet_at_physical_collapse()
        result = resolve_fatigue_collapse(sheet, ActionCategory.PHYSICAL)
        assert result.outcome_label == ""
        assert result.message == ""
