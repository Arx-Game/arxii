"""Tests for the singleton Narrator persona used to author combat outcomes."""

from __future__ import annotations

from django.test import TestCase

from world.combat.narrator import NARRATOR_PERSONA_NAME, get_or_create_narrator_persona
from world.scenes.models import Persona


class NarratorPersonaTest(TestCase):
    def test_creates_singleton_persona(self) -> None:
        persona = get_or_create_narrator_persona()
        assert persona.name == NARRATOR_PERSONA_NAME
        assert persona.pk is not None

    def test_returns_same_persona_on_second_call(self) -> None:
        first = get_or_create_narrator_persona()
        second = get_or_create_narrator_persona()
        assert first.pk == second.pk
        assert Persona.objects.filter(name=NARRATOR_PERSONA_NAME).count() == 1

    def test_narrator_is_flagged_system(self) -> None:
        persona = get_or_create_narrator_persona()
        assert persona.is_system is True

    def test_existing_narrator_healed_to_system(self) -> None:
        """A Narrator row predating is_system is healed to is_system=True."""
        persona = get_or_create_narrator_persona()
        Persona.objects.filter(pk=persona.pk).update(is_system=False)

        healed = get_or_create_narrator_persona()

        assert healed.pk == persona.pk
        assert healed.is_system is True
