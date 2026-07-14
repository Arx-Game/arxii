"""Test-infra guarantee (#1825 CI): DbHolder never breaks setUpTestData deepcopy.

Django's TestData descriptor deep-copies every setUpTestData attribute on first
per-test access, descending cached FK chains (sheet → character, deed → scene →
location). Evennia stashes a ``DbHolder`` on any typeclassed object whose ``.db`` /
``.ndb`` was touched, and DbHolder is un-deepcopyable — so any fixture whose object
graph reaches a touched ObjectDB explodes, shard-order dependently. The test-settings
shim gives DbHolder a share-on-deepcopy ``__deepcopy__`` (the holder is a lazy accessor
namespace; sharing it mirrors how the identity map already shares the instance itself).
"""

import copy

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory


class DbHolderDeepcopySafetyTests(TestCase):
    def test_character_with_touched_db_is_deepcopyable(self):
        from evennia.typeclasses.attributes import DbHolder

        character = CharacterSheetFactory().character
        character.db.some_flag = True  # stash the DbHolder on the instance
        assert any(isinstance(value, DbHolder) for value in vars(character).values())
        clone = copy.deepcopy(character)
        assert clone.pk == character.pk

    def test_fk_chain_reaching_a_touched_object_is_deepcopyable(self):
        sheet = CharacterSheetFactory()
        sheet.character.db.some_flag = True
        clone = copy.deepcopy(sheet)  # descends sheet → character → DbHolder
        assert clone.pk == sheet.pk
