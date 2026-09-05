from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import DeedCrimeTag, PersonaHeat
from world.justice.reaction_kinds import (
    IGNORE_CHOICE,
    INTERVENE_CHOICE,
    REPORT_CHOICE,
    WITNESS_KIND,
    open_witness_window,
)
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import MissionDeedRecordFactory, MissionDeedRewardLineFactory
from world.missions.integrations import crime_watch
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.reaction_models import WindowReaction
from world.scenes.reaction_services import get_reaction_kind, react_to_window
from world.societies.factories import LegendEntryFactory, SocietyFactory
from world.societies.models import SocietyReputation


class WitnessKindConstantTests(TestCase):
    def test_witness_kind_exists(self) -> None:
        self.assertEqual(ReactionWindowKind.WITNESS, "witness")


def make_participant(scene, *, link_account=True):
    """Account-backed persona participating in ``scene`` (full roster chain).

    Mirrors the kudos/spread-assist reaction-kind test fixtures.
    """
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    if link_account:
        character.db_account = account
        character.save()
    return roster_entry.character_sheet.primary_persona


class WitnessReactionKindTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.theft = CrimeKindFactory(slug="witness-theft", name="Theft")
        cls.assault = CrimeKindFactory(slug="witness-assault", name="Assault")
        cls.theft_law = AreaLawFactory(
            area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT
        )
        cls.assault_law = AreaLawFactory(
            area=cls.kingdom, crime_kind=cls.assault, heat_weight=DEFAULT_HEAT_WEIGHT
        )

    def setUp(self) -> None:
        self.room = RoomProfileFactory(area=self.city)
        self.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC, location=self.room.objectdb)
        self.witness = make_participant(self.scene)
        # The deed's actor: an established persona (reputation-eligible), not
        # itself a scene participant — the deed can be reported wherever
        # bystanders happen to be, not only where the actor is present.
        self.actor = PersonaFactory()
        self.interaction = InteractionFactory(persona=self.actor, scene=self.scene)
        self.deed = LegendEntryFactory(persona=self.actor)
        DeedCrimeTag.objects.create(deed=self.deed, crime_kind=self.theft)
        DeedCrimeTag.objects.create(deed=self.deed, crime_kind=self.assault)
        self.window = open_witness_window(interaction=self.interaction, entry=self.deed)

    def test_choices_are_the_three_static_slugs(self) -> None:
        config = get_reaction_kind(ReactionWindowKind.WITNESS)
        slugs = [choice.slug for choice in config.choices_for(self.window)]
        self.assertEqual(slugs, [REPORT_CHOICE, INTERVENE_CHOICE, IGNORE_CHOICE])

    def test_report_accrues_heat_once_per_crime_tag_and_stings_reputation(self) -> None:
        react_to_window(window=self.window, reactor_persona=self.witness, choice=REPORT_CHOICE)

        row = PersonaHeat.objects.get(persona=self.actor)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT * 2)
        rep = SocietyReputation.objects.get(persona=self.actor, society=self.crown)
        self.assertEqual(rep.value, -DEFAULT_HEAT_WEIGHT * 2)

        # Parity check: flag_crime's CRIME_WATCH path, reporting one crime
        # kind at the same room, mints the exact same per-tag magnitude —
        # both paths now share report_witnessed_crime as their core.
        sheet = CharacterSheetFactory()
        deed_record = MissionDeedRecordFactory(actor=sheet)
        line = MissionDeedRewardLineFactory(
            deed=deed_record,
            recipient=sheet,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
            ref=self.theft.slug,
        )
        crime_watch.flag_crime(line, room=self.room.objectdb)
        comparison_row = PersonaHeat.objects.get(persona=sheet.primary_persona)
        comparison_rep = SocietyReputation.objects.get(
            persona=sheet.primary_persona, society=self.crown
        )
        self.assertEqual(comparison_row.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(comparison_rep.value, -DEFAULT_HEAT_WEIGHT)
        self.assertEqual(row.value, comparison_row.value * 2)
        self.assertEqual(rep.value, comparison_rep.value * 2)

    def test_ignore_and_intervene_write_a_reaction_and_no_heat(self) -> None:
        second_witness = make_participant(self.scene)

        react_to_window(window=self.window, reactor_persona=self.witness, choice=INTERVENE_CHOICE)
        react_to_window(window=self.window, reactor_persona=second_witness, choice=IGNORE_CHOICE)

        self.assertEqual(
            set(WindowReaction.objects.filter(window=self.window).values_list("choice", flat=True)),
            {INTERVENE_CHOICE, IGNORE_CHOICE},
        )
        self.assertFalse(PersonaHeat.objects.exists())
        self.assertFalse(SocietyReputation.objects.filter(persona=self.actor).exists())

    def test_non_witness_is_rejected_by_the_existing_gate(self) -> None:
        stranger = PersonaFactory()  # never joined the scene

        with self.assertRaises(ValidationError):
            react_to_window(window=self.window, reactor_persona=stranger, choice=REPORT_CHOICE)

    def test_kind_is_registered_and_hidden(self) -> None:
        config = get_reaction_kind(ReactionWindowKind.WITNESS)
        self.assertIs(config, WITNESS_KIND)
        self.assertFalse(config.public)
        self.assertFalse(config.lazy_open)
