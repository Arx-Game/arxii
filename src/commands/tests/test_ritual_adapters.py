"""Unit tests for the ritual draft/join adapter registry (#1346).

Covers the SoulTetherAdapter token-parsing logic and the get_adapter registry lookup.
The broader E2E behaviour (parse → draft_session → fire → accept_soul_tether_via_session)
is covered by test_ritual_session_kwargs and test_soul_tether_telnet_journey_e2e.
"""

from __future__ import annotations

from django.test import TestCase

from commands.exceptions import CommandError
from commands.ritual_adapters import (
    BannerCallAdapter,
    CovenantInductionAdapter,
    DraftParse,
    JoinParse,
    RitualDraftAdapter,
    SoulTetherAdapter,
    get_adapter,
)
from world.covenants.factories import CovenantFactory, CovenantRoleFactory
from world.magic.constants import ParticipationRule, ReferenceKind, RitualExecutionKind
from world.magic.factories import (
    AcceptSoulTetherRitualFactory,
    AffinityFactory,
    BattleCovenantRiseRitualFactory,
    CovenantInductionRitualFactory,
    ResonanceFactory,
    RitualFactory,
    wire_soul_tether_content,
)
from world.magic.types.sessions import RitualSessionReferenceSpec


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

    def test_induction_ritual_gets_induction_adapter(self) -> None:
        ritual = CovenantInductionRitualFactory()
        adapter = get_adapter(ritual)
        self.assertIsInstance(adapter, CovenantInductionAdapter)

    def test_banner_call_ritual_gets_banner_call_adapter(self) -> None:
        ritual = BattleCovenantRiseRitualFactory()
        adapter = get_adapter(ritual)
        self.assertIsInstance(adapter, BannerCallAdapter)


class CovenantInductionAdapterDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory(name="The Ember Throne")

    def test_builds_covenant_session_reference(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "The Ember Throne"}, caller=None)
        self.assertIsInstance(parse, DraftParse)
        self.assertEqual(len(parse.session_references), 1)
        ref = parse.session_references[0]
        self.assertIsInstance(ref, RitualSessionReferenceSpec)
        self.assertEqual(ref.kind, ReferenceKind.COVENANT)
        self.assertEqual(ref.ref_covenant, self.covenant)

    def test_covenant_lookup_is_case_insensitive(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "the ember throne"}, caller=None)
        self.assertEqual(parse.session_references[0].ref_covenant, self.covenant)

    def test_unknown_covenant_raises_command_error(self) -> None:
        adapter = CovenantInductionAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_draft(kwargs={"covenant": "No Such Covenant"}, caller=None)
        self.assertIn("No covenant named", str(ctx.exception))

    def test_returns_empty_session_kwargs_and_initiator_refs(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "The Ember Throne"}, caller=None)
        self.assertEqual(parse.session_kwargs, {})
        self.assertEqual(parse.initiator_references, [])
        self.assertEqual(parse.initiator_participant_kwargs, {})


class CovenantInductionAdapterJoinTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory(name="Vanguard")

    def test_builds_covenant_role_reference(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_join(kwargs={"role": "Vanguard"}, caller=None)
        self.assertIsInstance(parse, JoinParse)
        self.assertEqual(len(parse.references), 1)
        ref = parse.references[0]
        self.assertIsInstance(ref, RitualSessionReferenceSpec)
        self.assertEqual(ref.kind, ReferenceKind.COVENANT_ROLE)
        self.assertEqual(ref.ref_covenant_role, self.role)

    def test_role_lookup_is_case_insensitive(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_join(kwargs={"role": "vanguard"}, caller=None)
        self.assertEqual(parse.references[0].ref_covenant_role, self.role)

    def test_unknown_role_raises_command_error(self) -> None:
        adapter = CovenantInductionAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_join(kwargs={"role": "No Such Role"}, caller=None)
        self.assertIn("No covenant role named", str(ctx.exception))

    def test_returns_empty_participant_kwargs(self) -> None:
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_join(kwargs={"role": "Vanguard"}, caller=None)
        self.assertEqual(parse.participant_kwargs, {})

    def test_multi_word_role_resolves_correctly(self) -> None:
        """``role=Iron Warden`` (assembled by the fixed _handle_join tokenizer) resolves."""
        role = CovenantRoleFactory(name="Iron Warden")
        adapter = CovenantInductionAdapter()
        parse = adapter.parse_join(kwargs={"role": "Iron Warden"}, caller=None)
        self.assertIsInstance(parse, JoinParse)
        self.assertEqual(len(parse.references), 1)
        self.assertEqual(parse.references[0].ref_covenant_role, role)


class BannerCallAdapterDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory(name="Iron Banner")

    def test_builds_covenant_session_reference(self) -> None:
        adapter = BannerCallAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "Iron Banner"}, caller=None)
        self.assertIsInstance(parse, DraftParse)
        self.assertEqual(len(parse.session_references), 1)
        ref = parse.session_references[0]
        self.assertEqual(ref.kind, ReferenceKind.COVENANT)
        self.assertEqual(ref.ref_covenant, self.covenant)

    def test_covenant_lookup_is_case_insensitive(self) -> None:
        adapter = BannerCallAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "iron banner"}, caller=None)
        self.assertEqual(parse.session_references[0].ref_covenant, self.covenant)

    def test_unknown_covenant_raises_command_error(self) -> None:
        adapter = BannerCallAdapter()
        with self.assertRaises(CommandError) as ctx:
            adapter.parse_draft(kwargs={"covenant": "No Such Covenant"}, caller=None)
        self.assertIn("No covenant named", str(ctx.exception))

    def test_returns_empty_session_kwargs(self) -> None:
        adapter = BannerCallAdapter()
        parse = adapter.parse_draft(kwargs={"covenant": "Iron Banner"}, caller=None)
        self.assertEqual(parse.session_kwargs, {})


class BannerCallAdapterJoinTests(TestCase):
    def test_parse_join_returns_empty(self) -> None:
        adapter = BannerCallAdapter()
        parse = adapter.parse_join(kwargs={}, caller=None)
        self.assertIsInstance(parse, JoinParse)
        self.assertEqual(parse.participant_kwargs, {})
        self.assertEqual(parse.references, [])
