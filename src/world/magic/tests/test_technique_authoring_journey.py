"""End-to-end telnet journey test for the technique authoring workbench (#1496).

Drives a staff/GM caller through the full draft → set → payloads → price → author
workflow via CmdTechnique, asserting on the resulting Technique + child rows.

Scenarios covered
-----------------
Happy path
    draft → set all core fields → restrict add → grant add → damage add →
    condition add → price (assert breakdown with within-budget line) →
    author; asserts Technique + all payload child rows exist, draft gone.

Over-budget (price) path
    Shrink TechniqueTierBudget.power_budget to 1 for tier 1; assert that
    ``technique price`` reports "over budget".  Staff budget is advisory
    (StaffPolicy.enforced=False), so ``technique author`` still creates the
    Technique.  The test documents that advisory behaviour explicitly — the
    budget indicator is informational, not a hard block for staff.

Lock denial
    Assert CmdTechnique.locks declares ``perm(Builder)`` so the Evennia
    command-lock machinery gates the command at dispatch time (verified via
    the locks string rather than calling func() without the permission because
    the bare-func harness bypasses Evennia's lock check before func()).
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from django.test import TestCase

from commands.technique import CmdTechnique
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    RestrictionFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    Technique,
    TechniqueDraft,
    TechniqueTierBudget,
)
from world.magic.services.technique_builder import get_technique_budget_config


class TechniqueAuthoringJourneyTests(TestCase):
    """Full E2E journey through CmdTechnique — draft, set, payloads, price, author.

    One test class, three scenarios:
    1. Lock denial (perm check).
    2. Happy path (full authoring → Technique + child rows).
    3. Over-budget advisory (price shows "over budget"; author still creates for staff).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.restriction = RestrictionFactory(power_bonus=10)
        cls.capability = CapabilityTypeFactory()
        cls.damage_type = DamageTypeFactory()
        cls.condition_template = ConditionTemplateFactory()
        # Ensure TechniqueTierBudget for tier 1 exists with a permissive cap
        # so the happy-path design (intensity=2, control=2 → cost 4) clears it.
        TechniqueTierBudget.objects.get_or_create(
            tier=1,
            defaults={
                "power_budget": 100,
                "representative_level": 1,
                "label": "Tier 1",
            },
        )
        # Ensure the budget config singleton exists.
        get_technique_budget_config()

    def setUp(self) -> None:
        self.character = cast(Any, self.sheet.character)
        self.character.msg = MagicMock()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run(self, args: str) -> None:
        """Run a CmdTechnique subcommand using the test harness."""
        cmd = CmdTechnique()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"technique {args}"
        cmd.func()

    def _output(self) -> str:
        """Collect all messages emitted to the caller since the last reset."""
        return "\n".join(
            str(call.args[0]) for call in self.character.msg.call_args_list if call.args
        )

    # ------------------------------------------------------------------
    # Scenario 1: lock denial
    # ------------------------------------------------------------------

    def test_command_requires_builder_lock(self) -> None:
        """CmdTechnique declares perm(Builder), gating the command at dispatch."""
        assert "perm(Builder)" in CmdTechnique().locks

    # ------------------------------------------------------------------
    # Scenario 2: happy path — full authoring journey
    # ------------------------------------------------------------------

    def test_happy_path_creates_technique_with_all_payloads(self) -> None:
        """Full draft → set → payloads → price → author journey.

        Asserts:
        - One new Technique row with the expected name and tier.
        - Capability grant, damage profile, and applied-condition child rows
          matching what was added via the command.
        - Restriction transferred to the authored Technique.
        - Draft discarded on success.
        """
        # Step 1 — draft
        self._run("draft Ember Cascade")
        assert TechniqueDraft.objects.filter(character=self.sheet).exists(), (
            "draft subcommand must create a TechniqueDraft row."
        )
        output_after_draft = self._output()
        assert "Ember Cascade" in output_after_draft

        # Step 2 — set all core fields (use PKs to avoid multi-word name issues)
        self.character.msg.reset_mock()
        self._run(
            f"set gift={self.gift.pk}"
            f" style={self.style.pk}"
            f" effect_type={self.effect_type.pk}"
            f" action_category=physical"
            f" tier=1"
            f" intensity=2"
            f" control=2"
            f" anima_cost=3"
        )
        draft = TechniqueDraft.objects.get(character=self.sheet)
        assert draft.gift_id == self.gift.pk
        assert draft.style_id == self.style.pk
        assert draft.effect_type_id == self.effect_type.pk
        assert draft.action_category == "physical"
        assert draft.tier == 1
        assert draft.intensity == 2
        assert draft.control == 2
        assert draft.anima_cost == 3

        set_output = self._output()
        assert "updated" in set_output.lower() or "draft" in set_output.lower()

        # Step 3 — restrict add
        self._run(f"restrict add {self.restriction.pk}")
        draft.refresh_from_db()
        assert draft.restrictions.filter(pk=self.restriction.pk).exists(), (
            "Restriction must be attached to the draft after 'restrict add'."
        )

        # Step 4 — grant add
        self._run(f"grant add capability={self.capability.pk} base=5 mult=1.0")
        assert draft.capability_grants.count() == 1, (
            "One capability grant expected on draft after 'grant add'."
        )

        # Step 5 — damage add
        self._run(f"damage add type={self.damage_type.pk} base=8 mult=0.5")
        assert draft.damage_profiles.count() == 1, (
            "One damage profile expected on draft after 'damage add'."
        )

        # Step 6 — condition add (with duration)
        self._run(f"condition add template={self.condition_template.pk} severity=2 duration=3")
        assert draft.applied_conditions.count() == 1, (
            "One applied condition expected on draft after 'condition add'."
        )

        # Step 7 — price: assert breakdown shows within-budget
        self.character.msg.reset_mock()
        self._run("price")
        price_output = self._output()
        assert "Total:" in price_output or "total:" in price_output.lower(), (
            f"Expected 'Total:' in price output, got: {price_output!r}"
        )
        assert "budget" in price_output.lower(), (
            f"Expected 'budget' in price output, got: {price_output!r}"
        )
        assert "within budget" in price_output.lower(), (
            f"Expected 'within budget' in price output, got: {price_output!r}"
        )

        # Step 8 — author: assert Technique created + draft gone
        count_before = Technique.objects.count()
        self.character.msg.reset_mock()
        self._run("author")
        author_output = self._output()

        assert Technique.objects.count() == count_before + 1, (
            "author must create exactly one new Technique row."
        )
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists(), (
            "Draft must be discarded after a successful author."
        )

        # Success message includes the technique name.
        assert "Ember Cascade" in author_output, (
            f"Expected technique name in author output, got: {author_output!r}"
        )

        # --- assert the authored Technique has correct name and tier ---
        technique = Technique.objects.filter(name="Ember Cascade").order_by("-pk").first()
        assert technique is not None
        assert technique.name == "Ember Cascade"
        # representative_level for tier 1 is 1 → tier property returns 1.
        assert technique.tier == 1, (
            f"Expected Technique.tier == 1 (level 1), got {technique.tier!r}"
        )

        # --- assert capability grant child row ---
        assert technique.capability_grants.filter(
            capability=self.capability,
            base_value=5,
        ).exists(), "Authored Technique must carry the capability grant row added via 'grant add'."

        # --- assert damage profile child row ---
        assert technique.damage_profiles.filter(
            damage_type=self.damage_type,
            base_damage=8,
        ).exists(), "Authored Technique must carry the damage profile row added via 'damage add'."

        # --- assert applied-condition child row ---
        assert technique.condition_applications.filter(
            condition=self.condition_template,
            base_severity=2,
            base_duration_rounds=3,
        ).exists(), (
            "Authored Technique must carry the applied-condition row added via 'condition add'."
        )

        # --- assert restriction transferred ---
        assert technique.restrictions.filter(pk=self.restriction.pk).exists(), (
            "Restriction added via 'restrict add' must appear on the authored Technique."
        )

    # ------------------------------------------------------------------
    # Scenario 3: over-budget (advisory for staff)
    # ------------------------------------------------------------------

    def test_over_budget_price_shows_over_budget_advisory(self) -> None:
        """Staff budget is advisory: price shows 'over budget'; author still creates.

        Shrinks TechniqueTierBudget.power_budget to 1 for tier 1 so a design with
        intensity=5/control=5 (cost=10) clearly exceeds it.  Asserts:
        - 'technique price' output includes 'over budget'.
        - 'technique author' succeeds (StaffPolicy.enforced=False) — creates the
          Technique and discards the draft.

        This validates the advisory budget display and documents that the staff path
        is non-blocking: staff can author over-budget techniques intentionally.
        """
        # Shrink the budget to 1 for this test (auto-rolled back at test teardown).
        TechniqueTierBudget.objects.update_or_create(
            tier=1,
            defaults={
                "power_budget": 1,
                "representative_level": 1,
                "label": "Tier 1",
            },
        )

        # Build a complete draft with intensity=5, control=5 → cost 10 >> budget 1.
        self._run("draft Budget Breaker")
        self._run(
            f"set gift={self.gift.pk}"
            f" style={self.style.pk}"
            f" effect_type={self.effect_type.pk}"
            f" action_category=physical"
            f" tier=1"
            f" intensity=5"
            f" control=5"
            f" anima_cost=2"
        )

        # Price should report over budget.
        self.character.msg.reset_mock()
        self._run("price")
        price_output = self._output()
        assert "over budget" in price_output.lower(), (
            f"Expected 'over budget' indicator in price output, got: {price_output!r}"
        )

        # Author still creates the Technique (StaffPolicy is advisory).
        count_before = Technique.objects.count()
        self.character.msg.reset_mock()
        self._run("author")

        assert Technique.objects.count() == count_before + 1, (
            "Staff author creates Technique even when over advisory budget."
        )
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists(), (
            "Draft must be discarded after successful staff author."
        )

        author_output = self._output()
        assert "Budget Breaker" in author_output, (
            f"Expected technique name in staff author output, got: {author_output!r}"
        )
