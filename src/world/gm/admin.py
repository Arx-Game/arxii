"""GM admin configuration."""

from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Model, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from world.gm.models import (
    AreaBuildGrant,
    CatalogSuggestion,
    CheckTypeSituationFit,
    ConsequencePoolGuide,
    DistinctionChangeRequestDetails,
    GMApplication,
    GMLevelCap,
    GMLevelChange,
    GMProfile,
    GMPrompt,
    GMRewardConfig,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    GMWeeklyRewardTracker,
    GuideProfile,
    ProfileTextRequestDetails,
    SituationDifficultyGuide,
    SituationKind,
    StoryArea,
    StoryRoomGrant,
    TableUpdateRequest,
)
from world.roster.constants import NPCLoanStatus
from world.roster.models import NPCLoan


@admin.register(GMProfile)
class GMProfileAdmin(admin.ModelAdmin):
    list_display = ["account", "level", "approved_at"]
    list_filter = ["level"]
    raw_id_fields = ["account", "approved_by"]
    search_fields = ["account__username"]


@admin.register(GuideProfile)
class GuideProfileAdmin(admin.ModelAdmin):
    """Staff grant the Guide role here and see what a Guide is playing (#4418).

    Laid out as the approved demo's admin screen: Who (granted by is set to the
    saving staff account), Right now (each active loan with a Return to GM link),
    and Last 30 days (how the Guide's hand-offs went).
    """

    list_display = ["display_name", "account", "is_active", "granted_by", "granted_at"]
    list_filter = ["is_active"]
    raw_id_fields = ["account"]
    # Granted by is never a form field: ``save_model`` sets it to the saving staff
    # account, and ``granted_by_label`` shows it read-only. No widget, large or not.
    large_table_widget_exempt = ["granted_by"]
    search_fields = ["display_name", "account__username"]
    readonly_fields = ["granted_by_label", "right_now", "hand_offs"]
    fieldsets = [
        ("Who", {"fields": ["account", "granted_by_label", "is_active", "display_name"]}),
        ("Right now", {"fields": ["right_now"]}),
        ("Last 30 days", {"fields": ["hand_offs"]}),
    ]
    actions = ["end_active_loans"]

    def save_model(
        self, request: HttpRequest, obj: GuideProfile, form: ModelForm, change: bool
    ) -> None:
        """A new grant records the staff account saving it; later edits keep it."""
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Granted by")
    def granted_by_label(self, obj: GuideProfile | None) -> str:
        if obj is None or obj.pk is None:
            return "Set to you on save"
        return str(obj.granted_by)

    @admin.display(description="Playing")
    def right_now(self, obj: GuideProfile | None) -> str:
        """The Guide's active loans: NPC, who lent it, the scene, and Return to GM."""
        from world.scenes.cast_list_services import player_names  # noqa: PLC0415

        if obj is None or obj.pk is None:
            return "Nothing yet."
        loans = list(
            NPCLoan.objects.filter(borrower=obj.account, status=NPCLoanStatus.ACTIVE)
            .select_related("roster_entry__character_sheet__character", "scene")
            .order_by("pk")
        )
        if not loans:
            return "Nothing right now."
        names = player_names({loan.offered_by_id for loan in loans})
        rows = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (
                    _admin_link(loan.roster_entry, _npc_name(loan)),
                    names.get(loan.offered_by_id, ""),
                    _admin_link(loan.scene, loan.scene.name) if loan.scene else "",
                    format_html(
                        '<a href="{}">Return to GM</a>',
                        reverse(_RETURN_URL, args=[obj.pk, loan.pk]),
                    ),
                )
                for loan in loans
            ),
        )
        return format_html(
            '<table class="guide-loans"><thead><tr><th>Playing</th><th>For</th>'
            "<th>Scene</th><th></th></tr></thead><tbody>{}</tbody></table>",
            rows,
        )

    @admin.display(description="Hand-offs")
    def hand_offs(self, obj: GuideProfile | None) -> str:
        from world.roster.services.npc_lending import guide_hand_off_counts  # noqa: PLC0415

        if obj is None or obj.pk is None:
            return "None yet."
        counts = guide_hand_off_counts(
            obj.account, since=timezone.now() - timedelta(days=HAND_OFF_WINDOW_DAYS)
        )
        return (
            f"{counts.accepted} accepted, {counts.declined} declined, "
            f"{counts.taken_back_early} taken back early"
        )

    def get_urls(self) -> list[URLPattern]:
        return [
            path(
                "<int:object_id>/return-loan/<int:loan_id>/",
                self.admin_site.admin_view(self.return_loan_view),
                name=_RETURN_URL.removeprefix("admin:"),
            ),
            *super().get_urls(),
        ]

    def return_loan_view(self, request: HttpRequest, object_id: int, loan_id: int) -> HttpResponse:
        """Confirm, then end one of this Guide's active loans (Return to GM)."""
        from world.roster.services.npc_lending import end_loan  # noqa: PLC0415

        guide = self.get_object(request, str(object_id))
        if guide is None or not self.has_change_permission(request, guide):
            raise PermissionDenied
        loan = get_object_or_404(
            NPCLoan, pk=loan_id, borrower=guide.account, status=NPCLoanStatus.ACTIVE
        )
        change_url = reverse(
            f"admin:{self.opts.app_label}_{self.opts.model_name}_change", args=[guide.pk]
        )
        if request.method == "POST":
            end_loan(loan, by=request.user)
            self.message_user(request, f"{_npc_name(loan)} is back with its GM.", messages.SUCCESS)
            return HttpResponseRedirect(change_url)
        return TemplateResponse(
            request,
            "admin/guide_profile/return_loan.html",
            {
                **self.admin_site.each_context(request),
                "title": "Return to GM",
                "opts": self.opts,
                "guide": guide,
                "loan": loan,
                "npc_name": _npc_name(loan),
                "change_url": change_url,
            },
        )

    @admin.action(description="End the selected Guides' active NPC loans")
    def end_active_loans(self, request: HttpRequest, queryset: QuerySet[GuideProfile]) -> None:
        """Return every NPC the selected Guides are playing to its holder (#4418)."""
        from world.roster.services.npc_lending import end_loan  # noqa: PLC0415

        loans = NPCLoan.objects.filter(
            borrower__guide_profile__in=queryset, status=NPCLoanStatus.ACTIVE
        ).select_related("roster_entry__character_sheet__character", "borrower")
        ended = 0
        for loan in loans:
            end_loan(loan, by=request.user)
            ended += 1
        self.message_user(request, f"Ended {ended} NPC loan(s).", messages.SUCCESS)


# The Guide admin's summary window, and the name of its Return to GM page.
HAND_OFF_WINDOW_DAYS = 30
_RETURN_URL = "admin:arxii_guideprofile_return_loan"


def _npc_name(loan: NPCLoan) -> str:
    return loan.roster_entry.character_sheet.character.key


def _admin_link(obj: Model, label: str) -> str:
    """``label`` linked to ``obj``'s admin change page."""
    opts = obj._meta  # noqa: SLF001
    return format_html(
        '<a href="{}">{}</a>',
        reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]),
        label,
    )


@admin.register(AreaBuildGrant)
class AreaBuildGrantAdmin(admin.ModelAdmin):
    list_display = ["account", "area", "max_level", "room_budget", "granted_by", "created_at"]
    list_filter = ["max_level"]
    raw_id_fields = ["account", "area", "granted_by"]
    search_fields = ["account__username", "area__name"]


@admin.register(GMApplication)
class GMApplicationAdmin(admin.ModelAdmin):
    list_display = ["account", "status", "created_at", "reviewed_by"]
    list_filter = ["status"]
    raw_id_fields = ["account", "reviewed_by"]


@admin.register(GMTable)
class GMTableAdmin(admin.ModelAdmin):
    list_display = ["name", "gm", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["gm"]
    # A being's steward inline picks a table by autocomplete (#4333 slice 4).
    search_fields = ["name", "gm__account__username"]


@admin.register(GMTableMembership)
class GMTableMembershipAdmin(admin.ModelAdmin):
    list_display = ["table", "persona", "joined_at", "left_at"]
    list_filter = ["left_at"]
    raw_id_fields = ["table", "persona"]


@admin.register(GMRosterInvite)
class GMRosterInviteAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "roster_entry",
        "created_by",
        "created_at",
        "expires_at",
        "is_public",
        "claimed_by",
    ]
    list_filter = ["is_public", "claimed_at"]
    search_fields = ["code", "invited_email"]
    raw_id_fields = ["roster_entry", "created_by", "claimed_by"]


@admin.register(GMLevelCap)
class GMLevelCapAdmin(admin.ModelAdmin):
    list_display = [
        "level",
        "max_beat_risk",
        "allow_custom_stakes",
        "allow_global_scope_authoring",
        "auto_clear_regional",
        "max_story_areas",
        "max_story_rooms_per_area",
        "may_adapt_answers",
    ]
    list_filter = [
        "max_beat_risk",
        "may_adapt_answers",
        "allow_custom_stakes",
        "allow_global_scope_authoring",
        "auto_clear_regional",
    ]


@admin.register(GMLevelChange)
class GMLevelChangeAdmin(admin.ModelAdmin):
    """Audit row for a staff-driven GM level change — written by ``promote_gm`` only.

    Read-only in admin: no add/change/delete, so the audit trail can't be
    hand-edited or backdated.
    """

    list_display = ["profile", "old_level", "new_level", "changed_by", "created_at"]
    list_filter = ["old_level", "new_level"]
    raw_id_fields = ["profile", "changed_by"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(StoryArea)
class StoryAreaAdmin(admin.ModelAdmin):
    list_display = ("area", "gm", "created_at")
    raw_id_fields = ("gm", "area")


@admin.register(StoryRoomGrant)
class StoryRoomGrantAdmin(admin.ModelAdmin):
    autocomplete_fields = ["room", "return_location"]  # rooms are searched, never scrolled
    list_display = ("room", "character", "granted_by", "created_at")
    raw_id_fields = ["character", "granted_by"]


@admin.register(SituationKind)
class SituationKindAdmin(admin.ModelAdmin):
    list_display = ["name", "minimum_gm_level"]
    list_filter = ["minimum_gm_level"]
    search_fields = ["name"]


@admin.register(CheckTypeSituationFit)
class CheckTypeSituationFitAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "check_type"]
    list_filter = ["situation_kind"]
    raw_id_fields = ["check_type", "situation_kind"]


@admin.register(SituationDifficultyGuide)
class SituationDifficultyGuideAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "risk", "recommended_difficulty"]
    list_filter = ["risk", "recommended_difficulty"]
    raw_id_fields = ["situation_kind"]


@admin.register(ConsequencePoolGuide)
class ConsequencePoolGuideAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "pool", "is_default"]
    list_filter = ["is_default"]
    raw_id_fields = ["situation_kind", "pool"]


@admin.register(CatalogSuggestion)
class CatalogSuggestionAdmin(admin.ModelAdmin):
    list_display = ["submitted_by", "proposal_kind", "status", "created_at", "reviewer"]
    list_filter = ["proposal_kind", "status"]
    raw_id_fields = ["submitted_by", "situation_kind", "reviewer"]
    search_fields = ["proposal_text"]


@admin.register(GMRewardConfig)
class GMRewardConfigAdmin(admin.ModelAdmin):
    """Admin interface for the GM Story Reward's tunable award values (#2123)."""

    list_display = [
        "beat_xp_per_player",
        "beat_xp_cap",
        "episode_xp_per_player",
        "episode_xp_cap",
        "story_completion_xp_per_player",
        "story_completion_xp_cap",
        "weekly_reward_cap",
        "feedback_xp_per_rating_point",
    ]

    fieldsets = (
        (
            "Beat mark",
            {"fields": ("beat_xp_per_player", "beat_xp_cap")},
        ),
        (
            "Episode resolution",
            {"fields": ("episode_xp_per_player", "episode_xp_cap")},
        ),
        (
            "Story completion",
            {"fields": ("story_completion_xp_per_player", "story_completion_xp_cap")},
        ),
        (
            "Story feedback",
            {"fields": ("feedback_xp_per_rating_point",)},
        ),
        (
            "Weekly ceiling",
            {"fields": ("weekly_reward_cap",)},
        ),
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        """Singleton — no adding a second row via admin."""
        return not GMRewardConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        """Singleton — never delete the row (services rely on it existing)."""
        return False


@admin.register(GMWeeklyRewardTracker)
class GMWeeklyRewardTrackerAdmin(admin.ModelAdmin):
    """Admin interface for the per-GM weekly reward ledger (#2123). Read-only audit."""

    list_display = ["gm_profile", "game_week", "xp_awarded_this_week"]
    list_filter = ["game_week"]
    raw_id_fields = ["gm_profile", "game_week"]
    search_fields = ["gm_profile__account__username"]


class ProfileTextRequestDetailsInline(admin.StackedInline):
    """Inline payload view for PROFILE_TEXT requests (#2631)."""

    model = ProfileTextRequestDetails
    extra = 0
    raw_id_fields = ["applied_version"]


class DistinctionChangeRequestDetailsInline(admin.StackedInline):
    """Inline payload view for DISTINCTION_CHANGE requests (#2631)."""

    model = DistinctionChangeRequestDetails
    extra = 0
    raw_id_fields = ["distinction", "character_distinction", "sheet_update_request"]


@admin.register(TableUpdateRequest)
class TableUpdateRequestAdmin(admin.ModelAdmin):
    """Admin for player-submitted sheet-update requests (#2631)."""

    list_display = ["__str__", "kind", "status", "created_at", "resolved_by"]
    list_filter = ["kind", "status"]
    raw_id_fields = ["membership", "resolved_by"]
    readonly_fields = ["created_at", "resolved_at", "completed_at"]
    inlines = [ProfileTextRequestDetailsInline, DistinctionChangeRequestDetailsInline]


@admin.register(GMPrompt)
class GMPromptAdmin(admin.ModelAdmin):
    autocomplete_fields = [
        "addressed_to",
        "character_sheet",
        "interaction",
        "resolved_by",
        "scene",
        "subject_persona",
    ]
    list_display = (
        "id",
        "kind",
        "character_sheet",
        "addressed_to",
        "moment_type",
        "scene",
        "status",
        "success_level",
        "resolved_by",
        "created_at",
    )
    list_filter = ("status", "kind", "moment_type")
    readonly_fields = tuple(f.name for f in GMPrompt._meta.fields)  # noqa: SLF001

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        # Prompts are only ever created by maybe_suggest_dramatic_moments() and
        # resolved via resolve_dramatic_moment_suggestion() — no admin-authored rows.
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False
