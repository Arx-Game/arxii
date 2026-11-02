"""Every magic route that can create, update or delete keeps a player out of it (#4898).

#4898 found five magic viewsets (character-gifts, the gift catalog, character-anima,
character-resonances, character-auras) whose router writes any signed-in player could use:
a player could give themselves any gift or refill their anima. This walks every viewset the
magic router registers and asks, for each base write it serves (create, update, partial
update, destroy), whether a plain signed-in non-staff account passes its permission
classes. One that does must be on ``PLAYER_WRITABLE`` with the reason a player may write it.
The ``player-writable-endpoint-reviewer`` agent is the review half of this check.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase
from rest_framework import mixins
from rest_framework.request import Request

from evennia_extensions.factories import AccountFactory
from world.magic.urls import router

#: action -> (the mixin that serves it, the HTTP method it answers)
_WRITES = {
    "create": (mixins.CreateModelMixin, "post"),
    "update": (mixins.UpdateModelMixin, "put"),
    "partial_update": (mixins.UpdateModelMixin, "patch"),
    "destroy": (mixins.DestroyModelMixin, "delete"),
}

#: Viewset name -> why a player may use its base writes. Each one gates the row some other
#: way (an object-level owner check, a validating serializer) and the web client writes it.
PLAYER_WRITABLE: dict[str, str] = {
    "ThreadViewSet": (
        "A player weaves and retires their own threads (frontend/src/magic/api.ts:467): "
        "IsThreadOwner on the row, and the write serializer resolves character_sheet_id "
        "against the requester (_resolve_account_sheet)."
    ),
    "RitualViewSet": (
        "PATCH only (http_method_names), gated per row by IsRitualAuthorOrStaff: an author "
        "edits their own ritual."
    ),
    "PoseEndorsementViewSet": (
        "perform_create goes through create_pose_endorsement, which checks the endorser; "
        "destroy refuses a settled endorsement. The web EndorsementControl writes it."
    ),
    "SceneEntryEndorsementViewSet": (
        "perform_create goes through create_scene_entry_endorsement, which checks the "
        "endorser and the scene."
    ),
    "StylePresentationEndorsementViewSet": (
        "perform_create goes through create_style_presentation_endorsement, which checks the "
        "endorser."
    ),
    "DramaticMomentTagViewSet": (
        "perform_create refuses anyone but the scene's GM, owner or staff "
        "(IsSceneGMOrOwnerOrStaff) and tags through create_dramatic_moment_tag."
    ),
    "PreparedCrossingTextViewSet": (
        "Staff or the character's table GM (CanPrepareCharacterText on the row, "
        "may_prepare_text_for in the serializer's validate_character_sheet)."
    ),
    "PreparedSurgeTextViewSet": (
        "Staff or the character's table GM, as PreparedCrossingTextViewSet."
    ),
}


def _served_writes(viewset: type) -> list[tuple[str, str]]:
    allowed = {name.lower() for name in viewset.http_method_names}
    return [
        (action, method)
        for action, (mixin, method) in _WRITES.items()
        if issubclass(viewset, mixin) and method in allowed
    ]


def _player_passes(viewset: type, action: str, method: str, player: object) -> bool:
    raw = getattr(RequestFactory(), method)("/")
    raw.user = player
    request = Request(raw)
    request.user = player
    view = viewset()
    view.action = action
    view.request = request
    view.format_kwarg = None
    return all(p.has_permission(request, view) for p in view.get_permissions())


class MagicRouterWritesAreStaffOnly(TestCase):
    maxDiff = None

    def test_no_player_reaches_a_base_write_unless_allowlisted(self) -> None:
        player = AccountFactory()
        open_writes = []
        for prefix, viewset, _basename in router.registry:
            if viewset.__name__ in PLAYER_WRITABLE:
                continue
            for action, method in _served_writes(viewset):
                if _player_passes(viewset, action, method, player):
                    open_writes.append(f"{prefix} ({viewset.__name__}).{action}")

        self.assertEqual(open_writes, [], "Player-writable magic routes; gate or allowlist.")

    def test_the_allowlist_names_only_registered_viewsets(self) -> None:
        names = {viewset.__name__ for _prefix, viewset, _basename in router.registry}

        self.assertEqual(set(PLAYER_WRITABLE) - names, set())
