"""The item-deletes linter flags a game object or ItemInstance delete outside the usage
helpers and honours a reasoned suppression (#4474)."""

from pathlib import Path

from lint_item_deletes import check_file, check_source


def test_deleting_an_items_game_object_is_flagged():
    source = "def deposit(item):\n    item.game_object.delete()\n"
    assert check_source(source) == [(2, 4)]


def test_deleting_a_local_named_game_object_is_flagged():
    source = "game_object = instance.game_object\ngame_object.delete()\n"
    assert check_source(source) == [(2, 0)]


def test_item_instance_queryset_delete_is_flagged():
    source = "ItemInstance.objects.filter(pk=1).delete()\n"
    assert check_source(source) == [(1, 0)]


def test_other_deletes_pass():
    source = (
        "condition.delete()\n"
        "holding.delete()\n"
        "Persona.objects.filter(pk=1).delete()\n"
        "obj.delete()\n"
    )
    assert check_source(source) == []


def test_a_reasoned_suppression_passes_and_a_bare_one_does_not():
    reasoned = "room.game_object.delete()  # noqa: ITEM_DELETE a room, not an item\n"
    bare = "room.game_object.delete()  # noqa: ITEM_DELETE\n"
    assert check_source(reasoned) == []
    assert check_source(bare) == [(1, 0)]


def test_the_canonical_module_is_exempt(tmp_path: Path):
    canonical = tmp_path / "world" / "items" / "services" / "usage.py"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("item.game_object.delete()\n")
    other = tmp_path / "world" / "items" / "services" / "other.py"
    other.write_text("item.game_object.delete()\n")
    assert check_file(canonical) == []
    assert check_file(other) == [(1, 0)]
