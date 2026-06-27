"""Unit tests for the ritual draft/join adapter registry (#1346).

Covers the SoulTetherAdapter token-parsing logic and the get_adapter registry lookup.
The broader E2E behaviour (parse → draft_session → fire → accept_soul_tether_via_session)
is covered by test_ritual_session_kwargs and test_soul_tether_telnet_journey_e2e.
"""

from __future__ import annotations

from django.test import TestCase

from commands.exceptions import CommandError
from commands.ritual_adapters import (
    DraftParse,
    JoinParse,
    RitualDraftAdapter,
    SoulTetherAdapter,
    get_adapter,
)
from world.magic.constants import ParticipationRule, RitualExecutionKind
from world.magic.factories import (
    AcceptSoulTetherRitualFactory,
    AffinityFactory,
    ResonanceFactory,
    RitualFactory,
    wire_soul_tether_content,
)


class SoulTetherAdapterDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(affinity=cls.affinity)

    def test_resonance_goes_to_session_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(
            kwargs={"role": "sinner", "resonance": self.resonance.name, "writeup": "a bond"},
            caller=None,
        )
        self.assertIn("resonance_id", parse.session_kwargs)
        self.assertEqual(parse.session_kwargs["resonance_id"], self.resonance.pk)
        self.assertEqual(parse.session_kwargs["writeup"], "a bond")

    def test_role_goes_to_initiator_participant_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(
            kwargs={"role": "sineater", "resonance": self.resonance.name},
            caller=None,
        )
        self.assertEqual(parse.initiator_participant_kwargs.get("soul_tether_role"), "SINEATER")

    def test_role_normalised_to_uppercase(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(kwargs={"role": "SINNER"}, caller=None)
        self.assertEqual(parse.initiator_participant_kwargs.get("soul_tether_role"), "SINNER")

    def test_unknown_role_raises_command_error(self) -> None:
        adapter = SoulTetherAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_draft(kwargs={"role": "wizard"}, caller=None)
        self.assertIn("Unknown role", str(ctx.exception))

    def test_unknown_resonance_raises_command_error(self) -> None:
        adapter = SoulTetherAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_draft(kwargs={"resonance": "NoSuchResonance"}, caller=None)
        self.assertIn("No resonance named", str(ctx.exception))

    def test_missing_role_skips_participant_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(
            kwargs={"resonance": self.resonance.name},
            caller=None,
        )
        self.assertNotIn("soul_tether_role", parse.initiator_participant_kwargs)
        self.assertIn("resonance_id", parse.session_kwargs)

    def test_missing_resonance_skips_session_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(kwargs={"role": "sinner"}, caller=None)
        self.assertNotIn("resonance_id", parse.session_kwargs)
        self.assertIn("soul_tether_role", parse.initiator_participant_kwargs)

    def test_empty_kwargs_returns_empty_parse(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(kwargs={}, caller=None)
        self.assertEqual(parse.session_kwargs, {})
        self.assertEqual(parse.initiator_participant_kwargs, {})
        self.assertEqual(parse.session_references, [])
        self.assertEqual(parse.initiator_references, [])

    def test_parse_result_is_draft_parse(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_draft(kwargs={}, caller=None)
        self.assertIsInstance(parse, DraftParse)


class SoulTetherAdapterJoinTests(TestCase):
    def test_role_goes_to_participant_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_join(kwargs={"role": "sineater"}, caller=None)
        self.assertIsInstance(parse, JoinParse)
        self.assertEqual(parse.participant_kwargs.get("soul_tether_role"), "SINEATER")
        self.assertEqual(parse.references, [])

    def test_unknown_role_raises_command_error(self) -> None:
        adapter = SoulTetherAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_join(kwargs={"role": "wizard"}, caller=None)
        self.assertIn("Unknown role", str(ctx.exception))

    def test_no_role_returns_empty_participant_kwargs(self) -> None:
        adapter = SoulTetherAdapter()
        parse = adapter.parse_join(kwargs={}, caller=None)
        self.assertEqual(parse.participant_kwargs, {})


class BaseAdapterTests(TestCase):
    def test_parse_draft_returns_empty(self) -> None:
        adapter = RitualDraftAdapter()
        parse = adapter.parse_draft(kwargs={"role": "sinner", "resonance": "foo"}, caller=None)
        self.assertIsInstance(parse, DraftParse)
        self.assertEqual(parse.session_kwargs, {})
        self.assertEqual(parse.initiator_participant_kwargs, {})
        self.assertEqual(parse.session_references, [])
        self.assertEqual(parse.initiator_references, [])

    def test_parse_join_returns_empty(self) -> None:
        adapter = RitualDraftAdapter()
        parse = adapter.parse_join(kwargs={"role": "sinner"}, caller=None)
        self.assertIsInstance(parse, JoinParse)
        self.assertEqual(parse.participant_kwargs, {})
        self.assertEqual(parse.references, [])


class GetAdapterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        cls.soul_tether_ritual = AcceptSoulTetherRitualFactory()
        cls.other_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SERVICE,
            participation_rule=ParticipationRule.FORMATION,
            service_function_path="world.magic.services.placeholder_ritual",
        )

    def test_soul_tether_ritual_gets_soul_tether_adapter(self) -> None:
        adapter = get_adapter(self.soul_tether_ritual)
        self.assertIsInstance(adapter, SoulTetherAdapter)

    def test_unregistered_ritual_gets_base_adapter(self) -> None:
        adapter = get_adapter(self.other_ritual)
        self.assertIsInstance(adapter, RitualDraftAdapter)
        self.assertNotIsInstance(adapter, SoulTetherAdapter)
