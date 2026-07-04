"""Serializers for the boundaries API (#1771 task 6, privacy-critical).

Every serializer here is either (a) an owner-only CRUD shape for
``PlayerBoundary``/``TreasuredSubject`` — mounted behind an owner-scoped
queryset so a non-owner request never reaches these fields for someone
else's row — or (b) a read-only wire shape over an already-ANONYMIZED value
object produced by ``world.boundaries.services`` (``SharedAdvisoryBoundary``,
``SharedTreasuredSubject``, ``SceneLinesAndVeils``). None of these carry an
owner-identifying field, and none carry a hard-line row (the service layer
never queries ``kind=HARD_LINE`` when building them — see
``world.boundaries.services.scene_lines_and_veils``).

``blocked_reason_private`` (from ``world.stories.types.StakeBoundaryReport``)
does not appear in any serializer in this module or in
``world.stories.serializers``' ``StakeAvailabilitySerializer`` — see that
module for the GM-availability read (ADR-0033).
"""

from __future__ import annotations

from rest_framework import serializers

from world.boundaries.constants import BoundaryKind
from world.boundaries.models import ContentTheme, PlayerBoundary, TreasuredSubject


class ContentThemeSerializer(serializers.ModelSerializer):
    """Read-only serializer for the staff-authored content theme catalog."""

    class Meta:
        model = ContentTheme
        fields = ("id", "key", "name", "description", "display_order", "is_active")
        read_only_fields = fields


class PlayerBoundarySerializer(serializers.ModelSerializer):
    """Owner-authored ``PlayerBoundary`` CRUD shape.

    ``owner`` is never client-writable — the viewset sets it from the
    requesting player's own ``PlayerData`` on create, so a player can never
    author a boundary for anyone else. Mounted behind an owner-scoped
    queryset (see ``PlayerBoundaryViewSet.get_queryset``), so this serializer
    is only ever handed rows the requester already owns; there is no
    non-owner read path through this class.
    """

    class Meta:
        model = PlayerBoundary
        fields = (
            "id",
            "owner",
            "kind",
            "theme",
            "detail",
            "visibility_mode",
            "visible_to_tenures",
            "visible_to_groups",
            "excluded_tenures",
            "created_at",
        )
        read_only_fields = ("id", "owner", "created_at")

    def validate(self, attrs: dict) -> dict:
        """Mirror ``PlayerBoundary.clean()``'s hard-line invariant (ADR-0033).

        A hard line must name a theme and stay PRIVATE — duplicated here
        (rather than relying on ``instance.clean()``) because the instance
        doesn't exist yet at validation time for creates, and m2m fields
        (``visible_to_tenures`` etc.) aren't settable on an unsaved instance.
        """
        instance = self.instance
        default_visibility = PlayerBoundary.VisibilityMode.PRIVATE
        instance_kind = instance.kind if instance is not None else None
        instance_theme = instance.theme if instance is not None else None
        instance_visibility = (
            instance.visibility_mode if instance is not None else default_visibility
        )
        kind = attrs.get("kind", instance_kind)
        theme = attrs.get("theme", instance_theme)
        visibility_mode = attrs.get("visibility_mode", instance_visibility)
        if kind == BoundaryKind.HARD_LINE:
            if theme is None:
                raise serializers.ValidationError(
                    {"theme": "A hard line must name a content theme."}
                )
            if visibility_mode != PlayerBoundary.VisibilityMode.PRIVATE:
                raise serializers.ValidationError(
                    {"visibility_mode": "Hard lines are always private and cannot be shared."}
                )
        return attrs


class TreasuredSubjectSerializer(serializers.ModelSerializer):
    """Owner-authored ``TreasuredSubject`` CRUD shape.

    ``owner`` (a ``RosterTenure``) IS client-writable — a player may have
    several tenures (characters) — but ``validate()`` rejects any tenure not
    belonging to the requesting player, mirroring
    ``world.consent.serializers``' ``owner_tenure`` validation pattern.
    """

    class Meta:
        model = TreasuredSubject
        fields = (
            "id",
            "owner",
            "subject_kind",
            "subject_sheet",
            "subject_item",
            "subject_society",
            "subject_organization",
            "subject_label",
            "detail",
            "visibility_mode",
            "visible_to_tenures",
            "visible_to_groups",
            "excluded_tenures",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate(self, attrs: dict) -> dict:
        """Ensure ``owner`` (the tenure) belongs to the requesting player."""
        request = self.context.get("request")
        is_create = self.instance is None
        owner = attrs.get("owner")
        if is_create and owner is None:
            raise serializers.ValidationError(
                {"owner": "owner is required when creating a treasured subject."}
            )
        if request is not None and hasattr(request.user, "player_data") and owner is not None:
            player_data = request.user.player_data
            if owner.player_data_id != player_data.pk:
                raise serializers.ValidationError(
                    {"owner": "You may only manage treasured subjects for your own tenures."}
                )
        return attrs


class SharedAdvisoryBoundarySerializer(serializers.Serializer):
    """Read-only wire shape for ``world.boundaries.types.SharedAdvisoryBoundary``.

    Anonymized by construction — no owner field exists to leak.
    """

    theme_name = serializers.CharField(read_only=True)
    detail = serializers.CharField(read_only=True)


class SharedTreasuredSubjectSerializer(serializers.Serializer):
    """Read-only wire shape for ``world.boundaries.types.SharedTreasuredSubject``."""

    subject_kind = serializers.CharField(read_only=True)
    subject_label = serializers.CharField(read_only=True)
    detail = serializers.CharField(read_only=True)


class SceneLinesAndVeilsSerializer(serializers.Serializer):
    """Read-only wire shape for ``world.boundaries.types.SceneLinesAndVeils``.

    Built by ``SceneLinesAndVeilsView`` from ``scene_lines_and_veils`` — the
    already-anonymized, hard-line-free scene aggregate.
    """

    advisories = SharedAdvisoryBoundarySerializer(many=True, read_only=True)
    treasured_subjects = SharedTreasuredSubjectSerializer(many=True, read_only=True)
