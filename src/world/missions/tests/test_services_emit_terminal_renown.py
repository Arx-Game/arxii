"""Tests for ``emit_terminal_renown_awards`` (#735).

Parallel to ``emit_terminal_rewards`` (flat-reward emission) — walks
``route.renown_awards`` and fires ``fire_renown_award`` per
(award × recipient). Real factory objects, no mocks.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import OptionKind, OptionSource, RewardGroupRule
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionRenownAward
from world.missions.services.renown_emission import emit_terminal_renown_awards
from world.societies.constants import (
    MAGNITUDE_FAME_AWARDS,
    MAGNITUDE_PRESTIGE_AWARDS,
    RenownMagnitude,
    RenownRisk,
)


def _make_holder_setup(template_name: str = "renown-emission-tmpl"):
    """Build a MissionInstance with a contract-holder participant + a terminal route."""
    template = MissionTemplateFactory(
        name=template_name, reward_group_rule=RewardGroupRule.ALL_EQUAL
    )
    node = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(
        node=node,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
    )
    route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
    instance = MissionInstanceFactory(template=template)
    holder_char = CharacterFactory(db_key="RenownHolder")
    CharacterSheetFactory(character=holder_char)
    holder = MissionParticipantFactory(
        instance=instance, character=holder_char, is_contract_holder=True
    )
    deed = MissionDeedRecordFactory(instance=instance, actor=holder_char, node=node, option=option)
    return instance, route, deed, holder


class EmitRenownAwardsContractHolderTests(TestCase):
    def test_no_awards_returns_empty_list(self) -> None:
        instance, route, deed, _ = _make_holder_setup()
        results = emit_terminal_renown_awards(instance, route, deed)
        self.assertEqual(results, [])

    def test_contract_holder_only_award_fires_on_holder_persona(self) -> None:
        instance, route, deed, holder = _make_holder_setup()
        MissionRenownAward.objects.create(
            route=route,
            magnitude=RenownMagnitude.MODERATE,
            risk=RenownRisk.NONE,
            contract_holder_only=True,
        )

        results = emit_terminal_renown_awards(instance, route, deed)

        self.assertEqual(len(results), 1)
        result = results[0]
        holder_persona = holder.character.sheet_data.primary_persona
        self.assertEqual(result.persona_id, holder_persona.pk)
        holder_persona.refresh_from_db()
        self.assertEqual(holder_persona.fame_points, MAGNITUDE_FAME_AWARDS["moderate"])
        self.assertEqual(holder_persona.prestige_from_deeds, MAGNITUDE_PRESTIGE_AWARDS["moderate"])

    def test_accepted_as_persona_wins_over_primary(self) -> None:
        """When instance.accepted_as_persona is set, holder-only fires on it."""
        from world.scenes.factories import PersonaFactory

        instance, route, deed, holder = _make_holder_setup()
        accepted = PersonaFactory(character_sheet=holder.character.sheet_data)
        instance.accepted_as_persona = accepted
        instance.save(update_fields=["accepted_as_persona"])
        MissionRenownAward.objects.create(
            route=route, magnitude=RenownMagnitude.HIGH, contract_holder_only=True
        )

        results = emit_terminal_renown_awards(instance, route, deed)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].persona_id, accepted.pk)


class EmitRenownAwardsBroadcastTests(TestCase):
    def test_broadcast_award_fires_on_every_participant(self) -> None:
        instance, route, deed, holder = _make_holder_setup()
        # Add a second participant.
        other_char = CharacterFactory(db_key="RenownHelper")
        CharacterSheetFactory(character=other_char)
        MissionParticipantFactory(instance=instance, character=other_char, is_contract_holder=False)
        MissionRenownAward.objects.create(
            route=route,
            magnitude=RenownMagnitude.SMALL,
            contract_holder_only=False,
        )

        results = emit_terminal_renown_awards(instance, route, deed)

        self.assertEqual(len(results), 2)
        result_personas = {r.persona_id for r in results}
        holder_persona_pk = holder.character.sheet_data.primary_persona.pk
        other_persona_pk = other_char.sheet_data.primary_persona.pk
        self.assertEqual(result_personas, {holder_persona_pk, other_persona_pk})

    def test_by_role_stub_sealed_raises(self) -> None:
        instance, route, deed, _ = _make_holder_setup()
        instance.template.reward_group_rule = RewardGroupRule.BY_ROLE
        instance.template.save(update_fields=["reward_group_rule"])
        MissionRenownAward.objects.create(
            route=route,
            magnitude=RenownMagnitude.MODERATE,
            contract_holder_only=False,
        )

        with self.assertRaises(NotImplementedError):
            emit_terminal_renown_awards(instance, route, deed)


class EmitRenownAwardsMultiAwardTests(TestCase):
    def test_multiple_awards_all_fire(self) -> None:
        instance, route, deed, holder = _make_holder_setup()
        MissionRenownAward.objects.create(
            route=route,
            magnitude=RenownMagnitude.MODERATE,
            contract_holder_only=True,
        )
        MissionRenownAward.objects.create(
            route=route,
            magnitude=RenownMagnitude.HIGH,
            risk=RenownRisk.LOW,
            contract_holder_only=True,
        )

        results = emit_terminal_renown_awards(instance, route, deed)

        self.assertEqual(len(results), 2)
        holder_persona = holder.character.sheet_data.primary_persona
        holder_persona.refresh_from_db()
        # Both awards land on the same persona.
        expected_fame = MAGNITUDE_FAME_AWARDS["moderate"] + MAGNITUDE_FAME_AWARDS["high"]
        self.assertEqual(holder_persona.fame_points, expected_fame)
