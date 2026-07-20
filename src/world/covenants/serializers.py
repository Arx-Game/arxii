"""DRF serializers for covenants API."""

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.covenants.handlers import can_engage_membership
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantLevelThreshold,
    CovenantRank,
    CovenantRite,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.covenants.services import resolve_effective_role


class CovenantRoleSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantRole lookup data."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )

    class Meta:
        model = CovenantRole
        fields = [
            "id",
            "name",
            "slug",
            "covenant_type",
            "covenant_type_display",
            "sword_weight",
            "shield_weight",
            "crown_weight",
            "speed_rank",
            "description",
            "parent_role",
        ]
        read_only_fields = fields


class CovenantRankSerializer(serializers.ModelSerializer):
    """Serializer for CovenantRank (the per-covenant authority ladder).

    Read: exposes all rank fields.
    Write: validates tier uniqueness per covenant and capability flags.
    """

    class Meta:
        model = CovenantRank
        fields = [
            "id",
            "covenant",
            "name",
            "tier",
            "description",
            "can_invite",
            "can_kick",
            "can_manage_ranks",
            "can_lead_rituals",
            "can_request_gm",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        inst: CovenantRank | None = self.instance  # type: ignore[assignment]
        covenant = attrs.get("covenant", inst.covenant if inst is not None else None)
        tier = attrs.get("tier", inst.tier if inst is not None else None)
        name = attrs.get("name", inst.name if inst is not None else None)

        if covenant is not None and tier is not None:
            qs = CovenantRank.objects.filter(covenant=covenant, tier=tier)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"tier": "A rank with this tier already exists for this covenant."}
                )

        if covenant is not None and name is not None:
            qs = CovenantRank.objects.filter(covenant=covenant, name=name)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "A rank with this name already exists for this covenant."}
                )

        return attrs


class CovenantRankNestedSerializer(serializers.ModelSerializer):
    """Minimal nested representation of a CovenantRank (id, name, tier) for embedding
    inside CharacterCovenantRoleSerializer."""

    class Meta:
        model = CovenantRank
        fields = ["id", "name", "tier"]
        read_only_fields = fields


class ViewerCapabilitiesSerializer(serializers.Serializer):
    """Inline serializer for the viewer's capabilities in a covenant."""

    can_invite = serializers.BooleanField()
    can_kick = serializers.BooleanField()
    can_manage_ranks = serializers.BooleanField()
    can_request_gm = serializers.BooleanField()


class CharacterCovenantRoleSerializer(serializers.ModelSerializer):
    """Read-only serializer for a character's covenant role assignment.

    Exposes the member's rank (nested id/name/tier) and a viewer_capabilities
    block showing the requesting user's own active membership capabilities in
    the same covenant (or all-False if the viewer has no active membership).

    ``covenant_role`` is the RESOLVED effective role (the resonance sub-role when
    the character's COVENANT_ROLE thread has crossed the sub-role's unlock threshold;
    the stored parent role otherwise). ``anchor_role`` is always the stored parent
    (anchor) role, providing context for what sub-roles are possible.
    """

    covenant_role = serializers.SerializerMethodField()
    anchor_role = CovenantRoleSerializer(source="covenant_role", read_only=True)
    rank = CovenantRankNestedSerializer(read_only=True)
    is_active = serializers.SerializerMethodField()
    can_engage = serializers.SerializerMethodField()
    engage_blocked_reason = serializers.SerializerMethodField()
    viewer_capabilities = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = CharacterCovenantRole
        fields = [
            "id",
            "character_sheet",
            "covenant",
            "covenant_role",
            "anchor_role",
            "rank",
            "engaged",
            "joined_at",
            "left_at",
            "is_active",
            "can_engage",
            "engage_blocked_reason",
            "viewer_capabilities",
            "display_name",
        ]
        read_only_fields = fields

    @extend_schema_field(CovenantRoleSerializer)
    def get_covenant_role(self, obj: CharacterCovenantRole) -> dict:
        """Return the RESOLVED effective role serialized as CovenantRoleSerializer.

        Falls back to the stored parent role when the membership's character
        typeclass is unavailable (e.g. unpuppeted / no ObjectDB row yet).
        """
        character = obj.character_sheet.character
        if character is None:
            effective_role = obj.covenant_role
        else:
            effective_role = resolve_effective_role(character=character, role=obj.covenant_role)
        return CovenantRoleSerializer(effective_role).data

    def get_is_active(self, obj: CharacterCovenantRole) -> bool:
        return obj.left_at is None

    def get_can_engage(self, obj: CharacterCovenantRole) -> bool:
        return can_engage_membership(obj)

    def get_engage_blocked_reason(self, obj: CharacterCovenantRole) -> str | None:
        if can_engage_membership(obj):
            return None
        from world.covenants.constants import CovenantType  # noqa: PLC0415

        if obj.covenant.covenant_type == CovenantType.BATTLE and obj.covenant.is_dormant:
            return (
                "This battle covenant is dormant — it must be raised again before you can engage."
            )
        return "No covenant members present in this scene."

    @extend_schema_field(ViewerCapabilitiesSerializer)
    def get_viewer_capabilities(self, obj: CharacterCovenantRole) -> dict:
        """Return can_invite/can_kick/can_manage_ranks for the REQUESTING user's own
        active membership in the same covenant, or all-False when not a member.

        Results are memoized per covenant_id in the serializer context so a list
        response of N memberships from the same covenant issues only one query
        rather than one per row.
        """
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return {
                "can_invite": False,
                "can_kick": False,
                "can_manage_ranks": False,
                "can_request_gm": False,
            }

        # Memoize per-covenant in the serializer context dict.
        cache_key = f"_viewer_caps_{obj.covenant_id}"
        if cache_key not in self.context:
            viewer_membership = (
                CharacterCovenantRole.objects.filter(
                    covenant_id=obj.covenant_id,
                    left_at__isnull=True,
                    character_sheet__roster_entry__tenures__end_date__isnull=True,
                    character_sheet__roster_entry__tenures__player_data__account=request.user,
                )
                .select_related("rank")
                .first()
            )
            if viewer_membership is None:
                self.context[cache_key] = {
                    "can_invite": False,
                    "can_kick": False,
                    "can_manage_ranks": False,
                    "can_request_gm": False,
                }
            else:
                self.context[cache_key] = {
                    "can_invite": viewer_membership.rank.can_invite,
                    "can_kick": viewer_membership.rank.can_kick,
                    "can_manage_ranks": viewer_membership.rank.can_manage_ranks,
                    "can_request_gm": viewer_membership.rank.can_request_gm,
                }
        return self.context[cache_key]  # type: ignore[return-value]

    def get_display_name(self, obj: CharacterCovenantRole) -> str:
        """The member's display name, or a generic placeholder if they blocked the viewer (#2086).

        When the viewer is blocked by this member's player, returns "a member has blocked you"
        — never the member's name or identity. Staff always see the real character name.
        """
        from world.scenes.block_services import member_blocked_viewer  # noqa: PLC0415

        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return f"Character #{obj.character_sheet_id}"
        try:
            if member_blocked_viewer(viewer_account=request.user, member_sheet=obj.character_sheet):
                return "a member has blocked you"
        except ObjectDoesNotExist:
            pass  # No roster entry on this sheet — show the normal name.
        return f"Character #{obj.character_sheet_id}"


class CovenantSerializer(serializers.ModelSerializer):
    """Read-only serializer for Covenant identity, type, level, and lifecycle state."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )
    battle_binding_display = serializers.CharField(
        source="get_battle_binding_display", read_only=True
    )
    member_count = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    legend_total = serializers.SerializerMethodField()
    storylines = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Covenant
        fields = [
            "id",
            "name",
            "covenant_type",
            "covenant_type_display",
            "level",
            "sworn_objective",
            "formed_at",
            "dissolved_at",
            "is_active",
            "is_dormant",
            "battle_binding",
            "battle_binding_display",
            "member_count",
            "legend_total",
            "storylines",
        ]
        read_only_fields = fields

    def get_member_count(self, obj: Covenant) -> int:
        # Prefer the page aggregate the viewset precomputed (2026-07 audit);
        # fall back to a direct count for callers outside CovenantViewSet.list.
        aggregate = self.context.get("covenant_aggregates", {}).get(obj.pk)
        if aggregate is not None:
            return aggregate["member_count"]
        return obj.memberships.filter(left_at__isnull=True).count()

    def get_is_active(self, obj: Covenant) -> bool:
        return obj.dissolved_at is None

    def get_legend_total(self, obj: Covenant) -> int:
        aggregate = self.context.get("covenant_aggregates", {}).get(obj.pk)
        if aggregate is not None:
            return aggregate["legend_total"]
        from world.societies.services import get_covenant_legend_total  # noqa: PLC0415

        return get_covenant_legend_total(obj)


class CovenantLevelThresholdSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantLevelThreshold lookup rows."""

    class Meta:
        model = CovenantLevelThreshold
        fields = ("level", "required_legend")


class CovenantRiteSerializer(serializers.ModelSerializer):
    """Read-only serializer for CovenantRite authored definitions."""

    covenant_type_display = serializers.CharField(
        source="get_covenant_type_display", read_only=True
    )

    class Meta:
        model = CovenantRite
        fields = [
            "id",
            "ritual",
            "covenant_type",
            "covenant_type_display",
            "min_covenant_level",
            "min_members_present",
            "granted_condition",
            "base_severity",
            "severity_per_extra_participant",
            "max_severity",
            "duration_rounds",
        ]
        read_only_fields = fields


class CovenantRolePassivePowerSerializer(serializers.Serializer):
    """Read-only shape for one active membership's current passive role power.

    A member's passive power is the tier-0 CAPABILITY_GRANT ThreadPullEffect for
    the resonance their COVENANT_ROLE thread channels. Members without a woven
    role-thread (or whose thread level is below the effect's min_thread_level)
    have null capability fields; resonance_name may still be populated when a
    thread exists.
    """

    membership_id = serializers.IntegerField(read_only=True)
    character_sheet = serializers.IntegerField(read_only=True)
    covenant_role_id = serializers.IntegerField(read_only=True)
    covenant_role_name = serializers.CharField(read_only=True)
    resonance_name = serializers.CharField(read_only=True, allow_null=True)
    capability_name = serializers.CharField(read_only=True, allow_null=True)
    narrative_snippet = serializers.CharField(read_only=True, allow_null=True)
    engaged = serializers.BooleanField(read_only=True)


class GearArchetypeCompatibilitySerializer(serializers.ModelSerializer):
    """Read-only serializer for GearArchetypeCompatibility join rows."""

    gear_archetype_display = serializers.CharField(
        source="get_gear_archetype_display", read_only=True
    )

    class Meta:
        model = GearArchetypeCompatibility
        fields = [
            "id",
            "covenant_role",
            "gear_archetype",
            "gear_archetype_display",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Action input serializers — used for @extend_schema request bodies only.
# These are explicit lightweight serializers so drf-spectacular generates
# accurate OpenAPI request bodies for the three @action endpoints that
# would otherwise inherit the parent ViewSet's CovenantRankSerializer.
# ---------------------------------------------------------------------------


class AssignMemberRequestSerializer(serializers.Serializer):
    """Request body for POST /api/covenants/ranks/{pk}/assign-member/."""

    membership = serializers.IntegerField(
        help_text="PK of the CharacterCovenantRole to assign to this rank.",
    )


class TransferTopRequestSerializer(serializers.Serializer):
    """Request body for POST /api/covenants/ranks/{pk}/transfer-top/."""

    new_top_membership = serializers.IntegerField(
        help_text="PK of the CharacterCovenantRole that will receive the top rank.",
    )


class ReorderRanksRequestSerializer(serializers.Serializer):
    """Request body for POST /api/covenants/ranks/reorder/."""

    covenant = serializers.IntegerField(
        help_text="PK of the Covenant whose rank ladder is being reordered.",
    )
    ordered_rank_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text=(
            "All rank PKs for this covenant in desired order (index 0 = top authority / tier 1)."
        ),
    )
