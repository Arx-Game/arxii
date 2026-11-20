"""Every character-linked table is wiped, kept with a reason, or awaiting a ruling (#3055).

A new play-state model with a link to a character fails these tests until someone puts it
in one of the three places in ``world.beta_reset.classification``.
"""

from __future__ import annotations

from django.apps import apps
from django.test import SimpleTestCase

from world.beta_reset.classification import (
    KEPT_WITH_REASON,
    PROTECT_BLOCKERS_AWAITING_RULING,
    UNDECIDED_AWAITING_RULING,
    cascade_closure,
    classify_character_linked_models,
    protect_blockers,
)


class CharacterLinkedModelClassificationTests(SimpleTestCase):
    def test_every_character_linked_model_is_in_exactly_one_list(self) -> None:
        misplaced = {
            model.__name__: lists
            for model, lists in classify_character_linked_models().items()
            if len(lists) != 1
        }
        self.assertEqual(
            misplaced,
            {},
            "Each character-linked model must be wiped (SCOPE_TABLE or a cascade from it), in "
            "KEPT_WITH_REASON, or in UNDECIDED_AWAITING_RULING, and in only one of them.",
        )

    def test_listed_names_are_real_character_linked_models(self) -> None:
        linked = {model.__name__ for model in classify_character_linked_models()}
        real = {model.__name__ for model in apps.get_app_config("arxii").get_models()}
        for listed in (KEPT_WITH_REASON, UNDECIDED_AWAITING_RULING):
            self.assertEqual(set(listed) - real, set())
            self.assertEqual(set(listed) - linked, set())

    def test_a_kept_model_is_never_reached_by_the_wipe(self) -> None:
        reached = {model.__name__ for model in cascade_closure()}
        self.assertEqual(set(KEPT_WITH_REASON) & reached, set())

    def test_every_note_says_something(self) -> None:
        for listed in (KEPT_WITH_REASON, UNDECIDED_AWAITING_RULING):
            for name, note in listed.items():
                self.assertGreater(len(note), 20, name)


class WipeDeleteOrderTests(SimpleTestCase):
    def test_only_the_known_clue_blockers_can_stop_the_wipe(self) -> None:
        found = {
            (source.__name__, field, target.__name__)
            for source, field, target in protect_blockers()
        }
        self.assertEqual(
            found,
            set(PROTECT_BLOCKERS_AWAITING_RULING),
            "A PROTECT or RESTRICT foreign key points at a table the wipe deletes and the "
            "row holding it is not deleted first. Put the dependent table into SCOPE_TABLE "
            "ahead of its target, or list it in PROTECT_BLOCKERS_AWAITING_RULING with why.",
        )
