"""Tests for ExitProfile (#2175)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.constants import ExitKind
from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ExitProfile


class ExitProfileTests(TestCase):
    def test_get_or_create_defaults_to_door(self):
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        assert profile.exit_kind == ExitKind.DOOR
        assert profile.is_open is False

    def test_get_or_create_returns_existing_row(self):
        exit_obj = ObjectDBFactory(db_key="south", db_typeclass_path="typeclasses.exits.Exit")
        profile = ExitProfile.objects.create(
            objectdb=exit_obj, exit_kind=ExitKind.WINDOW, is_open=True
        )
        fetched = ExitProfile.get_or_create_for_exit(exit_obj)
        assert fetched.pk == profile.pk
        assert fetched.exit_kind == ExitKind.WINDOW
        assert fetched.is_open is True

    def test_str_includes_key_and_kind(self):
        exit_obj = ObjectDBFactory(db_key="win", db_typeclass_path="typeclasses.exits.Exit")
        profile = ExitProfile.objects.create(objectdb=exit_obj, exit_kind=ExitKind.WINDOW)
        assert "win" in str(profile)
        assert "window" in str(profile)
