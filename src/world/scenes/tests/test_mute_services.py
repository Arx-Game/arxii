"""Mute resolution + toggle (#1278) — the lighter, one-way sibling of Block.

A mute only changes what the muter sees: ``muted_persona_ids_for_viewer`` lists the personas they
have IC-muted, and ``set_mute`` / ``unmute`` toggle it. No mutuality, no enforcement, fully
reversible.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.scenes.factories import PersonaFactory
from world.scenes.models import Mute
from world.scenes.mute_services import (
    muted_persona_ids_for_viewer,
    set_mute,
    unmute,
)


class MuteServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.muter_account = AccountFactory()
        cls.muter = PlayerData.objects.get_or_create(account=cls.muter_account)[0]
        cls.persona = PersonaFactory(name="Annoying Bard")
        cls.other = PersonaFactory(name="Someone Else")

    def test_no_mutes_lists_nothing(self) -> None:
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()

    def test_set_mute_hides_the_persona_for_the_muter_only(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona)
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == {self.persona.pk}
        # One-way: the muted persona's owner is unaffected (different viewer → nothing muted).
        assert muted_persona_ids_for_viewer(viewer_account=AccountFactory()) == set()

    def test_ic_only_mute_is_not_listed_for_the_ic_feed_when_ic_false(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona, ic=False, ooc=True)
        # The IC feed resolver only lists IC-muted personas.
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()

    def test_set_mute_is_idempotent_and_updates_scope(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona, ic=True, ooc=True)
        set_mute(owner=self.muter, muted_persona=self.persona, ic=True, ooc=False)
        mute = Mute.objects.get(owner=self.muter, muted_persona=self.persona)
        assert mute.mute_ooc is False
        assert Mute.objects.filter(owner=self.muter, muted_persona=self.persona).count() == 1

    def test_unmute_is_fully_reversible(self) -> None:
        set_mute(owner=self.muter, muted_persona=self.persona)
        unmute(owner=self.muter, muted_persona=self.persona)
        assert muted_persona_ids_for_viewer(viewer_account=self.muter_account) == set()
        assert not Mute.objects.filter(owner=self.muter).exists()
