"""Per-persona deed knowledge: vectors, union gate, echo (#902)."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.societies.constants import DeedKnowledgeSource
from world.societies.factories import (
    LegendEntryFactory,
    LegendSourceTypeFactory,
)
from world.societies.knowledge_services import (
    grant_deed_knowledge,
    known_deed_ids,
    scene_witness_personas,
)
from world.societies.models import LegendEntry, PersonaDeedKnowledge
from world.societies.services import create_solo_deed, spread_deed
from world.societies.spread_services import get_spreadable_deeds


def make_participant(scene):
    """Account-backed persona participating in ``scene`` (full roster chain)."""
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    return roster_entry.character_sheet.primary_persona


class GrantDeedKnowledgeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.doer = make_participant(cls.scene)
        cls.witness = make_participant(cls.scene)
        cls.deed = LegendEntryFactory(persona=cls.doer, base_value=100)

    def test_grant_skips_the_doer_and_is_idempotent(self) -> None:
        created = grant_deed_knowledge(
            deed=self.deed,
            personas=[self.doer, self.witness],
            source=DeedKnowledgeSource.WITNESSED,
        )
        assert created == 1
        again = grant_deed_knowledge(
            deed=self.deed,
            personas=[self.witness],
            source=DeedKnowledgeSource.HEARD_TOLD,
        )
        assert again == 0
        row = PersonaDeedKnowledge.objects.get(persona=self.witness, deed=self.deed)
        assert row.source == DeedKnowledgeSource.WITNESSED  # first vector wins

    def test_scene_witnesses_include_interactors_and_silent_participants(self) -> None:
        InteractionFactory(persona=self.witness, scene=self.scene)
        silent = make_participant(self.scene)
        witnesses = scene_witness_personas(self.scene)
        assert self.witness in witnesses
        assert silent in witnesses


class KnownDeedIdsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.doer = make_participant(cls.scene)
        cls.stranger = make_participant(cls.scene)
        cls.source_type = LegendSourceTypeFactory()

    def test_doer_knows_own_deed(self) -> None:
        deed = LegendEntryFactory(persona=self.doer, base_value=100)
        assert deed.pk in {row["pk"] for row in known_deed_ids(self.doer)}

    def test_knowledge_row_grants_access(self) -> None:
        deed = LegendEntryFactory(persona=self.doer, base_value=100)
        assert deed.pk not in {row["pk"] for row in known_deed_ids(self.stranger)}
        grant_deed_knowledge(
            deed=deed, personas=[self.stranger], source=DeedKnowledgeSource.WITNESSED
        )
        assert deed.pk in {row["pk"] for row in known_deed_ids(self.stranger)}
        assert deed in get_spreadable_deeds(self.stranger)

    def test_common_knowledge_at_five_times_base(self) -> None:
        deed = LegendEntryFactory(persona=self.doer, base_value=100, spread_multiplier=9)
        spreader = make_participant(self.scene)
        # 399 spread → total 499 < 500: not yet common knowledge.
        spread_deed(deed=deed, spreader_persona=spreader, value_added=399)
        assert deed.pk not in {row["pk"] for row in known_deed_ids(self.stranger)}
        assert not LegendEntry.objects.get(pk=deed.pk).is_common_knowledge
        # One more point crosses the 5× gate (total 500 ≥ 500).
        spread_deed(deed=deed, spreader_persona=spreader, value_added=1)
        assert LegendEntry.objects.get(pk=deed.pk).is_common_knowledge
        assert deed.pk in {row["pk"] for row in known_deed_ids(self.stranger)}

    def test_inactive_deed_never_known(self) -> None:
        deed = LegendEntryFactory(persona=self.doer, base_value=100, is_active=False)
        grant_deed_knowledge(
            deed=deed, personas=[self.stranger], source=DeedKnowledgeSource.WITNESSED
        )
        assert deed.pk not in {row["pk"] for row in known_deed_ids(self.stranger)}


class WitnessWriteSiteTests(TestCase):
    def test_create_solo_deed_grants_scene_witnesses(self) -> None:
        scene = SceneFactory()
        doer = make_participant(scene)
        watcher = make_participant(scene)
        InteractionFactory(persona=watcher, scene=scene)
        source_type = LegendSourceTypeFactory()
        deed = create_solo_deed(doer, "Slew the wyrm", source_type, 100, scene=scene)
        row = PersonaDeedKnowledge.objects.get(persona=watcher, deed=deed)
        assert row.source == DeedKnowledgeSource.WITNESSED
        assert not PersonaDeedKnowledge.objects.filter(persona=doer, deed=deed).exists()


class DeedNamedEchoTests(TestCase):
    """The telling's outcome line names the tale (#902)."""

    def test_spread_result_interaction_names_the_deed(self) -> None:
        from world.scenes.action_services import _create_result_interaction
        from world.scenes.factories import SceneActionRequestFactory
        from world.scenes.tests.cast_test_helpers import make_enhanced_result

        scene = SceneFactory()
        teller = make_participant(scene)
        deed = LegendEntryFactory(persona=teller, base_value=100, title="The Sack of Veil Harbor")
        request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=teller,
            target_persona=None,
            action_key="spread_a_tale",
            spread_deed_target=deed,
            pose_text="",
        )
        interaction = _create_result_interaction(
            action_request=request, result=make_enhanced_result("spread_a_tale")
        )
        assert "spreads the tale of «The Sack of Veil Harbor»" in interaction.content
