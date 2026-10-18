"""Serializers for the NPC roster and authoring API (#4418)."""

from __future__ import annotations

from typing import Any, ClassVar

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.npc_services.constants import RegardTargetType
from world.npc_services.models import (
    REGARD_MAX,
    REGARD_MIN,
    PersonalityTrait,
    PreferenceValence,
)
from world.roster.constants import NPCBorrowAudience, NPCLendPolicy, NPCSection
from world.roster.models import NPCLoan, RosterEntry
from world.roster.services.gallery import portrait_url
from world.roster.services.npc_lending import OWNER_FALLBACK_NAME

DESCRIPTION_PREVIEW_LENGTH = 200


# The templates staff curate for every GM.
STAFF_TEMPLATES = Q(story_npc_settings__is_template=True, created_by_account__is_staff=True)
# What the NPC roster lists to every GM and Guide.
LISTED_NPCS = Q(
    story_npc_settings__listed_on_npc_roster=True, story_npc_settings__is_template=False
)


def source_entries_for(account) -> Q:
    """The NPCs ``account`` may copy from: its own, staff templates, and any listed NPC.

    A copy of an NPC ``account`` does not own leaves out its notes (``copy_npc_section``).
    """
    if account.is_staff:
        return Q()
    return Q(created_by_account=account) | STAFF_TEMPLATES | LISTED_NPCS


class NPCRosterRowSerializer(serializers.ModelSerializer):
    """One listed NPC for a GM or Guide browsing the roster.

    ``context`` carries what the view read once for the page: ``viewer`` (the
    ``NPCViewer`` for the request), ``owner_names`` (account id to character name).
    """

    name = serializers.CharField(source="character_sheet.character.db_key", read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    lend_policy = serializers.CharField(source="story_npc_settings.lend_policy", read_only=True)
    borrow_audience = serializers.CharField(
        source="story_npc_settings.borrow_audience", read_only=True
    )
    can_borrow = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields: ClassVar[tuple[str, ...]] = (
            "id",
            "name",
            "thumbnail_url",
            "description",
            "owner_name",
            "lend_policy",
            "borrow_audience",
            "can_borrow",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields

    def get_thumbnail_url(self, obj: RosterEntry) -> str | None:
        return portrait_url(obj)

    def get_description(self, obj: RosterEntry) -> str:
        """What the character handler shows, read off rows the view selected.

        The handler's own read get_or_creates a display row per NPC, which a list
        must not do; the order is the handler's: a disguise overlay, the permanent
        description, then the sheet's free text.
        """
        try:
            display = obj.character_sheet.character.display_data
            text = display.get_display_description()
        except ObjectDoesNotExist:
            text = ""
        return (text or obj.character_sheet.additional_desc or "")[:DESCRIPTION_PREVIEW_LENGTH]

    def get_owner_name(self, obj: RosterEntry) -> str:
        return self.context["owner_names"].get(obj.created_by_account_id, OWNER_FALLBACK_NAME)

    def get_can_borrow(self, obj: RosterEntry) -> bool:
        return self.context["viewer"].can_borrow(obj, obj.story_npc_settings)

    def to_representation(self, instance: RosterEntry) -> dict[str, Any]:
        data = super().to_representation(instance)
        if self.context["viewer"].sees_notes(instance):
            data["notes_for_player"] = instance.story_npc_settings.notes_for_player
        return data


class NPCLoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = NPCLoan
        fields: ClassVar[tuple[str, ...]] = ("id", "roster_entry", "status")
        read_only_fields: ClassVar[tuple[str, ...]] = fields


class NPCPreferenceReadSerializer(serializers.Serializer):
    """One trait the NPC likes or dislikes, as the NPC form shows it."""

    trait_id = serializers.IntegerField(read_only=True)
    trait_name = serializers.CharField(read_only=True)
    valence = serializers.ChoiceField(choices=PreferenceValence.choices, read_only=True)


class NPCRegardReadSerializer(serializers.Serializer):
    """One active opinion the NPC holds. ``target_name`` is a persona, organization or
    society name, never an account name."""

    target_type = serializers.ChoiceField(choices=RegardTargetType.choices, read_only=True)
    target_id = serializers.IntegerField(read_only=True)
    target_name = serializers.CharField(read_only=True)
    value = serializers.IntegerField(read_only=True)
    reason = serializers.CharField(read_only=True)


class NPCDetailSerializer(NPCRosterRowSerializer):
    """The owner's, an active borrower's, or staff's view of one NPC and its settings."""

    listed_on_npc_roster = serializers.BooleanField(
        source="story_npc_settings.listed_on_npc_roster"
    )
    lend_policy = serializers.ChoiceField(
        source="story_npc_settings.lend_policy", choices=NPCLendPolicy.choices
    )
    borrow_audience = serializers.ChoiceField(
        source="story_npc_settings.borrow_audience", choices=NPCBorrowAudience.choices
    )
    notes_for_player = serializers.CharField(
        source="story_npc_settings.notes_for_player", allow_blank=True
    )
    is_template = serializers.BooleanField(source="story_npc_settings.is_template", read_only=True)
    open_requests = serializers.SerializerMethodField()
    # What the NPC already has, so the form's edits merge onto it (#4418). Two
    # queries for the one NPC a detail read serves.
    preferences = serializers.SerializerMethodField()
    regard = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields: ClassVar[tuple[str, ...]] = (
            *NPCRosterRowSerializer.Meta.fields,
            "listed_on_npc_roster",
            "notes_for_player",
            "is_template",
            "open_requests",
            "preferences",
            "regard",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = (
            "id",
            "name",
            "thumbnail_url",
            "description",
            "owner_name",
            "can_borrow",
            "is_template",
            "open_requests",
            "preferences",
            "regard",
        )

    @extend_schema_field(NPCPreferenceReadSerializer(many=True))
    def get_preferences(self, obj: RosterEntry) -> list[dict[str, Any]]:
        from world.npc_services.models import NpcPreference  # noqa: PLC0415

        rows = NpcPreference.objects.filter(
            persona=obj.character_sheet.primary_persona
        ).select_related("trait")
        return NPCPreferenceReadSerializer(
            [
                {"trait_id": row.trait_id, "trait_name": row.trait.name, "valence": row.valence}
                for row in rows
            ],
            many=True,
        ).data

    @extend_schema_field(NPCRegardReadSerializer(many=True))
    def get_regard(self, obj: RosterEntry) -> list[dict[str, Any]]:
        from world.npc_services.models import NpcRegard  # noqa: PLC0415

        rows = (
            NpcRegard.objects.filter(
                holder_persona=obj.character_sheet.primary_persona, ended_at__isnull=True
            )
            .select_related("target_persona", "target_organization", "target_society")
            .order_by("pk")
        )
        lines = []
        for row in rows:
            target = row.get_active_target()
            if target is None:  # the target row was deleted (SET_NULL)
                continue
            lines.append(
                {
                    "target_type": row.target_type,
                    "target_id": target.pk,
                    "target_name": target.name,
                    "value": row.value,
                    "reason": row.reason,
                }
            )
        return NPCRegardReadSerializer(lines, many=True).data

    def get_owner_name(self, obj: RosterEntry) -> str:
        from world.roster.views.npc_views import owner_names_for  # noqa: PLC0415

        return owner_names_for([obj]).get(obj.created_by_account_id, OWNER_FALLBACK_NAME)

    def get_open_requests(self, obj: RosterEntry) -> list[dict[str, Any]]:
        if not self.context["viewer"].manages(obj):
            return []
        return [
            {"id": loan.pk, "status": loan.status}
            for loan in obj.npc_loans.filter(status="requested").order_by("pk")
        ]

    def to_representation(self, instance: RosterEntry) -> dict[str, Any]:
        data = super().to_representation(instance)
        if not self.context["viewer"].sees_notes(instance):
            data.pop("notes_for_player", None)
        return data

    def update(self, instance: RosterEntry, validated_data: dict[str, Any]) -> RosterEntry:
        changes = validated_data.get("story_npc_settings", {})
        settings = instance.story_npc_settings
        for field, value in changes.items():
            setattr(settings, field, value)
        if changes:
            settings.save(update_fields=list(changes))
        return instance


class CopySectionSerializer(serializers.Serializer):
    """``{source_entry, section}``: replace one section of the target with the source's."""

    source_entry = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.none())
    section = serializers.ChoiceField(choices=NPCSection.choices)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None:  # schema generation builds the serializer with no request
            return
        account = request.user
        self.fields["source_entry"].queryset = RosterEntry.objects.filter(
            source_entries_for(account), story_npc_settings__isnull=False
        )


class CopyAsNewSerializer(serializers.Serializer):
    """``{name, as_template}``: a copy of the NPC under a new name."""

    name = serializers.CharField(max_length=80)
    as_template = serializers.BooleanField(default=False)


class AnswerSerializer(serializers.Serializer):
    """``{loan_id, accept}``."""

    loan_id = serializers.IntegerField()
    accept = serializers.BooleanField()


class RegardSerializer(serializers.Serializer):
    """``{target_type, target_id, value, reason}``: the NPC's opinion of one target."""

    target_type = serializers.ChoiceField(choices=RegardTargetType.choices)
    target_id = serializers.IntegerField()
    value = serializers.IntegerField(min_value=REGARD_MIN, max_value=REGARD_MAX)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.models import Organization, Society  # noqa: PLC0415

        model = {
            RegardTargetType.PERSONA: Persona,
            RegardTargetType.ORGANIZATION: Organization,
            RegardTargetType.SOCIETY: Society,
        }[attrs["target_type"]]
        target = model.objects.filter(pk=attrs["target_id"]).first()
        if target is None:
            raise serializers.ValidationError({"target_id": "No such target."})
        attrs["target"] = target
        return attrs


class PreferenceLineSerializer(serializers.Serializer):
    trait = serializers.PrimaryKeyRelatedField(queryset=PersonalityTrait.objects.all())
    valence = serializers.ChoiceField(choices=PreferenceValence.choices)


class PreferencesSerializer(serializers.Serializer):
    """``{preferences: [{trait, valence}]}``: replaces the NPC's likes and dislikes."""

    preferences = PreferenceLineSerializer(many=True)


class NPCOfferSerializer(serializers.ModelSerializer):
    """One OFFERED loan, as the Guide it was offered to reads it.

    ``context["offered_names"]`` maps the offering account's id to the name shown.
    """

    loan_id = serializers.IntegerField(source="pk", read_only=True)
    roster_entry_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(
        source="roster_entry.character_sheet.character.db_key", read_only=True
    )
    thumbnail_url = serializers.SerializerMethodField()
    scene_id = serializers.IntegerField(read_only=True, allow_null=True)
    scene_title = serializers.CharField(source="scene.name", read_only=True, allow_null=True)
    offered_by_name = serializers.SerializerMethodField()
    notes_for_player = serializers.SerializerMethodField()

    class Meta:
        model = NPCLoan
        fields: ClassVar[tuple[str, ...]] = (
            "loan_id",
            "roster_entry_id",
            "name",
            "thumbnail_url",
            "scene_id",
            "scene_title",
            "offered_by_name",
            "notes_for_player",
        )
        read_only_fields: ClassVar[tuple[str, ...]] = fields

    def get_thumbnail_url(self, obj: NPCLoan) -> str | None:
        return portrait_url(obj.roster_entry)

    def get_offered_by_name(self, obj: NPCLoan) -> str:
        return self.context["offered_names"].get(obj.offered_by_id, OWNER_FALLBACK_NAME)

    def get_notes_for_player(self, obj: NPCLoan) -> str:
        try:
            return obj.roster_entry.story_npc_settings.notes_for_player
        except ObjectDoesNotExist:
            return ""


class RegardResultSerializer(serializers.Serializer):
    """What ``PUT regard`` answers: the regard now set."""

    target_type = serializers.ChoiceField(choices=RegardTargetType.choices)
    target_id = serializers.IntegerField()
    value = serializers.IntegerField()


class CopySectionResultSerializer(serializers.Serializer):
    """What ``POST copy-section`` answers: the section copied."""

    section = serializers.ChoiceField(choices=NPCSection.choices)


class CreatedNPCSerializer(serializers.Serializer):
    """What ``POST copy-as-new`` answers: the new NPC's roster entry id."""

    id = serializers.IntegerField()
