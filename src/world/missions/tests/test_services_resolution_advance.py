"""Tests for the Phase-5a I-1 routing-free check primitive.

``resolve_option(..., advance=False)`` must perform the check + per-act
consequence/rider application + emit the ``MissionDeedRecord`` exactly as
``advance=True`` does, but MUST NOT route the graph or terminate the run:
``instance.current_node`` / ``status`` / ``completed_at`` are left
untouched. ``advance=True`` (the default) is unchanged Phase-3 behavior.

This is the primitive the Phase-4 JOINT orchestrator now uses so that no
attempt ever transiently routes/terminates the instance mid-loop; the
single combined decision is the only thing that routes.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.missions.constants import (
    MissionStatus,
    OptionKind,
    OptionProduces,
    OptionSource,
)
from world.missions.factories import (
    AffordanceBindingFactory,
    AffordanceFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRecord
from world.missions.services import resolve_option
from world.traits.factories import CheckOutcomeFactory

_APPLY = "world.missions.services.resolution.apply_resolution"


class ResolveOptionAdvanceFalseTests(TestCase):
    """advance=False resolves the check + deed but never routes/terminates."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.template = MissionTemplateFactory(slug="advance-tmpl", risk_tier=3)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.dest = MissionNodeFactory(template=cls.template, key="dest")
        cls.instance = MissionInstanceFactory(
            template=cls.template,
            current_node=cls.entry,
        )
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.character,
            is_contract_holder=True,
        )

        cls.success = CheckOutcomeFactory(name="AdvSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="AdvSneak")
        cls.check_option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.sneak,
        )
        cls.success_conseq = ConsequenceFactory(outcome_tier=cls.success)
        MissionOptionRouteFactory(
            option=cls.check_option,
            outcome_tier=cls.success,
            target_node=cls.dest,
            consequence=cls.success_conseq,
        )

    def test_advance_false_emits_deed_without_routing(self) -> None:
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            deed = resolve_option(
                self.instance,
                self.entry,
                self.check_option,
                self.actor,
                None,
                advance=False,
            )
        self.instance.refresh_from_db()
        # Deed emitted with the rolled outcome + correct actor (same as
        # advance=True).
        self.assertEqual(deed.outcome, self.success)
        self.assertEqual(deed.actor, self.character)
        self.assertTrue(MissionDeedRecord.objects.filter(pk=deed.pk).exists())
        # Per-act consequence still applied (the reuse boundary).
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(
            mocked.call_args_list[0].args[0].selected_consequence,
            self.success_conseq,
        )
        # But the instance position/status is UNTOUCHED — no routing.
        self.assertEqual(self.instance.current_node, self.entry)
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)
        self.assertIsNone(self.instance.completed_at)

    def test_advance_false_does_not_terminate_on_terminal_route(self) -> None:
        # A terminal (null target) route would COMPLETE the run under
        # advance=True; advance=False must leave the run ACTIVE.
        term_option = MissionOptionFactory(
            node=self.entry,
            order=1,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        MissionOptionRouteFactory(
            option=term_option,
            outcome_tier=self.success,
            target_node=None,  # terminal under advance=True
        )
        with force_check_outcome(self.success):
            resolve_option(
                self.instance,
                self.entry,
                term_option,
                self.actor,
                None,
                advance=False,
            )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)
        self.assertIsNone(self.instance.completed_at)
        self.assertEqual(self.instance.current_node, self.entry)

    def test_advance_false_applies_permitted_rider(self) -> None:
        rider = ConsequenceFactory(outcome_tier=self.success)
        self.entry.allowed_riders.add(rider)
        dist = DistinctionFactory(slug="adv-rider-dist")
        CharacterDistinctionFactory(character=self.character, distinction=dist)
        aff = AffordanceFactory(name="adv-rider-aff")
        binding = AffordanceBindingFactory(
            source_kind="distinction",
            source_distinction=dist,
            affordance=aff,
            produces=OptionProduces.CHECK,
            check_type=self.sneak,
            rider=rider,
        )
        with force_check_outcome(self.success), patch(_APPLY) as mocked:
            resolve_option(
                self.instance,
                self.entry,
                self.check_option,
                self.actor,
                binding,
                advance=False,
            )
        # Route consequence THEN rider — additive composition unchanged.
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(
            mocked.call_args_list[1].args[0].selected_consequence,
            rider,
        )

    def test_advance_true_default_still_routes(self) -> None:
        # Regression guard: the default path is unchanged Phase-3 behavior.
        with force_check_outcome(self.success):
            resolve_option(
                self.instance,
                self.entry,
                self.check_option,
                self.actor,
                None,
            )
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.dest)

    def test_advance_false_branch_option_no_routing(self) -> None:
        branch_option = MissionOptionFactory(
            node=self.entry,
            order=2,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            branch_target=self.dest,
        )
        with patch("world.missions.services.resolution.perform_check") as pc:
            deed = resolve_option(
                self.instance,
                self.entry,
                branch_option,
                self.actor,
                None,
                advance=False,
            )
        pc.assert_not_called()
        self.instance.refresh_from_db()
        # BRANCH deed: no dice (outcome None), and no routing under
        # advance=False.
        self.assertIsNone(deed.outcome)
        self.assertEqual(self.instance.current_node, self.entry)
        self.assertEqual(self.instance.status, MissionStatus.ACTIVE)
