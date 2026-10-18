"""The NPC resist-check required-content sentinel (#4418).

A social single-target template needs a resist check (the flipped roll when an NPC acts)
and a consent category (an untagged template could slip romance through as resist-only).
"""

from __future__ import annotations

from django.test import TestCase

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from web.admin.tuning import required_content as rc
from world.checks.factories import CheckTypeFactory
from world.consent.factories import make_general_category


def _probe_for(key: str) -> rc.ContentProbe:
    """The shipped declaration's own probe, never a hand-copied duplicate."""
    return next(dep.probe for dep in rc._declarations() if dep.key == key)


class NpcResistCheckProbeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ActionTemplateFactory(
            name="Deceive",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
        )

    def _resolve(self) -> rc.ProbeResult:
        return _probe_for("npc-resist-checks").resolve(None)

    def test_template_without_resist_is_reported(self) -> None:
        result = self._resolve()
        self.assertFalse(result.present)
        self.assertIn("Deceive", result.missing)

    def test_authored_resist_closes_the_gap(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.consent_category = make_general_category()
        self.template.save()
        self.assertTrue(self._resolve().present)

    def test_resist_without_consent_category_is_still_reported(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.save()
        self.assertIn("Deceive", self._resolve().missing)
