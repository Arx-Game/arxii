"""DRF serializers for the boards API (#3286)."""

from __future__ import annotations

from rest_framework import serializers

from world.boards.models import Board, BoardPost


class BoardSerializer(serializers.ModelSerializer):
    is_location_board = serializers.BooleanField(read_only=True)
    is_org_board = serializers.BooleanField(read_only=True)

    class Meta:
        model = Board
        fields = [
            "id",
            "room_profile",
            "organization",
            "name",
            "max_active_posts",
            "is_location_board",
            "is_org_board",
        ]


class BoardPostSerializer(serializers.ModelSerializer):
    """Read-only board post — writes go through action dispatch (ADR-0001).

    ``author_display`` renders through the same per-viewer persona display
    resolution as everywhere else (a masked poster shows the mask; a
    discovered mask reveals; staff sees through every mask).
    """

    author_display = serializers.SerializerMethodField()
    is_removed = serializers.BooleanField(read_only=True)

    class Meta:
        model = BoardPost
        fields = [
            "id",
            "board",
            "title",
            "body",
            "author_display",
            "created_at",
            "edited_at",
            "is_removed",
        ]

    def get_author_display(self, obj: BoardPost) -> str:
        from world.scenes.persona_display import (  # noqa: PLC0415
            resolve_display_for_viewer,
            viewer_context_for_account,
        )

        request = self.context.get("request")
        user = request.user if request is not None else None
        viewer_persona_ids: set[int] = set()
        viewer_sheet_ids: set[int] = set()
        is_staff = False
        if user is not None and user.is_authenticated:
            viewer_persona_ids, viewer_sheet_ids = viewer_context_for_account(user)
            is_staff = bool(user.is_staff)
        name, _ = resolve_display_for_viewer(
            obj.author_persona,
            viewer_persona_ids=viewer_persona_ids,
            viewer_sheet_ids=viewer_sheet_ids,
            is_staff=is_staff,
        )
        return name
