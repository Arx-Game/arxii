"""The undelivered-interaction linter flags a ``create_interaction`` call with no
delivery-seam call in scope, and honours its suppression (#3807)."""

from lint_undelivered_interaction import check_source


def test_no_delivery_anywhere_is_flagged():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    return interaction\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(2, "create_interaction")]


def test_push_interaction_seam_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    push_interaction(interaction)\n"
    )
    assert check_source(source) == []


def test_deliver_outcome_interaction_seam_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    deliver_outcome_interaction(interaction, location=location)\n"
    )
    assert check_source(source) == []


def test_push_ephemeral_interaction_seam_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    push_ephemeral_interaction(persona=persona, content=content)\n"
    )
    assert check_source(source) == []


def test_send_to_objects_seam_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    _send_to_objects([character], payload)\n"
    )
    assert check_source(source) == []


def test_broadcast_to_location_seam_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    interaction = create_interaction(persona=persona, content=content)\n"
        "    _broadcast_to_location(room, payload)\n"
    )
    assert check_source(source) == []


def test_nested_closure_delivering_its_own_call_passes():
    source = (
        "def create_cast_outcome_pose(scene):\n"
        "    def _emit_tier(recipients, content):\n"
        "        tier_interaction = create_interaction(persona=narrator, content=content)\n"
        "        deliver_outcome_interaction(tier_interaction, location=location)\n"
        "    _emit_tier(audience.vague, text)\n"
    )
    assert check_source(source) == []


def test_enclosing_function_delivery_covers_a_nested_closure_call():
    source = (
        "def outer():\n"
        "    def _inner():\n"
        "        return create_interaction(persona=persona, content=content)\n"
        "    interaction = _inner()\n"
        "    push_interaction(interaction)\n"
    )
    assert check_source(source) == []


def test_nested_closure_call_with_no_delivery_anywhere_is_flagged():
    source = (
        "def outer():\n"
        "    def _inner():\n"
        "        return create_interaction(persona=persona, content=content)\n"
        "    return _inner()\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(3, "create_interaction")]


def test_attribute_call_spelling_is_flagged():
    source = (
        "def make_pose(service, persona, content):\n"
        "    return service.create_interaction(persona=persona, content=content)\n"
    )
    assert [(line, name) for line, _, name in check_source(source)] == [(2, "create_interaction")]


def test_attribute_call_delivery_seam_passes():
    source = (
        "def make_pose(service, persona, content):\n"
        "    interaction = service.create_interaction(persona=persona, content=content)\n"
        "    service.push_interaction(interaction)\n"
    )
    assert check_source(source) == []


def test_module_level_call_is_flagged():
    source = "interaction = create_interaction(persona=persona, content=content)\n"
    assert [(line, name) for line, _, name in check_source(source)] == [(1, "create_interaction")]


def test_suppressed_call_passes():
    source = (
        "def make_pose(persona, content):\n"
        "    return create_interaction(  # noqa: UNDELIVERED - caller delivers it\n"
        "        persona=persona, content=content\n"
        "    )\n"
    )
    assert check_source(source) == []


def test_create_interaction_definition_itself_is_not_flagged():
    source = (
        "def create_interaction(*, persona, content, mode=None, scene=None, **kwargs):\n"
        "    return Interaction.objects.create(persona=persona, content=content)\n"
    )
    assert check_source(source) == []
