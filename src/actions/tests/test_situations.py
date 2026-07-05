"""Tests for SetSituationAction (#1895)."""

from django.test import TestCase
from evennia import create_object

from actions.definitions.situations import SetSituationAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.mechanics.factories import SituationTemplateFactory
from world.mechanics.models import SituationInstance


def _make_room(key: str = "The Solar") -> object:
    """Return a bare Evennia room -- characters need a real location."""
    return create_object("typeclasses.rooms.Room", key=key, nohome=True)


class SetSituationActionTest(TestCase):
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
