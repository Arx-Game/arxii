"""Serializers for the GM system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import serializers

if TYPE_CHECKING:
    from world.projects.models import Project

from world.areas.serializers import WorldBuilderAreaManagerSerializer, WorldBuilderRoomSerializer
from world.gm.constants import (
    GMApplicationStatus,
    GMLevel,
    GMTableViewerRole,
    TableRequestKind,
)
from world.gm.models import (
    CatalogSuggestion,
    DistinctionChangeRequestDetails,
    GMApplication,
    GMLevelChange,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    ProfileTextRequestDetails,
    StoryRoomGrant,
    TableUpdateRequest,
)
from world.instances.models import InstancedRoom
from world.roster.models.applications import RosterApplication


class GMApplicationCreateSerializer(serializers.ModelSerializer):
    """For players submitting a GM application."""

    application_text = serializers.CharField(
        min_length=50,
        max_length=10000,
        allow_blank=False,
    )

    class Meta:
        model = GMApplication
        fields = ["application_text"]

    def validate(self, attrs: dict) -> dict:
        account = self.context["request"].user
        if GMProfile.objects.filter(account=account).exists():
            msg = "This account is already an approved GM."
            raise serializers.ValidationError(msg)
        if GMApplication.objects.filter(
            account=account,
            status=GMApplicationStatus.PENDING,
        ).exists():
            msg = "You already have a pending GM application."
            raise serializers.ValidationError(msg)
        return attrs

    def create(self, validated_data: dict) -> GMApplication:
        validated_data["account"] = self.context["request"].user
        return super().create(validated_data)


class GMApplicationDetailSerializer(serializers.ModelSerializer):
    """For staff reviewing GM applications."""

    account_username = serializers.CharField(source="account.username", read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = GMApplication
        fields = [
            "id",
            "account",
            "account_username",
            "application_text",
            "staff_response",
            "status",
            "created_at",
            "updated_at",
            "reviewed_by",
            "reviewed_by_username",
        ]
        read_only_fields = ["id", "account", "created_at", "updated_at", "reviewed_by"]


class CatalogSuggestionDetailSerializer(serializers.ModelSerializer):
    """For staff triaging GM scenario-catalog suggestions (#2127).

    No create serializer — creation only happens through
    ``SubmitCatalogSuggestionAction`` (the generic REGISTRY dispatch seam both
    telnet and web use), never a direct DRF POST.
    """

    submitted_by_username = serializers.CharField(source="submitted_by.username", read_only=True)
    situation_kind_name = serializers.CharField(
        source="situation_kind.name", read_only=True, allow_null=True
    )
    reviewer_username = serializers.CharField(
        source="reviewer.username", read_only=True, allow_null=True
    )

    class Meta:
        model = CatalogSuggestion
        fields = [
            "id",
            "submitted_by",
            "submitted_by_username",
            "situation_kind",
            "situation_kind_name",
            "proposal_kind",
            "proposal_text",
            "status",
            "reviewer",
            "reviewer_username",
            "review_notes",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = [
            "id",
            "submitted_by",
            "situation_kind",
            "proposal_kind",
            "proposal_text",
            "reviewer",
            "created_at",
        ]


class GMProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for GM profiles."""

    account_username = serializers.CharField(source="account.username", read_only=True)
    level_display = serializers.CharField(source="get_level_display", read_only=True)

    class Meta:
        model = GMProfile
        fields = [
            "id",
            "account",
            "account_username",
            "level",
            "level_display",
            "approved_at",
        ]
        read_only_fields = fields


class GMLevelChangeSerializer(serializers.ModelSerializer):
    """Read-only audit row for a staff-driven GM trust-level change (#2000)."""

    changed_by_username = serializers.CharField(source="changed_by.username", read_only=True)
    old_level_display = serializers.CharField(source="get_old_level_display", read_only=True)
    new_level_display = serializers.CharField(source="get_new_level_display", read_only=True)

    class Meta:
        model = GMLevelChange
        fields = [
            "id",
            "profile",
            "old_level",
            "old_level_display",
            "new_level",
            "new_level_display",
            "changed_by",
            "changed_by_username",
            "reason",
            "created_at",
        ]
        read_only_fields = fields


class CategoryFeedbackSerializer(serializers.Serializer):
    """One trust category's aggregated feedback ratings for a GM (read-only)."""

    category_name = serializers.CharField()
    average_rating = serializers.FloatField()
    rating_count = serializers.IntegerField()


class GMEvidenceSummarySerializer(serializers.Serializer):
    """Read-only view of ``world.gm.types.GMEvidenceSummary`` for staff review (#2000)."""

    profile_id = serializers.IntegerField()
    level = serializers.ChoiceField(choices=GMLevel.choices)
    approved_at = serializers.DateTimeField()
    last_active_at = serializers.DateTimeField(allow_null=True)
    stories_running = serializers.IntegerField()
    beats_completed_by_risk = serializers.DictField(child=serializers.IntegerField())
    feedback_by_category = CategoryFeedbackSerializer(many=True)
    level_changes = GMLevelChangeSerializer(many=True)


class PromoteGMInputSerializer(serializers.Serializer):
    """Validate a staff-driven promotion/demotion before it reaches ``promote_gm`` (#2000).

    ``context["profile"]`` is the ``GMProfile`` being changed — the view passes
    ``self.get_object()``. Rejecting the same-level case here means
    ``promote_gm``'s ``ValueError`` guard is a programmer-error backstop only and
    should never fire from user input.
    """

    new_level = serializers.ChoiceField(choices=GMLevel.choices)
    reason = serializers.CharField(required=True, allow_blank=False)

    def validate(self, attrs: dict) -> dict:
        profile = self.context["profile"]
        if attrs["new_level"] == profile.level:
            msg = "This GM is already at that level."
            raise serializers.ValidationError({"new_level": msg})
        return attrs


class GMTableSerializer(serializers.ModelSerializer):
    """Serializer for GM tables.

    Computed read-only fields:
    - member_count: active memberships (left_at__isnull=True)
    - story_count: stories with primary_table=this table
    - viewer_role: "gm" / "staff" / "member" / "guest" / "none" derived from
      request.user vs. table.gm.account and membership/participation lookups
    """

    gm_username = serializers.CharField(source="gm.account.username", read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    story_count = serializers.IntegerField(read_only=True)
    viewer_role = serializers.SerializerMethodField()

    class Meta:
        model = GMTable
        fields = [
            "id",
            "gm",
            "gm_username",
            "name",
            "description",
            "status",
            "created_at",
            "archived_at",
            "member_count",
            "story_count",
            "viewer_role",
        ]
        read_only_fields = [
            "id",
            "gm_username",
            "created_at",
            "archived_at",
            "status",
            "member_count",
            "story_count",
            "viewer_role",
        ]

    def get_viewer_role(self, table: GMTable) -> str:
        """Return the requesting user's role relative to this table.

        Priority: gm > staff > member > guest > none.
        "guest" means the user participates in a story at this table via
        StoryParticipation but has no active GMTableMembership.

        Membership and story-participation lookups read from sets pre-computed
        once per request in ``GMTableViewSet.get_serializer_context``. When
        the serializer is invoked outside a viewset (e.g. directly in tests)
        the sets fall back to lazy ``.exists()`` queries — keeps the test
        ergonomics while letting the viewset path stay query-free per-row.
        """
        from world.stories.models import StoryParticipation  # noqa: PLC0415

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return GMTableViewerRole.NONE
        user = request.user
        # GM owner of this table.
        if table.gm.account_id == user.pk:
            return GMTableViewerRole.GM
        # Staff (but not the table's GM, already handled above).
        if user.is_staff:
            return GMTableViewerRole.STAFF
        # Active table member via any persona.
        # Chain: GMTableMembership.persona → Persona.character_sheet
        #        → CharacterSheet.character (ObjectDB) → ObjectDB.db_account
        viewer_member_table_ids = self.context.get("viewer_member_table_ids")
        if viewer_member_table_ids is not None:
            is_member = table.id in viewer_member_table_ids
        else:
            is_member = table.memberships.filter(
                persona__character_sheet__character__db_account=user,
                left_at__isnull=True,
            ).exists()
        if is_member:
            return GMTableViewerRole.MEMBER
        # Guest: participates in a story at this table but is not a member.
        viewer_story_participant_table_ids = self.context.get("viewer_story_participant_table_ids")
        if viewer_story_participant_table_ids is not None:
            is_guest = table.id in viewer_story_participant_table_ids
        else:
            is_guest = StoryParticipation.objects.filter(
                story__primary_table=table,
                character__db_account=user,
                is_active=True,
            ).exists()
        if is_guest:
            return GMTableViewerRole.GUEST
        return GMTableViewerRole.NONE


class GMTableMembershipSerializer(serializers.ModelSerializer):
    """Serializer for persona memberships at GM tables."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = GMTableMembership
        fields = ["id", "table", "persona", "persona_name", "joined_at", "left_at"]
        read_only_fields = ["id", "persona_name", "joined_at", "left_at"]


class GMRosterInviteSerializer(serializers.ModelSerializer):
    """For GM create/list operations on invites for their own characters."""

    claimed_username = serializers.CharField(
        source="claimed_by.username",
        read_only=True,
        allow_null=True,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    invited_email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = GMRosterInvite
        fields = [
            "id",
            "roster_entry",
            "code",
            "created_by",
            "created_at",
            "expires_at",
            "is_public",
            "invited_email",
            "claimed_at",
            "claimed_by",
            "claimed_username",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "created_at",
            "claimed_at",
            "claimed_by",
            "claimed_username",
        ]

    def validate(self, attrs: dict) -> dict:
        """GM must oversee the roster_entry's character at an active table."""
        from world.gm.constants import GMTableStatus  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415

        request = self.context.get("request")
        if request is None or not hasattr(request.user, "gm_profile"):
            msg = "GM profile required."
            raise serializers.ValidationError(msg)

        gm = request.user.gm_profile
        roster_entry = attrs["roster_entry"]
        oversees = RosterEntry.objects.filter(
            pk=roster_entry.pk,
            character_sheet__character__story_participations__is_active=True,
            character_sheet__character__story_participations__story__primary_table__gm=gm,
            character_sheet__character__story_participations__story__primary_table__status=(
                GMTableStatus.ACTIVE
            ),
        ).exists()
        if not oversees:
            raise serializers.ValidationError(
                {"roster_entry": "You do not oversee this character."},
            )
        return attrs

    def create(self, validated_data: dict) -> GMRosterInvite:
        """Delegate to the service. Validation already ran in ``validate()``."""
        from world.gm.services import create_invite  # noqa: PLC0415

        request = self.context["request"]
        return create_invite(
            gm=request.user.gm_profile,
            roster_entry=validated_data["roster_entry"],
            is_public=validated_data.get("is_public", False),
            invited_email=validated_data.get("invited_email", "").strip(),
            expires_at=validated_data.get("expires_at"),
        )


class GMInviteRevokeSerializer(serializers.Serializer):
    """Validate that the current GM (or staff) can revoke this invite."""

    def validate(self, attrs: dict) -> dict:
        invite = self.instance
        if invite.is_claimed:
            msg = "Claimed invites cannot be revoked."
            raise serializers.ValidationError(msg)
        request = self.context["request"]
        if request.user.is_staff:
            return attrs
        if invite.created_by.account != request.user:
            msg = "You did not create this invite."
            raise serializers.ValidationError(msg)
        return attrs

    def save(self, **kwargs: object) -> GMRosterInvite:  # noqa: ARG002
        from world.gm.services import revoke_invite  # noqa: PLC0415

        revoke_invite(self.instance)
        return self.instance


class GMInviteClaimSerializer(serializers.Serializer):
    """Claim a GM invite by code."""

    code = serializers.CharField(max_length=64)

    def validate_code(self, value: str) -> str:
        try:
            invite = GMRosterInvite.objects.select_for_update().get(code=value)
        except GMRosterInvite.DoesNotExist as exc:
            msg = "Invalid invite code."
            raise serializers.ValidationError(msg) from exc
        if invite.is_claimed:
            msg = "This invite has already been claimed."
            raise serializers.ValidationError(msg)
        if invite.is_expired:
            msg = "This invite has expired."
            raise serializers.ValidationError(msg)
        self.context["invite"] = invite
        return value

    def validate(self, attrs: dict) -> dict:
        from evennia_extensions.models import PlayerData  # noqa: PLC0415
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        invite = self.context["invite"]
        request = self.context["request"]
        account = request.user
        if not invite.is_public and invite.invited_email:
            invited = invite.invited_email.strip().lower()
            account_email = (account.email or "").strip().lower()
            if not account_email or invited != account_email:
                msg = "This invite is private and does not match your account email."
                raise serializers.ValidationError(msg)

        # Reject if a finalized (non-pending) application already exists for
        # this (player_data, character). The service will reuse a PENDING one.
        try:
            player_data = PlayerData.objects.get(account=account)
        except PlayerData.DoesNotExist:
            player_data = None
        if player_data is not None:
            character = invite.roster_entry.character_sheet.character
            existing = RosterApplication.objects.filter(
                player_data=player_data,
                character=character,
            ).first()
            if existing is not None and existing.status != ApplicationStatus.PENDING:
                msg = (
                    "You already have a finalized application for this character. "
                    "Contact staff if you want to re-apply."
                )
                raise serializers.ValidationError(msg)
        return attrs

    def save(self, **kwargs: object) -> RosterApplication:  # noqa: ARG002
        from world.gm.services import claim_invite  # noqa: PLC0415

        invite: GMRosterInvite = self.context["invite"]
        account = self.context["request"].user
        return claim_invite(invite=invite, account=account)


class GMApplicationActionSerializer(serializers.Serializer):
    """Validate that the current GM can approve/deny the application."""

    APPROVE = "approve"
    DENY = "deny"

    action = serializers.ChoiceField(choices=[APPROVE, DENY])
    review_notes = serializers.CharField(required=False, default="", allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        from world.gm.services import gm_application_queue  # noqa: PLC0415
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        request = self.context["request"]
        application: RosterApplication = self.context["application"]
        gm = request.user.gm_profile

        if not gm_application_queue(gm).filter(pk=application.pk).exists():
            msg = "This application is not in your GM application queue."
            raise serializers.ValidationError(msg)

        # Bypass SMM identity map via values_list and acquire row lock.
        locked_status = (
            RosterApplication.objects.select_for_update()
            .filter(pk=application.pk)
            .values_list("status", flat=True)
            .first()
        )
        if locked_status != ApplicationStatus.PENDING:
            msg = "This application has already been processed."
            raise serializers.ValidationError(msg)
        application.refresh_from_db(fields=["status"])
        return attrs

    def save(self, **kwargs: object) -> RosterApplication:  # noqa: ARG002
        from world.gm.services import (  # noqa: PLC0415
            approve_application_as_gm,
            deny_application_as_gm,
        )

        application: RosterApplication = self.context["application"]
        gm = self.context["request"].user.gm_profile
        action = self.validated_data["action"]
        notes = self.validated_data.get("review_notes", "")

        if action == self.APPROVE:
            approve_application_as_gm(gm, application)
        else:
            deny_application_as_gm(gm, application, review_notes=notes)
        return application


class GMApplicationQueueSerializer(serializers.ModelSerializer):
    """Pending application surfaced to the overseeing GM."""

    character_key = serializers.CharField(source="character.db_key", read_only=True)
    applicant_username = serializers.CharField(
        source="player_data.account.username",
        read_only=True,
    )

    class Meta:
        model = RosterApplication
        fields = [
            "id",
            "character",
            "character_key",
            "applicant_username",
            "status",
            "applied_date",
            "application_text",
        ]
        read_only_fields = fields


class DemandRansomSerializer(serializers.Serializer):
    """Validate + execute a GM ransom demand for a held captive (#1500).

    ``captivity_id`` must point at a currently-held captivity; ``amount`` (coppers)
    is optional and falls through to the captor's default demand. ``save`` raises
    the crowdfundable RANSOM project via ``demand_ransom_project`` and returns it.
    """

    captivity_id = serializers.IntegerField()
    amount = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs: dict) -> dict:
        from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
        from world.captivity.models import Captivity  # noqa: PLC0415

        captivity = Captivity.objects.filter(pk=attrs["captivity_id"]).first()
        if captivity is None:
            msg = "No such captivity."
            raise serializers.ValidationError(msg)
        if captivity.status != CaptivityStatus.HELD:
            msg = "That captivity has already ended."
            raise serializers.ValidationError(msg)
        attrs["captivity"] = captivity
        return attrs

    def save(self, **kwargs: object) -> Project:  # noqa: ARG002
        from world.captivity.exceptions import CaptivityError  # noqa: PLC0415
        from world.captivity.ransom_project import demand_ransom_project  # noqa: PLC0415

        try:
            return demand_ransom_project(
                self.validated_data["captivity"],
                amount=self.validated_data.get("amount"),
            )
        except CaptivityError as exc:
            raise serializers.ValidationError(exc.user_message) from exc


class StoryInstanceSerializer(serializers.ModelSerializer):
    """A GM-owned temp scene room row for the story-builder dashboard (#2450)."""

    room_id = serializers.IntegerField(source="room.pk", read_only=True)
    name = serializers.CharField(source="room.db_key", read_only=True)
    grants = serializers.SerializerMethodField()

    class Meta:
        model = InstancedRoom
        fields = ["id", "room_id", "name", "status", "created_at", "grants"]

    def get_grants(self, obj: InstancedRoom) -> list[str]:
        """Character names granted access, from the view's batched lookup.

        Populated via serializer ``context["grants_by_room"]`` (keyed by
        ``RoomProfile``/``ObjectDB`` pk, which are the same value —
        ``RoomProfile.objectdb`` is its primary key) so the whole list of
        instances costs one extra query, not one per row.
        """
        grants_by_room: dict[int, list[str]] = self.context.get("grants_by_room", {})
        return grants_by_room.get(obj.room_id, [])


class StoryRoomSerializer(WorldBuilderRoomSerializer):
    """One RoomProfile in the story-builder manager payload (#2450).

    Extends the staff-only ``WorldBuilderRoomSerializer`` with ``grants`` — the
    names of characters currently granted access to join this room. Kept as a
    subclass (not a change to the shared serializer) so the staff world-builder
    manager payload shape is untouched.
    """

    grants = serializers.ListField(child=serializers.CharField())


class StoryAreaManagerSerializer(WorldBuilderAreaManagerSerializer):
    """The story-builder area-manager payload: area header + rooms (with grants) + exits."""

    rooms = StoryRoomSerializer(many=True)


class MyStoryGrantSerializer(serializers.ModelSerializer):
    """A player's own story-room access grants (#2450 Fix 2 — spec Decision 1 web surface).

    Backs ``GET /api/gm/my-story-grants/``, the read side of the player-facing
    Story Rooms page. Read-only: joining/leaving still go through the
    ``join_story_room``/``leave_story_room`` REGISTRY actions
    (``JoinStoryRoomAction``/``LeaveStoryRoomAction``,
    ``actions/definitions/story_builder.py``), dispatched via the generic
    action-dispatch endpoint — never a DRF write here.

    ``character_id`` is included even though it isn't shown in the UI: those
    two actions resolve their actor from ``actor.sheet_data`` (no target-character
    kwarg) and ``join_story_room``/``leave_story_room`` 404 with "no invitation"
    unless the dispatching character is exactly the one the grant was issued to
    — so the frontend must dispatch each row's join/leave against *this*
    character, not whichever character happens to be active. Since
    ``CharacterSheet.character`` is a primary_key OneToOneField, this FK's attname
    (``StoryRoomGrant.character_id``) already equals the character's ObjectDB pk,
    the id the generic dispatch endpoint (``/api/actions/characters/<id>/dispatch/``)
    expects.
    """

    room_id = serializers.IntegerField(read_only=True)
    room_name = serializers.CharField(source="room.objectdb.db_key", read_only=True)
    character_id = serializers.IntegerField(read_only=True)
    character_name = serializers.CharField(source="character.character.db_key", read_only=True)
    is_inside = serializers.SerializerMethodField()

    class Meta:
        model = StoryRoomGrant
        fields = [
            "id",
            "room_id",
            "room_name",
            "character_id",
            "character_name",
            "is_inside",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_inside(self, obj: StoryRoomGrant) -> bool:
        """True when the granted character is currently located inside the room.

        Compares ObjectDB pks directly — ``room_id`` is the same value as the
        room's ObjectDB pk (``RoomProfile.objectdb`` is its primary key), so no
        extra query is needed beyond the character's own location.
        """
        return obj.character.character.db_location_id == obj.room_id


class ProfileTextRequestDetailsSerializer(serializers.ModelSerializer):
    """Read payload for PROFILE_TEXT requests (#2631)."""

    current_text = serializers.SerializerMethodField()

    class Meta:
        model = ProfileTextRequestDetails
        fields = ["field", "proposed_text", "current_text", "applied_version"]
        read_only_fields = fields

    def get_current_text(self, obj: ProfileTextRequestDetails) -> str:
        """The field's live text — the GM's side-by-side left pane."""
        sheet = obj.request.membership.persona.character_sheet
        return getattr(sheet.true_profile, obj.field, "")


class DistinctionChangeRequestDetailsSerializer(serializers.ModelSerializer):
    """Read payload for DISTINCTION_CHANGE requests (#2631)."""

    distinction_name = serializers.CharField(
        source="distinction.name", read_only=True, allow_null=True
    )
    held_distinction_name = serializers.CharField(
        source="character_distinction.distinction.name", read_only=True, allow_null=True
    )
    authorization_xp_cost = serializers.IntegerField(
        source="authorization.xp_cost", read_only=True, allow_null=True
    )
    authorization_consumed = serializers.BooleanField(
        source="authorization.is_consumed", read_only=True, allow_null=True
    )

    class Meta:
        model = DistinctionChangeRequestDetails
        fields = [
            "action",
            "distinction",
            "distinction_name",
            "character_distinction",
            "held_distinction_name",
            "rank",
            "authorization",
            "authorization_xp_cost",
            "authorization_consumed",
        ]
        read_only_fields = fields


class TableUpdateRequestSerializer(serializers.ModelSerializer):
    """Read serializer for table update requests (#2631)."""

    table = serializers.IntegerField(source="membership.table_id", read_only=True)
    table_name = serializers.CharField(source="membership.table.name", read_only=True)
    persona_name = serializers.CharField(source="membership.persona.name", read_only=True)
    character_sheet = serializers.IntegerField(
        source="membership.persona.character_sheet_id", read_only=True
    )
    profile_text_details = ProfileTextRequestDetailsSerializer(read_only=True, allow_null=True)
    distinction_details = DistinctionChangeRequestDetailsSerializer(read_only=True, allow_null=True)

    class Meta:
        model = TableUpdateRequest
        fields = [
            "id",
            "kind",
            "status",
            "player_reasoning",
            "gm_notes",
            "table",
            "table_name",
            "persona_name",
            "character_sheet",
            "created_at",
            "resolved_at",
            "completed_at",
            "profile_text_details",
            "distinction_details",
        ]
        read_only_fields = fields


class TableUpdateRequestCreateSerializer(serializers.Serializer):
    """Create input for a table update request — kind-branched validation (#2631)."""

    membership = serializers.PrimaryKeyRelatedField(
        queryset=GMTableMembership.objects.filter(left_at__isnull=True)
    )
    kind = serializers.ChoiceField(choices=TableRequestKind.choices)
    reasoning = serializers.CharField()
    # PROFILE_TEXT payload
    field = serializers.CharField(required=False, allow_blank=True)
    proposed_text = serializers.CharField(required=False, allow_blank=True)
    # DISTINCTION_CHANGE payload
    action = serializers.CharField(required=False, allow_blank=True)
    distinction = serializers.IntegerField(required=False, allow_null=True)
    character_distinction = serializers.IntegerField(required=False, allow_null=True)
    rank = serializers.IntegerField(required=False, min_value=1, default=1)

    def validate(self, attrs: dict) -> dict:
        kind = attrs["kind"]
        if kind == TableRequestKind.PROFILE_TEXT:
            if not attrs.get("field") or not attrs.get("proposed_text"):
                msg = "PROFILE_TEXT requests need field and proposed_text."
                raise serializers.ValidationError(msg)
        elif not attrs.get("action"):
            msg = "DISTINCTION_CHANGE requests need an action."
            raise serializers.ValidationError(msg)
        return attrs


class TableUpdateRequestSignoffSerializer(serializers.Serializer):
    """Signoff input: the GM's yes/no + notes (#2631)."""

    approve = serializers.BooleanField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
