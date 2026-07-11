"""EXTERNAL_ACT resolution + presentation (#1035).

EXTERNAL_ACT options resolve via the same no-check branch path as BRANCH
(``_resolve_branch``: deed ``outcome=None``, routes via ``branch_target`` or
a null-tier route, terminal otherwise) but are NEVER surfaced in a pickable
option list — they only ever resolve when ``satisfy_external_act`` (Task 3)
calls ``resolve_option`` directly on the player's behalf after a real
non-mission act.

Model-level validation (``required_act`` requiredness/exclusivity) lives in
``test_models_option_external_act.py``; this file covers the resolution
dispatch and the presentation/pick-entrypoint exclusion.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CharacterCovenantRoleFactory
from world.magic.factories import ThreadFactory
from world.missions.constants import ExternalAct, MissionStatus, OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRecord
from world.missions.services import build_option_list, enter_node, resolve_option
from world.missions.services.external_acts import satisfy_external_act
from world.missions.services.multiplayer import build_group_option_list


class ResolveExternalActOptionTests(TestCase):
    """EXTERNAL_ACT routes via the same no-check branch path as BRANCH."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="external-act-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.template, key="target")
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )

    def test_external_act_routes_to_target_and_outcome_is_none(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
            branch_target=self.target,
        )
        with patch("world.missions.services.resolution.perform_check") as pc:
            deed = resolve_option(self.instance, self.entry, option, self.actor)
        pc.assert_not_called()
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.target)
        self.assertIsNone(deed.outcome)
        self.assertTrue(MissionDeedRecord.objects.filter(pk=deed.pk).exists())

    def test_external_act_via_null_tier_route(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=1,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.THREAD_WOVEN,
        )
        MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=self.target)
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.target)
        self.assertIsNone(deed.outcome)

    def test_external_act_with_no_target_terminates_run(self) -> None:
        option = MissionOptionFactory(
            node=self.entry,
            order=2,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
        )
        deed = resolve_option(self.instance, self.entry, option, self.actor)
        self.instance.refresh_from_db()
        self.assertIsNone(self.instance.current_node)
        self.assertIsNone(deed.outcome)


class ExternalActNeverPickableTests(TestCase):
    """EXTERNAL_ACT options are presented like any option's framing lives in
    node ``flavor_text``, but never enter a pickable option list on any
    presentation surface, and are rejected exactly like an unknown option id
    at every pick entrypoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="external-act-pick-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.instance = MissionInstanceFactory(template=cls.template, current_node=cls.entry)
        cls.actor = MissionParticipantFactory(
            instance=cls.instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )
        cls.branch_option = MissionOptionFactory(
            node=cls.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        cls.external_act_option = MissionOptionFactory(
            node=cls.entry,
            order=1,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
        )

    def test_solo_presentation_excludes_external_act(self) -> None:
        presented = build_option_list(self.instance, self.entry, self.actor)
        option_ids = [p.option.pk for p in presented]
        self.assertIn(self.branch_option.pk, option_ids)
        self.assertNotIn(self.external_act_option.pk, option_ids)

    def test_group_presentation_excludes_external_act(self) -> None:
        presented = build_group_option_list(self.instance, self.entry)
        option_ids = [p.option.pk for p in presented]
        self.assertIn(self.branch_option.pk, option_ids)
        self.assertNotIn(self.external_act_option.pk, option_ids)

    def test_resolve_beat_option_rejects_external_act_id(self) -> None:
        from world.missions.services.play import BeatActionError, resolve_beat_option

        with self.assertRaises(BeatActionError):
            resolve_beat_option(
                self.instance,
                self.actor.character,
                option_id=self.external_act_option.pk,
            )


class SatisfyExternalActTests(TestCase):
    """``satisfy_external_act`` resolves every ACTIVE instance waiting on the
    matching act, on the acting participant's behalf, with actor-only
    messaging (#1035 leak rule — no room emit)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character_sheet = CharacterSheetFactory()
        cls.template = MissionTemplateFactory(name="satisfy-external-act-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.template, key="target")

    def _make_waiting_instance(self, *, required_act: str) -> tuple[object, object]:
        instance = MissionInstanceFactory(template=self.template, current_node=self.entry)
        MissionParticipantFactory(
            instance=instance,
            character=self.character_sheet.character,
            is_contract_holder=True,
        )
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=required_act,
            branch_target=self.target,
        )
        return instance, option

    def test_matching_act_resolves_advances_and_messages_actor_only(self) -> None:
        instance, _option = self._make_waiting_instance(required_act=ExternalAct.TECHNIQUE_CAST)

        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            deeds = satisfy_external_act(self.character_sheet, ExternalAct.TECHNIQUE_CAST)

        self.assertEqual(len(deeds), 1)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.target)
        sender.assert_called_once()
        _args, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.character_sheet])

    def test_wrong_act_is_a_noop(self) -> None:
        instance, _option = self._make_waiting_instance(required_act=ExternalAct.TECHNIQUE_CAST)

        deeds = satisfy_external_act(self.character_sheet, ExternalAct.THREAD_WOVEN)

        self.assertEqual(deeds, [])
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.entry)

    def test_no_active_instance_returns_empty_list(self) -> None:
        lone_sheet = CharacterSheetFactory()

        deeds = satisfy_external_act(lone_sheet, ExternalAct.TECHNIQUE_CAST)

        self.assertEqual(deeds, [])

    def test_two_active_instances_both_resolve(self) -> None:
        instance_one, _ = self._make_waiting_instance(required_act=ExternalAct.COVENANT_SWORN)
        instance_two, _ = self._make_waiting_instance(required_act=ExternalAct.COVENANT_SWORN)

        deeds = satisfy_external_act(self.character_sheet, ExternalAct.COVENANT_SWORN)

        self.assertEqual(len(deeds), 2)
        instance_one.refresh_from_db()
        instance_two.refresh_from_db()
        self.assertEqual(instance_one.current_node, self.target)
        self.assertEqual(instance_two.current_node, self.target)

    def test_instance_without_external_act_option_is_untouched(self) -> None:
        instance = MissionInstanceFactory(template=self.template, current_node=self.entry)
        MissionParticipantFactory(
            instance=instance,
            character=self.character_sheet.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            branch_target=self.target,
        )

        deeds = satisfy_external_act(self.character_sheet, ExternalAct.TECHNIQUE_CAST)

        self.assertEqual(deeds, [])
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.entry)

    def test_only_active_instances_are_considered(self) -> None:
        instance, _option = self._make_waiting_instance(required_act=ExternalAct.TECHNIQUE_CAST)
        instance.status = MissionStatus.COMPLETE
        instance.save()

        deeds = satisfy_external_act(self.character_sheet, ExternalAct.TECHNIQUE_CAST)

        self.assertEqual(deeds, [])


class FastForwardExternalActsTests(TestCase):
    """``enter_node`` fast-forwards a durable EXTERNAL_ACT option the
    contract-holder's sheet already satisfies (#1035); TECHNIQUE_CAST is
    transient and never fast-forwards."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character_sheet = CharacterSheetFactory()
        cls.template = MissionTemplateFactory(name="fast-forward-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.template, key="target")

    def _instance_with_option(self, *, required_act: str) -> tuple[object, object]:
        instance = MissionInstanceFactory(template=self.template)
        MissionParticipantFactory(
            instance=instance,
            character=self.character_sheet.character,
            is_contract_holder=True,
        )
        option = MissionOptionFactory(
            node=self.entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=required_act,
            branch_target=self.target,
        )
        return instance, option

    def test_thread_woven_fast_forwards_on_live_thread(self) -> None:
        instance, _option = self._instance_with_option(required_act=ExternalAct.THREAD_WOVEN)
        ThreadFactory(owner=self.character_sheet)

        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            enter_node(instance, self.entry)

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.target)
        sender.assert_called_once()
        _args, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.character_sheet])

    def test_covenant_sworn_fast_forwards_on_live_membership(self) -> None:
        instance, _option = self._instance_with_option(required_act=ExternalAct.COVENANT_SWORN)
        CharacterCovenantRoleFactory(character_sheet=self.character_sheet)

        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            enter_node(instance, self.entry)

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.target)
        sender.assert_called_once()
        _args, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.character_sheet])

    def test_technique_cast_never_fast_forwards(self) -> None:
        instance, _option = self._instance_with_option(required_act=ExternalAct.TECHNIQUE_CAST)
        # No durable state can ever satisfy TECHNIQUE_CAST — it's transient.

        enter_node(instance, self.entry)

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.entry)

    def test_no_matching_durable_state_leaves_node_untouched(self) -> None:
        instance, _option = self._instance_with_option(required_act=ExternalAct.THREAD_WOVEN)
        # No live Thread for this character_sheet.

        enter_node(instance, self.entry)

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, self.entry)


class WeaveThreadExternalActWiringTests(TestCase):
    """``weave_thread`` calls ``satisfy_external_act(THREAD_WOVEN)`` on success (#1035)."""

    def test_weave_thread_resolves_waiting_thread_woven_mission(self) -> None:
        from world.magic.constants import TargetKind
        from world.magic.factories import (
            CharacterThreadWeavingUnlockFactory,
            ResonanceFactory,
            ThreadWeavingUnlockFactory,
        )
        from world.magic.services import weave_thread
        from world.traits.factories import TraitFactory

        trait = TraitFactory()
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=100)

        template = MissionTemplateFactory(name="weave-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=sheet.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.THREAD_WOVEN,
            branch_target=target,
        )

        thread = weave_thread(sheet, TargetKind.TRAIT, trait, resonance, name="Wired Thread")

        self.assertEqual(thread.owner, sheet)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, target)


class WeaveGiftThreadExternalActWiringTests(TestCase):
    """``weave_thread``'s GIFT branch also calls ``satisfy_external_act(THREAD_WOVEN)``
    on success (#1035 review fix) — the GIFT branch early-returns before the general
    tail, so it needs its own wiring call (shared via ``_satisfy_thread_woven``)."""

    def test_weave_gift_thread_resolves_waiting_thread_woven_mission(self) -> None:
        from world.magic.constants import TargetKind
        from world.magic.factories import GiftFactory, ResonanceFactory
        from world.magic.services import weave_thread

        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        gift = GiftFactory()
        gift.resonances.add(resonance)

        template = MissionTemplateFactory(name="weave-gift-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=sheet.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.THREAD_WOVEN,
            branch_target=target,
        )

        thread = weave_thread(sheet, TargetKind.GIFT, gift, resonance)

        self.assertEqual(thread.owner, sheet)
        self.assertEqual(thread.target_kind, TargetKind.GIFT)
        instance.refresh_from_db()
        self.assertEqual(instance.current_node, target)


class CreateCovenantExternalActWiringTests(TestCase):
    """``create_covenant`` calls ``satisfy_external_act(COVENANT_SWORN)`` per founder (#1035)."""

    def test_create_covenant_resolves_covenant_sworn_for_every_founder(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant
        from world.covenants.types import CovenantFounder

        template = MissionTemplateFactory(name="covenant-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")

        founder_sheets = [CharacterSheetFactory(), CharacterSheetFactory()]
        instances = []
        for founder_sheet in founder_sheets:
            instance = MissionInstanceFactory(template=template, current_node=entry)
            MissionParticipantFactory(
                instance=instance,
                character=founder_sheet.character,
                is_contract_holder=True,
            )
            MissionOptionFactory(
                node=entry,
                order=0,
                option_kind=OptionKind.EXTERNAL_ACT,
                source_kind=OptionSource.AUTHORED,
                required_act=ExternalAct.COVENANT_SWORN,
                branch_target=target,
            )
            instances.append(instance)

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        founders = [
            CovenantFounder(character_sheet=founder_sheet, role=role)
            for founder_sheet in founder_sheets
        ]

        create_covenant(
            name="Wired Covenant",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="Prove the wiring.",
            founders=founders,
        )

        for instance in instances:
            instance.refresh_from_db()
            self.assertEqual(instance.current_node, target)


class InductMemberExternalActWiringTests(TestCase):
    """``induct_member_via_session`` calls ``satisfy_external_act(COVENANT_SWORN)``
    for the inducted candidate (#1035 review fold-in), mirroring
    ``CreateCovenantExternalActWiringTests`` for the induction path."""

    def _build_induction_session(self):
        """Minimal induction-session fixture, lifted from
        ``InductMemberViaSessionTests._build_induction_session``
        (``world/covenants/tests/test_services.py``) — trimmed to the one
        shape this test needs (one existing member, candidate chooses a role).
        Returns (session, candidate).
        """
        from datetime import UTC, datetime, timedelta

        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
        )
        from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind
        from world.magic.factories import RitualFactory
        from world.magic.models.sessions import (
            RitualSession,
            RitualSessionParticipant,
            RitualSessionReference,
        )

        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        existing_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        existing_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=existing_sheet,
            covenant=covenant,
            covenant_role=existing_role,
        )
        candidate = CharacterSheetFactory()
        chosen_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=existing_sheet,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=covenant,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=existing_sheet,
            state=ParticipantState.ACCEPTED,
        )
        candidate_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate,
            state=ParticipantState.ACCEPTED,
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=candidate_p,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=chosen_role,
        )
        return session, candidate

    def test_induct_member_resolves_waiting_covenant_sworn_mission(self) -> None:
        from world.covenants.services import induct_member_via_session

        session, candidate = self._build_induction_session()

        template = MissionTemplateFactory(name="induction-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=candidate.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
            branch_target=target,
        )

        induct_member_via_session(session=session)

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, target)


class UseTechniqueExternalActWiringTests(TestCase):
    """``use_technique`` calls ``satisfy_external_act(TECHNIQUE_CAST)`` on success (#1035)."""

    def test_use_technique_resolves_waiting_technique_cast_mission(self) -> None:
        from unittest.mock import MagicMock

        from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
        from world.magic.services import use_technique
        from world.mechanics.factories import CharacterEngagementFactory

        anima = CharacterAnimaFactory(current=20, maximum=20)
        character = anima.character
        CharacterEngagementFactory(character=character)
        sheet = CharacterSheetFactory(character=character)
        technique = TechniqueFactory(intensity=5, control=10, anima_cost=3)

        template = MissionTemplateFactory(name="technique-cast-wiring-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
            branch_target=target,
        )

        use_technique(
            character=character,
            technique=technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        instance.refresh_from_db()
        self.assertEqual(instance.current_node, target)
        self.assertIsNotNone(sheet)


class ExternalActFailureIsolationTests(TestCase):
    """A raising ``satisfy_external_act`` never aborts the host act (#1035, ADR-0112).

    ``notify_external_act``'s guard (``has_waiting_external_act``) only opens the
    savepoint and calls ``satisfy_external_act`` when a waiting mission exists, so
    this test must build one THREAD_WOVEN-waiting instance for the guard to pass —
    otherwise the patched ``satisfy_external_act`` would simply never be called.
    """

    def test_weave_thread_still_succeeds_and_logs_when_satisfy_external_act_raises(
        self,
    ) -> None:
        from world.magic.constants import TargetKind
        from world.magic.factories import (
            CharacterThreadWeavingUnlockFactory,
            ResonanceFactory,
            ThreadWeavingUnlockFactory,
        )
        from world.magic.models import Thread
        from world.magic.services import weave_thread
        from world.traits.factories import TraitFactory

        trait = TraitFactory()
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=100)

        template = MissionTemplateFactory(name="failure-isolation-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target_node = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=sheet.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.THREAD_WOVEN,
            branch_target=target_node,
        )

        with (
            patch(
                "world.missions.services.external_acts.satisfy_external_act",
                side_effect=RuntimeError("boom"),
            ),
            self.assertLogs("world.missions.services.external_acts", level="ERROR") as logs,
        ):
            thread = weave_thread(sheet, TargetKind.TRAIT, trait, resonance, name="Still Woven")

        self.assertIsInstance(thread, Thread)
        self.assertTrue(Thread.objects.filter(pk=thread.pk).exists())
        self.assertTrue(
            any("external-act satisfaction failed" in message for message in logs.output)
        )


class NotifyExternalActGuardTests(TestCase):
    """``notify_external_act``'s cheap EXISTS guard skips ``satisfy_external_act``
    entirely when nothing is waiting (#1035 CI query-scaling fix) — the combat cast
    path must pay exactly one indexed query per declaration, not the full
    savepoint + MissionParticipant walk, when the caster has no tutorial mission."""

    def test_no_waiting_mission_never_calls_satisfy_external_act(self) -> None:
        from world.missions.services.external_acts import notify_external_act

        sheet = CharacterSheetFactory()

        with patch("world.missions.services.external_acts.satisfy_external_act") as mock_satisfy:
            notify_external_act(sheet, ExternalAct.TECHNIQUE_CAST)

        mock_satisfy.assert_not_called()

    def test_waiting_mission_calls_satisfy_external_act(self) -> None:
        from world.missions.services.external_acts import notify_external_act

        sheet = CharacterSheetFactory()
        template = MissionTemplateFactory(name="notify-guard-tmpl")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        target = MissionNodeFactory(template=template, key="target")
        instance = MissionInstanceFactory(template=template, current_node=entry)
        MissionParticipantFactory(
            instance=instance,
            character=sheet.character,
            is_contract_holder=True,
        )
        MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
            branch_target=target,
        )

        with patch("world.missions.services.external_acts.satisfy_external_act") as mock_satisfy:
            notify_external_act(sheet, ExternalAct.TECHNIQUE_CAST)

        mock_satisfy.assert_called_once_with(sheet, ExternalAct.TECHNIQUE_CAST)
