"""Telnet E2E: reaction/favorite journey — react favorite/emoji/kudos (#1341).

Proves ``CmdReact`` reaches the same services the web viewsets use, via the
shared Actions. Two characters in a room with an active scene; mock only
``character.msg``; drive real commands + real services. Uses ``setUp`` (not
``setUpTestData``) for ObjectDB-bearing fixtures (idmapper deepcopy fails in
CI shard runs — see project memory).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from commands.react import CmdReact
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import DeedCrimeTag, PersonaHeat, WitnessReactionTarget
from world.justice.reaction_kinds import INTERVENE_CHOICE, REPORT_CHOICE
from world.mechanics.effect_handlers import apply_effect
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    ReactionWindowKind,
    ScenePrivacyMode,
)
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.models import InteractionFavorite, InteractionReaction, WindowReaction
from world.scenes.reaction_models import ReactionWindow
from world.scenes.reaction_services import react_to_window
from world.societies.factories import LegendSourceTypeFactory, SocietyFactory
from world.societies.models import LegendEntry, SocietyReputation


def _make_char_in_room(room: ObjectDB) -> ObjectDB:
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


def _wire_account(sheet):
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return tenure.player_data.account


class ReactionJourneyE2ETests(TestCase):
    """CmdReact drives the real reaction/favorite services end-to-end."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        self.room = ObjectDBFactory(
            db_key="ReactionE2ERoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)

        # Reactor
        self.reactor_char = _make_char_in_room(self.room)
        self.reactor_sheet = CharacterSheetFactory(character=self.reactor_char)
        self.reactor_account = _wire_account(self.reactor_sheet)
        self.reactor_char.db_account = self.reactor_account
        self.reactor_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.reactor_account)

        # Poser
        self.poser_char = _make_char_in_room(self.room)
        self.poser_sheet = CharacterSheetFactory(character=self.poser_char)
        self.poser_account = _wire_account(self.poser_sheet)
        self.poser_char.db_account = self.poser_account
        self.poser_char.save(update_fields=["db_account"])
        SceneParticipationFactory(scene=self.scene, account=self.poser_account)

        self.pose = InteractionFactory(
            scene=self.scene,
            persona=self.poser_sheet.primary_persona,
            mode=InteractionMode.POSE,
            visibility=InteractionVisibility.DEFAULT,
        )
        self.reactor_char.msg = MagicMock()

    def _run_cmd(self, args: str) -> MagicMock:
        cmd = CmdReact()
        cmd.caller = self.reactor_char
        cmd.args = args
        cmd.raw_string = f"react {args}"
        cmd.func()
        return self.reactor_char.msg

    def _output(self) -> str:
        return " ".join(str(c[0][0]) for c in self.reactor_char.msg.call_args_list if c[0])

    def test_favorite_toggle_on_then_off(self) -> None:
        self._run_cmd(f"favorite {self.poser_char.name} #1")
        self.assertEqual(InteractionFavorite.objects.count(), 1)
        self._run_cmd(f"favorite {self.poser_char.name} #1")
        self.assertEqual(InteractionFavorite.objects.count(), 0)

    def test_emoji_toggle(self) -> None:
        self._run_cmd(f"emoji {self.poser_char.name} #1 \U0001f389")
        self.assertEqual(InteractionReaction.objects.count(), 1)
        self.assertEqual(InteractionReaction.objects.get().emoji, "\U0001f389")

    def test_kudos_lazy_open(self) -> None:
        self._run_cmd(f"kudos {self.poser_char.name} #1")
        self.assertEqual(WindowReaction.objects.count(), 1)

    def test_react_no_active_scene_shows_error(self) -> None:
        empty_room = ObjectDBFactory(
            db_key="EmptyRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.reactor_char.location = empty_room
        self.reactor_char.save()
        self.reactor_char.msg.reset_mock()
        cmd = CmdReact()
        cmd.caller = self.reactor_char
        cmd.args = f"favorite {self.poser_char.name} #1"
        cmd.raw_string = "react ..."
        cmd.func()
        self.assertIn("scene", self._output().lower())


def _make_bystander(scene):
    """Account-backed persona present in ``scene`` (the full roster chain), the
    same fixture shape the reaction-kind tests use."""
    account = AccountFactory()
    character = CharacterFactory()
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    SceneParticipationFactory(scene=scene, account=account)
    character.db_account = account
    character.save()
    return roster_entry.character_sheet.primary_persona


class WitnessReportJourneyE2ETests(TestCase):
    """#2987 end to end, nothing mocked: an authored crime-tagged LEGEND_AWARD
    effect fires through the resolution pipeline with the scene interaction
    threaded in (the combat-aftermath shape), the minted deed is born
    crime-tagged, a WITNESS window opens on that interaction, a bystander
    reports, and the accused persona's heat and the enforcing society's regard
    both move by the law's weight. A second bystander's "intervene" changes
    nothing (justice stays NPC-driven; ADR-0032).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.theft = CrimeKindFactory(slug="journey-theft", name="Theft")
        AreaLawFactory(area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT)
        cls.source_type = LegendSourceTypeFactory()

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        profile = RoomProfileFactory(area=self.city, is_public=True)
        self.scene = SceneFactory(
            privacy_mode=ScenePrivacyMode.PUBLIC, location=profile.objectdb, is_active=True
        )
        self.actor = PersonaFactory()
        self.interaction = InteractionFactory(persona=self.actor, scene=self.scene)
        self.witness = _make_bystander(self.scene)
        # The authored seam: a LEGEND_AWARD effect a staff member tagged as theft.
        self.effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=10,
            legend_source_type=self.source_type,
            legend_description_template="A purse cut in the market square.",
        )
        self.effect.crime_kinds.add(self.theft)

    def _fire_the_effect(self):
        context = ResolutionContext(
            character=ObjectDBFactory(db_key="WitnessJourneyActor"),
            participants=[self.actor],
            scene=self.scene,
            interaction=self.interaction,
        )
        return apply_effect(self.effect, context)

    def test_tagged_award_opens_a_window_and_a_report_lands_heat_and_reputation(self) -> None:
        result = self._fire_the_effect()

        deed = LegendEntry.objects.get(event=result.created_instance, persona=self.actor)
        self.assertTrue(DeedCrimeTag.objects.filter(deed=deed, crime_kind=self.theft).exists())
        window = ReactionWindow.objects.get(
            interaction=self.interaction, kind=ReactionWindowKind.WITNESS
        )
        self.assertEqual(WitnessReactionTarget.objects.get(window=window).legend_entry_id, deed.pk)
        # Word of a crime-tagged deed already reaches the scene's witnesses at
        # birth (accrue_for_deed_knowledge, #1765): that is heat as word
        # spreads, and it carries no reputation sting. The report is the
        # second, distinct consequence on top of it.
        heat_at_birth = PersonaHeat.objects.get(persona=self.actor)
        self.assertEqual(heat_at_birth.area, self.city)
        self.assertFalse(SocietyReputation.objects.filter(persona=self.actor).exists())
        # Copy the number: the row is identity-mapped, so the report below
        # mutates this very instance.
        value_at_birth = heat_at_birth.value

        react_to_window(window=window, reactor_persona=self.witness, choice=REPORT_CHOICE)

        heat = PersonaHeat.objects.get(persona=self.actor)
        self.assertEqual(heat.value, value_at_birth + DEFAULT_HEAT_WEIGHT)
        regard = SocietyReputation.objects.get(persona=self.actor, society=self.crown)
        self.assertEqual(regard.value, -DEFAULT_HEAT_WEIGHT)

    def test_intervene_leaves_the_accused_untouched(self) -> None:
        self._fire_the_effect()
        window = ReactionWindow.objects.get(
            interaction=self.interaction, kind=ReactionWindowKind.WITNESS
        )

        heat_at_birth = PersonaHeat.objects.get(persona=self.actor).value

        react_to_window(window=window, reactor_persona=self.witness, choice=INTERVENE_CHOICE)

        self.assertEqual(WindowReaction.objects.filter(window=window).count(), 1)
        self.assertEqual(PersonaHeat.objects.get(persona=self.actor).value, heat_at_birth)
        self.assertFalse(SocietyReputation.objects.filter(persona=self.actor).exists())

    def test_untagged_award_opens_no_window(self) -> None:
        self.effect.crime_kinds.clear()

        self._fire_the_effect()

        self.assertFalse(
            ReactionWindow.objects.filter(
                interaction=self.interaction, kind=ReactionWindowKind.WITNESS
            ).exists()
        )
