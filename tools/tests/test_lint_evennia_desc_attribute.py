"""The Evennia-desc linter flags every use of the desc Attribute and honours a reasoned
suppression (#4329)."""

from lint_evennia_desc_attribute import check_source


def test_writing_db_desc_is_flagged():
    source = "def seed(room):\n    room.db.desc = 'A grey hall.'\n"
    assert check_source(source) == [(2, 4)]


def test_reading_and_deleting_db_desc_are_flagged():
    source = "text = room.db.desc or ''\ndel room.db.desc\n"
    assert [line for line, _ in check_source(source)] == [1, 2]


def test_attribute_handler_calls_are_flagged():
    source = (
        "room.attributes.get('desc')\n"
        "room.attributes.add('desc', 'text')\n"
        "room.attributes.remove('desc')\n"
        "room.attributes.has('desc')\n"
    )
    assert [line for line, _ in check_source(source)] == [1, 2, 3, 4]


def test_other_attributes_and_description_fields_pass():
    source = (
        "caller.db.evmenu_target = room\n"
        "room.attributes.get('locked')\n"
        "display.permanent_description = text\n"
        "state.description\n"
        "self.desc = text\n"
    )
    assert check_source(source) == []


def test_suppression_needs_a_reason():
    with_reason = "room.db.desc = x  # noqa: EVENNIA_DESC Evennia tutorial import\n"
    bare = "room.db.desc = x  # noqa: EVENNIA_DESC\n"
    assert check_source(with_reason) == []
    assert check_source(bare) == [(1, 0)]
