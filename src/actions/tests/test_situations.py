"""Tests for SetSituationAction (#1895, JUNIOR gate #2117) and PlaceChallengeAction (#2865)."""

from django.test import TestCase
from evennia import create_object

from actions.definitions.situations import PlaceChallengeAction, SetSituationAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.mechanics.constants import DiscoveryType
from world.mechanics.factories import (
    ChallengeTemplateFactory,
    SituationTemplateFactory,
    SituationTrapLinkFactory,
)
from world.mechanics.models import ChallengeInstance, SituationInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import (
    DIFFICULTY_BAND_STEP,
    DIFFICULTY_VALUES,
    DifficultyChoice,
)


def _make_room(key: str = "The Solar") -> object:
    """Return a bare Evennia room -- characters need a real location."""
    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


class GMActorMixin:
    """Shared actor builders for the two GM placement actions."""

    def _staff_character(self) -> object:
        account = AccountFactory(is_staff=True)
        character = CharacterFactory(db_key="stager", location=_make_room("Stager's Room"))
        character.db_account = account
        return character

    def _nonstaff_character(self) -> object:
        account = AccountFactory(is_staff=False)
        character = CharacterFactory(db_key="onlooker", location=_make_room("Onlooker's Room"))
        character.db_account = account
        return character

    def _gm_character(self, level: str, *, db_key: str = "trust-gm") -> object:
        """Return a Character with a live roster tenure + GMProfile at ``level``."""
        character = CharacterFactory(db_key=db_key, location=_make_room(f"{db_key}'s Room"))
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        return character


class SetSituationActionTest(GMActorMixin, TestCase):
    def test_missing_template_id_fails(self) -> None:
        action = SetSituationAction()
        actor = self._staff_character()

        result = action.run(actor)

        assert result.success is False

    def test_unknown_template_id_fails(self) -> None:
        action = SetSituationAction()
        actor = self._staff_character()

        result = action.run(actor, situation_template_id=999999)

        assert result.success is False

    def test_staff_actor_instantiates_situation(self) -> None:
        action = SetSituationAction()
        actor = self._staff_character()
        template = SituationTemplateFactory()

        result = action.run(actor, situation_template_id=template.pk)

        assert result.success is True
        assert SituationInstance.objects.filter(
            template=template,
            location=actor.location,
        ).exists()

    def test_nonstaff_actor_is_blocked(self) -> None:
        action = SetSituationAction()
        actor = self._nonstaff_character()
        template = SituationTemplateFactory()

        result = action.run(actor, situation_template_id=template.pk)

        assert result.success is False
        assert SituationInstance.objects.filter(template=template).count() == 0

    def test_junior_gm_instantiates_situation(self) -> None:
        """A JUNIOR-tier GM (no staff flag) may setsituation (#2117)."""
        action = SetSituationAction()
        actor = self._gm_character(GMLevel.JUNIOR, db_key="junior-gm")
        template = SituationTemplateFactory()

        result = action.run(actor, situation_template_id=template.pk)

        assert result.success is True
        assert SituationInstance.objects.filter(
            template=template,
            location=actor.location,
        ).exists()

    def test_starting_gm_below_junior_tier_is_blocked(self) -> None:
        """A STARTING-tier GM is below the JUNIOR gate and is refused (#2117)."""
        action = SetSituationAction()
        actor = self._gm_character(GMLevel.STARTING, db_key="starting-gm")
        template = SituationTemplateFactory()

        result = action.run(actor, situation_template_id=template.pk)

        assert result.success is False
        assert "Junior GM" in result.message
        assert SituationInstance.objects.filter(template=template).count() == 0

    def test_missing_room_profile_with_trap_link_fails_cleanly(self) -> None:
        """A trap-link-bearing template in a room with no RoomProfile should fail
        cleanly (#1895 Finding 2), not raise ObjectDoesNotExist unhandled."""
        from unittest.mock import patch

        from django.core.exceptions import ObjectDoesNotExist

        action = SetSituationAction()
        account = AccountFactory(is_staff=True)
        bare_location = _make_room("No-Profile Room")
        actor = CharacterFactory(db_key="stager-no-profile", location=bare_location)
        actor.db_account = account
        template = SituationTemplateFactory()
        SituationTrapLinkFactory(situation_template=template)

        # Simulate the room having no RoomProfile by patching
        # instantiate_situation to raise ObjectDoesNotExist — the real
        # RoomProfile lookup is tested in world.mechanics, and the point of
        # this test is that SetSituationAction catches the error cleanly.
        with patch(
            "actions.definitions.situations.instantiate_situation",
            side_effect=ObjectDoesNotExist("location has no RoomProfile"),
        ):
            result = action.run(actor, situation_template_id=template.pk)

        assert result.success is False
        assert result.message
        assert SituationInstance.objects.filter(template=template).count() == 0


class PlaceChallengeActionTest(GMActorMixin, TestCase):
    """The lightweight one-off placement path (#2865)."""

    def test_missing_template_id_hints_at_the_catalog(self) -> None:
        result = PlaceChallengeAction().run(self._staff_character())

        assert result.success is False
        assert "setsituation find" in result.message

    def test_unknown_template_id_fails(self) -> None:
        result = PlaceChallengeAction().run(
            self._staff_character(),
            challenge_template_id=999999,
            target_object_name="the barred gate",
        )

        assert result.success is False
        assert ChallengeInstance.objects.count() == 0

    def test_missing_target_name_fails(self) -> None:
        template = ChallengeTemplateFactory()

        result = PlaceChallengeAction().run(
            self._staff_character(), challenge_template_id=template.pk
        )

        assert result.success is False
        assert ChallengeInstance.objects.count() == 0

    def test_junior_gm_places_a_standalone_challenge(self) -> None:
        actor = self._gm_character(GMLevel.JUNIOR, db_key="junior-placer")
        template = ChallengeTemplateFactory()

        result = PlaceChallengeAction().run(
            actor,
            challenge_template_id=template.pk,
            target_object_name="the barred gate",
        )

        assert result.success is True
        instance = ChallengeInstance.objects.get(template=template)
        assert instance.situation_instance is None
        assert instance.location == actor.location
        assert instance.target_object.db_key == "the barred gate"
        assert instance.is_active is True
        assert instance.severity_adjustment == 0
        assert instance.adjustment_reason == ""

    def test_starting_gm_below_junior_tier_is_blocked(self) -> None:
        actor = self._gm_character(GMLevel.STARTING, db_key="starting-placer")
        template = ChallengeTemplateFactory()

        result = PlaceChallengeAction().run(
            actor,
            challenge_template_id=template.pk,
            target_object_name="the barred gate",
        )

        assert result.success is False
        assert "Junior GM" in result.message
        assert ChallengeInstance.objects.count() == 0

    def test_staff_bypass_places(self) -> None:
        template = ChallengeTemplateFactory()

        result = PlaceChallengeAction().run(
            self._staff_character(),
            challenge_template_id=template.pk,
            target_object_name="the guttering brazier",
        )

        assert result.success is True
        assert ChallengeInstance.objects.filter(template=template).count() == 1

    def test_setback_persists_a_signed_adjustment_and_its_reason(self) -> None:
        actor = self._staff_character()
        template = ChallengeTemplateFactory(severity=DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

        result = PlaceChallengeAction().run(
            actor,
            challenge_template_id=template.pk,
            target_object_name="the barred gate",
            setback_reason="they braced it from the far side",
        )

        assert result.success is True
        instance = ChallengeInstance.objects.get(template=template)
        assert instance.severity_adjustment == DIFFICULTY_BAND_STEP
        assert instance.adjustment_reason == "they braced it from the far side"
        assert instance.effective_severity == DIFFICULTY_VALUES[DifficultyChoice.HARD]
        assert "setback" in result.message

    def test_edge_shifts_one_band_easier(self) -> None:
        actor = self._staff_character()
        template = ChallengeTemplateFactory(severity=DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

        result = PlaceChallengeAction().run(
            actor,
            challenge_template_id=template.pk,
            target_object_name="the barred gate",
            edge_reason="the hinges are already half-rusted",
        )

        assert result.success is True
        instance = ChallengeInstance.objects.get(template=template)
        assert instance.severity_adjustment == -DIFFICULTY_BAND_STEP
        assert instance.effective_severity == DIFFICULTY_VALUES[DifficultyChoice.EASY]

    def test_both_reasons_together_refuses(self) -> None:
        template = ChallengeTemplateFactory()

        result = PlaceChallengeAction().run(
            self._staff_character(),
            challenge_template_id=template.pk,
            target_object_name="the barred gate",
            edge_reason="rusted",
            setback_reason="braced",
        )

        assert result.success is False
        assert ChallengeInstance.objects.count() == 0

    def test_shift_past_the_hardest_band_refuses_rather_than_clamping(self) -> None:
        """Out of bounds refuses -- the catalog does not express "harder than Harrowing"."""
        template = ChallengeTemplateFactory(severity=DIFFICULTY_VALUES[DifficultyChoice.HARROWING])

        result = PlaceChallengeAction().run(
            self._staff_character(),
            challenge_template_id=template.pk,
            target_object_name="the sealed vault",
            setback_reason="and it is warded besides",
        )

        assert result.success is False
        assert "hardest band" in result.message
        assert ChallengeInstance.objects.count() == 0

    def test_discoverable_template_places_unrevealed(self) -> None:
        """The authored discovery type carries through -- a hidden beat stays hidden."""
        template = ChallengeTemplateFactory(discovery_type=DiscoveryType.DISCOVERABLE)

        result = PlaceChallengeAction().run(
            self._staff_character(),
            challenge_template_id=template.pk,
            target_object_name="the seam in the panelling",
        )

        assert result.success is True
        assert ChallengeInstance.objects.get(template=template).is_revealed is False
