"""The live interaction push carries what the REST feed carries, bar a named allowlist.

#4418 real-testing bug I: ``InteractionListSerializer`` served ``action_links`` for a
long time while ``InteractionPayload`` (the live websocket frame) never had the key, so
only the poster, who renders the REST response to their own submit, saw a pose's attached
action. Nothing flagged the drift, because the websocket type is hand-written on both
ends. A field added to the REST serializer now has to be added to the push or named in
``REST_ONLY`` with the reason it is not pushed.
"""

from typing import get_type_hints

from django.test import SimpleTestCase

from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.types import InteractionPayload

_VIEWER = "depends on who is reading; the push is one frame for the whole room"

# REST fields the live frame deliberately does not carry, each with why.
REST_ONLY: dict[str, str] = {
    "is_favorited": _VIEWER,
    "my_pose_endorsement": _VIEWER,
    "entry_endorsed_by_me": _VIEWER,
    "is_muted": _VIEWER,
    "is_unread": _VIEWER,
    "scene": "the push names it as scene_id",
    "place": "the push names it as place_id",
    "attributed_companion": "the push names it as attributed_companion_id and _name",
}

# Push keys the REST feed spells differently, each with why.
PUSH_ONLY: dict[str, str] = {
    "scene_id": "REST serves the same value as scene",
    "place_id": "REST serves the same value as place",
    "attributed_companion_id": "REST serves the same value inside attributed_companion",
    "attributed_companion_name": "REST serves the same value inside attributed_companion",
}


class PushPayloadParityTests(SimpleTestCase):
    def test_push_and_rest_name_the_same_fields(self):
        rest = set(InteractionListSerializer.Meta.fields)
        push = set(get_type_hints(InteractionPayload))
        self.assertEqual(
            (sorted(rest - push - set(REST_ONLY)), sorted(push - rest - set(PUSH_ONLY))),
            ([], []),
            "Add the field to InteractionPayload/push_interaction, or name it in "
            "REST_ONLY / PUSH_ONLY with the reason.",
        )
