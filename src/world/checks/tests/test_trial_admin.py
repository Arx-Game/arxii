"""The Consequence page enforces the trial rules on a whole submitted set (#4501).

The inline formset runs ``Consequence.trial_rule_errors`` over every effect row in the
submission, so a technique-opening effect and its cost can arrive in one save, and a
cost-free one is refused with the message on the page.
"""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceFactory
from world.checks.models import ConsequenceEffect
from world.codex.factories import CodexEntryFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.factories import TechniqueFactory
from world.progression.factories import CodexKnowledgeRequirementFactory
from world.traits.factories import CheckOutcomeFactory


class ConsequencePageTrialRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountDB.objects.create_superuser("trialstaff", "ts@example.com", "pw-123456")
        cls.success = CheckOutcomeFactory(name="Win", success_level=1)
        cls.entry = CodexEntryFactory(name="Gating entry")
        CodexKnowledgeRequirementFactory(
            codex_entry=cls.entry, path=None, technique=TechniqueFactory()
        )
        cls.condition = ConditionTemplateFactory(name="Chill")
        cls.consequence = ConsequenceFactory(outcome_tier=cls.success, label="Crypt, Success")

    def _post(self, rows: list[dict[str, str]], **parent: str):
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_consequence_change", args=[self.consequence.pk])
        data = {
            "outcome_tier": str(self.success.pk),
            "label": self.consequence.label,
            "mechanical_description": "",
            "weight": "1",
            "effects-TOTAL_FORMS": str(len(rows)),
            "effects-INITIAL_FORMS": "0",
            "effects-MIN_NUM_FORMS": "0",
            "effects-MAX_NUM_FORMS": "1000",
            **parent,
        }
        for index, row in enumerate(rows):
            data[f"effects-{index}-consequence"] = str(self.consequence.pk)
            data[f"effects-{index}-target"] = EffectTarget.SELF
            for key, value in row.items():
                data[f"effects-{index}-{key}"] = value
        return self.client.post(url, data)

    def _known(self) -> dict[str, str]:
        return {
            "effect_type": EffectType.GRANT_CODEX,
            "execution_order": "0",
            "codex_entry": str(self.entry.pk),
            "grants_known": "on",
        }

    def _scar(self) -> dict[str, str]:
        return {
            "effect_type": EffectType.MAGICAL_SCARS,
            "execution_order": "1",
            "condition_template": str(self.condition.pk),
            "condition_severity": "2",
        }

    def test_a_known_grant_with_no_cost_is_refused_on_the_page(self) -> None:
        response = self._post([self._known()])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "opens or trains a technique and has no cost")
        self.assertFalse(ConsequenceEffect.objects.filter(consequence=self.consequence))

    def test_the_grant_and_its_cost_save_together(self) -> None:
        response = self._post([self._known(), self._scar()])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(
                ConsequenceEffect.objects.filter(consequence=self.consequence).values_list(
                    "effect_type", flat=True
                )
            ),
            [EffectType.GRANT_CODEX, EffectType.MAGICAL_SCARS],
        )

    def test_a_deliberately_free_grant_needs_its_reason(self) -> None:
        response = self._post([self._known()], deliberately_free="on", free_reason="")
        self.assertContains(response, "Say why this is deliberately free of cost.")
        response = self._post(
            [self._known()], deliberately_free="on", free_reason="[staff-authored reason]"
        )
        self.assertEqual(response.status_code, 302)
