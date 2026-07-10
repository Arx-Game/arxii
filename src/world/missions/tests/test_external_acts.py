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
from world.missions.constants import ExternalAct, OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRecord
from world.missions.services import build_option_list, resolve_option
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
