from __future__ import annotations

from django.contrib import admin
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

from world.admin_utils import OneRowPerFormSet
from world.scenes.action_constants import DIFFICULTY_VALUES, MIN_DIFFICULTY_POINTS, DifficultyChoice
from world.worship.constants import InvocationPieceSource
from world.worship.models import (
    Answer,
    AnswerSacrificeLine,
    BeingFacet,
    BeingNickname,
    BeingRelationship,
    BeingResonance,
    BeingSteward,
    BeingTarotCard,
    ChosenFavorConfig,
    ConsecrationTier,
    DevotionConfig,
    DevotionStanding,
    DivineInterventionConfig,
    FavorInvocation,
    FavorOutcomeAward,
    Miracle,
    MiracleAppliedCondition,
    MiracleDamageProfile,
    MiraclePerformance,
    PendingAnswer,
    Pledge,
    PledgeCredit,
    PledgeDetails,
    Prayer,
    Relic,
    RiteKind,
    ShrineDetails,
    TempleDedication,
    Vision,
    WorshipDeclaration,
    WorshipFeastDay,
    WorshipGrant,
    WorshippedBeing,
    WorshipRite,
    WorshipRitePerformance,
    WorshipRiteTierAward,
    WorshipTradition,
)


@admin.register(WorshipTradition)
class WorshipTraditionAdmin(admin.ModelAdmin):
    list_display = ("name", "rites_specialization")
    search_fields = ("name",)


class BeingTarotCardInline(admin.TabularInline):
    model = BeingTarotCard
    formset = OneRowPerFormSet
    extra = 0
    autocomplete_fields = ("card",)


class BeingStewardInline(admin.StackedInline):
    """The table that stewards this being (#4333 slice 4): at most one.

    The read-only line beside the table shows what staff check before assigning
    it: the table GM's level, its members, the other beings it stewards, and the
    signs of a god. Saving runs ``BeingSteward.clean``, which refuses a GM below
    Senior and a being that shows a god sign.
    """

    model = BeingSteward
    formset = OneRowPerFormSet
    extra = 0
    max_num = 1
    autocomplete_fields = ("table",)
    fields = ("table", "steward_context")
    readonly_fields = ("steward_context",)
    verbose_name = "Steward"
    verbose_name_plural = "Steward"

    @admin.display(description="Checked before assigning")
    def steward_context(self, obj: BeingSteward | None) -> str:
        if obj is None or obj.pk is None:
            return (
                "Saved with the being. Refused when the table's GM is below Senior, or "
                "when the being shows a sign of a god: a public codex entry, a public "
                "worship declaration naming it (a secret faith does not count), a Chosen "
                "of it outside the table, or a temple dedicated to it."
            )
        from world.worship.steward_services import (  # noqa: PLC0415
            god_signs,
            table_context_line,
        )

        signs = god_signs(obj.being, obj.table)
        sign_text = (
            "Signs of a god: " + " ".join(signs)
            if signs
            else (
                "Signs of a god: none (no public codex entry, no public worship "
                "declarations, no Chosen outside the table, no temple)."
            )
        )
        return f"{table_context_line(obj.table, being=obj.being)} {sign_text}"


@admin.register(WorshippedBeing)
class WorshippedBeingAdmin(admin.ModelAdmin):
    list_display = ("name", "tradition", "resonance_pool", "lifetime_worship", "is_active")
    list_filter = ("tradition", "is_active")
    search_fields = ("name",)
    raw_id_fields = ("avatar_sheet",)
    # codex_entry points into the whole CodexEntry corpus — a plain select would
    # render every entry. Same widget MagicProgressionMilestoneAdmin uses against
    # the same CodexEntryAdmin (which declares the required search_fields).
    # invocation_check_type (#4333): the per-being override of the default
    # invocation check; blank uses Devotion config's.
    autocomplete_fields = ("codex_entry", "invocation_check_type")
    filter_horizontal = ("ultimate_techniques",)
    # The tarot link carries an orientation (#4198), so it is a row, not a multi-select.
    # The steward (#4333 slice 4) is a stacked row with its context beside it.
    inlines = (BeingTarotCardInline, BeingStewardInline)


@admin.register(BeingFacet)
class BeingFacetAdmin(admin.ModelAdmin):
    list_display = ("being", "facet", "invocation_ease_points", "earning_bonus_percent")
    list_filter = ("being",)
    search_fields = ("being__name", "facet__name")


def worn_pieces_table(invocation: FavorInvocation) -> SafeString:
    """The GM's invocation detail (#4520): each worn piece that counted, its signals, the
    favored facet that made it count and the ease it gave, as the piece was when the check
    rolled. Never a price."""
    pieces = list(invocation.pieces.prefetch_related("signals"))  # noqa: PREFETCH_STRING
    if not pieces:
        return format_html("<p>No worn piece, keepsake or Relic counted on this invocation.</p>")
    rows = []
    for piece in pieces:
        signals = list(piece.signals.all())
        if piece.source == InvocationPieceSource.WORN:
            gate = format_html(
                "<td>Favored facet</td><td>{} (the gate; ease {} per point)</td>",
                piece.facet_name,
                piece.ease_per_point,
            )
        else:
            gate = format_html(
                "<td>{}</td><td>ease {} per point</td>",
                piece.get_source_display(),
                piece.ease_per_point,
            )
        rows.append(
            format_html(
                "<tr><td rowspan='{}'>{}</td>{}<td>-</td></tr>",
                len(signals) + 1,
                piece.item_name,
                gate,
            )
        )
        rows.extend(
            format_html(
                "<tr><td>{}</td><td>{}</td><td>{}</td></tr>",
                signal.get_kind_display(),
                signal.detail,
                signal.points,
            )
            for signal in signals
        )
    total_points = sum(piece.points for piece in pieces)
    total_ease = sum(piece.ease for piece in pieces)
    note = format_html(
        "<p>{} points, eased {} before the cap; eased {} on the roll. Roll: {}.</p>",
        total_points,
        total_ease,
        invocation.worn_ease,
        invocation.outcome_tier.name,
    )
    return format_html(
        "<table><thead><tr><th>Piece</th><th>Signal</th><th>Detail</th><th>Points</th></tr>"
        "</thead><tbody>{}</tbody></table>{}",
        format_html_join("", "{}", ((row,) for row in rows)),
        note,
    )


@admin.register(FavorInvocation)
class FavorInvocationAdmin(admin.ModelAdmin):
    """One invocation of a being, read-only (#4333, #4520): the roll and the worn pieces
    that eased it, each with the signals that made it count."""

    list_display = ("character_sheet", "being", "outcome_tier", "worn_ease", "created_at")
    list_filter = ("being", "outcome_tier")
    search_fields = ("being__name", "character_sheet__character__db_key")
    fields = (
        "character_sheet",
        "being",
        "game_week",
        "outcome_tier",
        "bonus",
        "worn_ease",
        "player_line",
        "scene",
        "created_at",
        "worn_pieces",
    )
    readonly_fields = fields
    raw_id_fields = ("character_sheet", "scene")

    @admin.display(description="Worn pieces that counted")
    def worn_pieces(self, obj: FavorInvocation) -> SafeString:
        return worn_pieces_table(obj)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: FavorInvocation | None = None
    ) -> bool:
        del request, obj
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: FavorInvocation | None = None
    ) -> bool:
        del request, obj
        return False


@admin.register(BeingResonance)
class BeingResonanceAdmin(admin.ModelAdmin):
    list_display = ("being", "resonance", "tier")
    list_filter = ("being", "tier")
    search_fields = ("being__name", "resonance__name")


@admin.register(BeingNickname)
class BeingNicknameAdmin(admin.ModelAdmin):
    list_display = ("name", "being")
    list_filter = ("being",)
    search_fields = ("being__name", "name")


@admin.register(BeingRelationship)
class BeingRelationshipAdmin(admin.ModelAdmin):
    list_display = ("being_a", "being_b", "valence")
    list_filter = ("valence",)
    search_fields = ("being_a__name", "being_b__name")


@admin.register(WorshipFeastDay)
class WorshipFeastDayAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "ic_month", "ic_day")
    list_filter = ("being",)
    search_fields = ("name", "being__name")


@admin.register(WorshipGrant)
class WorshipGrantAdmin(admin.ModelAdmin):
    list_display = ("being", "amount", "granted_by", "reason", "created_at")
    list_filter = ("being",)
    raw_id_fields = ("granted_by",)


@admin.register(DevotionStanding)
class DevotionStandingAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "being",
        "favor",
        "lifetime_favor",
        "valence",
        "established_at",
        "released_at",
    )
    list_filter = ("being", "valence")
    raw_id_fields = ("character_sheet",)


@admin.register(WorshipDeclaration)
class WorshipDeclarationAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "public_being", "secret_being")
    raw_id_fields = ("character_sheet", "secret")


class MiracleAppliedConditionInline(admin.TabularInline):
    model = MiracleAppliedCondition
    formset = OneRowPerFormSet
    extra = 0


class MiracleDamageProfileInline(admin.TabularInline):
    model = MiracleDamageProfile
    extra = 0


@admin.register(Miracle)
class MiracleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "being",
        "resonance_pool_cost",
        "intervention_trigger",
        "favor_threshold",
        "is_active",
    )
    list_filter = ("being", "intervention_trigger", "is_active")
    search_fields = ("name",)
    inlines = [
        MiracleAppliedConditionInline,
        MiracleDamageProfileInline,
    ]


@admin.register(MiraclePerformance)
class MiraclePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "miracle",
        "being",
        "target_character",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )
    list_filter = ("being", "trigger_event")
    raw_id_fields = ("target_character", "scene")
    readonly_fields = (
        "miracle",
        "being",
        "target_character",
        "scene",
        "resonance_spent",
        "trigger_event",
        "created_at",
    )


@admin.register(DivineInterventionConfig)
class DivineInterventionConfigAdmin(admin.ModelAdmin):
    list_display = ("favor_threshold", "cooldown_hours", "min_pool_for_intervention")


@admin.register(ChosenFavorConfig)
class ChosenFavorConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "anima_recovery_threshold",
        "anima_recovery_bonus",
        "earn_bonus_percent",
        "invocation_ease_points",
    )
    readonly_fields = ("chosen_per_being",)
    fieldsets = (
        (
            "Anima recovery and ceremony edge",
            {
                "fields": (
                    "anima_recovery_threshold",
                    "anima_recovery_bonus",
                    "ceremony_edge_threshold",
                    "ceremony_edge_bonus",
                )
            },
        ),
        (
            "Favor: earning and invocation",
            {"fields": ("earn_bonus_percent", "invocation_ease_points", "chosen_per_being")},
        ),
    )

    @admin.display(description="Chosen per being")
    def chosen_per_being(self, obj: ChosenFavorConfig) -> str:
        """How many characters each being has as its Chosen (an active patronage)."""
        del obj  # The counts are game-wide; the singleton row is not read.
        rows = (
            DevotionStanding.objects.filter(valence__isnull=False, released_at__isnull=True)
            .values("being__name")
            .annotate(count=Count("id"))
            .order_by("being__name")
        )
        if not rows:
            return "No being has a Chosen yet."
        return " · ".join(f"{row['being__name']} {row['count']}" for row in rows)


class FavorOutcomeAwardInline(admin.TabularInline):
    """The outcome-keyed favor terms (#4333): invocation bonuses, closing awards."""

    model = FavorOutcomeAward
    formset = OneRowPerFormSet
    extra = 0
    fields = ("kind", "outcome_tier", "amount")
    ordering = ("kind", "-outcome_tier__success_level")
    verbose_name = "favor outcome award"
    verbose_name_plural = "Favor outcome awards: one table, two kinds"


#: DevotionConfig's difficulty choice field, relabelled with its points.
_BASE_DIFFICULTY_FIELD = "base_difficulty"
#: The example favor invocation modifier the read-only difficulty table shows.
_EXAMPLE_INVOCATION_MODIFIER = 15


def _band_label(points: int) -> str:
    from world.worship.invocation_services import band_for_points  # noqa: PLC0415

    return DifficultyChoice(band_for_points(points)).label


def invocation_difficulty_rows(config: DevotionConfig, chosen_ease: int) -> list[list[str]]:
    """The read-only "Resulting invocation difficulty" table (#4333, design 10).

    One row per favor band, one column per kind of character: a stranger, a
    holder of an example +15 favor invocation modifier, a Chosen, and a Chosen
    holding the modifier. Each cell is the difficulty band the eases add up to.
    """
    base = DIFFICULTY_VALUES[config.base_difficulty]
    low, high = config.favor_ease_low_threshold, config.favor_ease_high_threshold
    bands = (
        (f"1 to {low - 1}", 0),
        (f"{low} to {high - 1}", config.favor_ease_low_points),
        (f"{high} or more", config.favor_ease_high_points),
    )
    columns = (
        (0, 0),
        (0, _EXAMPLE_INVOCATION_MODIFIER),
        (chosen_ease, 0),
        (chosen_ease, _EXAMPLE_INVOCATION_MODIFIER),
    )
    return [
        [label]
        + [
            _band_label(max(base - favor_ease - chosen - modifier, MIN_DIFFICULTY_POINTS))
            for chosen, modifier in columns
        ]
        for label, favor_ease in bands
    ]


def invocations_last_week() -> str:
    """Invocations in the last finished game week, by surface and by outcome."""
    from world.game_clock.models import GameWeek  # noqa: PLC0415

    week = GameWeek.objects.filter(is_current=False).order_by("-started_at").first()
    if week is None:
        return "No finished game week yet."
    rows = FavorInvocation.objects.filter(game_week=week)
    total = rows.count()
    if not total:
        return "None."
    missions = rows.filter(mission_instance__isnull=False).count()
    outcomes = (
        rows.values("outcome_tier__name", "outcome_tier__success_level")
        .annotate(count=Count("id"))
        .order_by("-outcome_tier__success_level")
    )
    by_outcome = ", ".join(f"{row['outcome_tier__name']} {row['count']}" for row in outcomes)
    return (
        f"{total} (missions {missions}, scene checks and actions {total - missions}). "
        f"Outcomes: {by_outcome}."
    )


@admin.register(DevotionConfig)
class DevotionConfigAdmin(admin.ModelAdmin):
    """The favor terms every character shares (#4333): a singleton change form.

    Read-only context below the awards: the difficulty the eases add up to for a
    stranger, a favor invocation modifier holder and a Chosen at each favor band,
    and last week's invocations by outcome.
    """

    change_form_template = "admin/worship/devotionconfig/change_form.html"
    autocomplete_fields = ("invocation_check_type",)
    readonly_fields = ("eases_rule", "earning_rate_rule")
    inlines = (FavorOutcomeAwardInline,)
    fieldsets = (
        (
            "Invocation check",
            {
                "fields": (
                    "invocation_check_type",
                    "base_difficulty",
                    "eases_rule",
                    ("favor_ease_low_threshold", "favor_ease_low_points"),
                    ("favor_ease_high_threshold", "favor_ease_high_points"),
                    "invocations_per_week",
                )
            },
        ),
        (
            "Earning",
            {
                "fields": (
                    "earning_rate_rule",
                    ("favored_deed_percent", "associated_deed_percent"),
                    "weekly_deed_favor_cap",
                )
            },
        ),
        (
            "Sacrifices",
            {
                "description": (
                    "A sacrifice is a check eased by what the item means to the character "
                    "who gives it up. No number here reads an item's price."
                ),
                "fields": (
                    "sacrifice_min_carried_days",
                    "sacrifice_carried_days_per_point",
                    "sacrifice_carried_max_points",
                    "maker_tie_max_points",
                    "sacrifice_ease_per_point",
                    "sacrifices_per_week",
                    "odds_reference_roller_points",
                ),
            },
        ),
        (
            "Made and shown",
            {
                "description": (
                    "What a commissioned piece's dedication, lineage and showings add to its "
                    "meaning. No number here reads an item's price or a commission's fee."
                ),
                "fields": (
                    "made_for_max_points",
                    "made_from_max_points",
                    "shown_window_weeks",
                    "shown_engagements_per_point",
                    "shown_max_points",
                ),
            },
        ),
        (
            "Worn pieces and invocations",
            {
                "description": (
                    "What the pieces a character wears do when she calls on a being whose "
                    "favored facet they carry (set per facet on the Being Service builder). "
                    "A piece with no meaning adds nothing, whatever it cost."
                ),
                "fields": (
                    "worn_item_max_points",
                    "worn_items_counted",
                    "resonance_fed_per_point",
                    "resonance_fed_max_points",
                    "invocation_ease_per_keepsake_point",
                    "invocation_meaning_ease_max",
                ),
            },
        ),
        (
            "Keepsakes and trophies",
            {
                "description": (
                    "A keepsake counts by what it stands for, never by the words its keeper "
                    "wrote. A trophy is an item won on a deed, scored by the deed's legend."
                ),
                "fields": (
                    "keepsake_wait_days",
                    "keepsakes_per_character",
                    "keepsake_max_points",
                    "keepsake_deed_legend_per_point",
                    "trophy_legend_per_point",
                    "trophy_max_points",
                ),
            },
        ),
        (
            "Rites and requests",
            {
                "description": (
                    "Items given up during a rite ease its roll. A requested item is a cheap "
                    "item a pledge or rite asks for, set on the Being Service builder."
                ),
                "fields": (
                    "rite_ease_per_point",
                    "rite_items_counted",
                    "requested_item_max_points",
                    "requested_item_max_value",
                ),
            },
        ),
    )

    @admin.display(description="Eases")
    def eases_rule(self, obj: DevotionConfig) -> str:
        del obj
        return (
            "All eases add, in points; 15 points is one band; never below Trivial (15). "
            "The Chosen ease is on Chosen favor config; favor invocation modifiers come "
            "from the modifier system."
        )

    @admin.display(description="Earning rate")
    def earning_rate_rule(self, obj: DevotionConfig) -> str:
        del obj
        return (
            "100% plus additive bonuses: the Chosen bonus (Chosen favor config) and favor "
            "earning modifiers (modifier system). Every favor a character earns with a "
            "being is scaled by it."
        )

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        """Show each difficulty band with its points ("Daunting (75 points)")."""
        if db_field.name == _BASE_DIFFICULTY_FIELD:
            kwargs["choices"] = [
                (value, f"{label} ({DIFFICULTY_VALUES[value]} points)")
                for value, label in DifficultyChoice.choices
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return not DevotionConfig.objects.exists()

    def has_delete_permission(
        self, request: HttpRequest, obj: DevotionConfig | None = None
    ) -> bool:
        del request, obj  # The singleton is never deleted.
        return False

    def changelist_view(
        self, request: HttpRequest, extra_context: dict | None = None
    ) -> HttpResponse:
        """The singleton has no list: open its one row (creating it if needed)."""
        from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

        del request, extra_context
        config = get_devotion_config()
        return HttpResponseRedirect(reverse("admin:arxii_devotionconfig_change", args=(config.pk,)))

    def render_change_form(  # noqa: PLR0913 - Django's own signature
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """Adds the read-only difficulty table and last week's counts."""
        from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

        if obj is not None:
            context["difficulty_headers"] = (
                "Favor",
                "Stranger",
                f"+{_EXAMPLE_INVOCATION_MODIFIER} invocation modifier",
                "Chosen",
                f"Chosen and +{_EXAMPLE_INVOCATION_MODIFIER} modifier",
            )
            context["difficulty_rows"] = invocation_difficulty_rows(
                obj, get_chosen_favor_config().invocation_ease_points
            )
            context["invocations_last_week"] = invocations_last_week()
            context["odds_rows"] = sacrifice_odds_rows()
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )


def sacrifice_odds_rows() -> list[tuple[str, str, str, str]]:
    """Rows for the Devotion config's read-only "Odds at these settings" table: for a
    reference roller, the meaning points, the difficulty, each outcome's chance and the
    Success-or-better total, all read from the real result charts (#4500)."""
    from world.worship.sacrifice_services import sacrifice_odds_bands  # noqa: PLC0415

    rows = []
    for band in sacrifice_odds_bands():
        if band.last_points is None:
            label = f"{band.first_points} or more points"
        elif band.last_points == band.first_points:
            label = f"{band.first_points} point{'s' if band.first_points != 1 else ''}"
        else:
            label = f"{band.first_points} to {band.last_points} points"
        odds = band.odds
        chances = ", ".join(f"{line.percent}% {line.outcome_name}" for line in odds.lines)
        rows.append((label, str(odds.difficulty_points), chances, f"{odds.success_or_better}%"))
    return rows


@admin.register(RiteKind)
class RiteKindAdmin(admin.ModelAdmin):
    list_display = ("name", "tier")
    list_filter = ("tier",)
    search_fields = ("name",)


@admin.register(WorshipRite)
class WorshipRiteAdmin(admin.ModelAdmin):
    list_display = ("name", "being", "kind", "check_type", "resonance", "is_active")
    list_filter = ("kind__tier", "is_active")
    search_fields = ("name", "being__name")
    autocomplete_fields = ("being", "check_type")
    raw_id_fields = ("resonance",)


@admin.register(WorshipRiteTierAward)
class WorshipRiteTierAwardAdmin(admin.ModelAdmin):
    list_display = ("tier", "outcome_tier", "resonance_amount", "favor_amount")
    list_filter = ("tier",)


@admin.register(WorshipRitePerformance)
class WorshipRitePerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "character_sheet",
        "rite",
        "outcome_tier",
        "resonance_granted",
        "favor_granted",
        "performed_at",
    )
    list_filter = ("rite__kind__tier",)
    raw_id_fields = ("character_sheet", "rite", "game_week", "scene", "ceremony")


@admin.register(Relic)
class RelicAdmin(admin.ModelAdmin):
    list_display = ("item_instance", "being", "invocation_points", "created_at")
    search_fields = ("being__name", "item_instance__custom_name", "item_instance__template__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("item_instance",)
    fields = ("being", "item_instance", "invocation_points", "lore")


@admin.register(ShrineDetails)
class ShrineDetailsAdmin(admin.ModelAdmin):
    list_display = ("feature_instance", "being", "consecration_points", "created_at")
    search_fields = ("being__name",)
    autocomplete_fields = ("being",)
    raw_id_fields = ("feature_instance", "founder_character_sheet")


@admin.register(TempleDedication)
class TempleDedicationAdmin(admin.ModelAdmin):
    list_display = ("building", "being", "consecration_points", "dedicated_at", "dissolved_at")
    list_filter = ("being",)
    search_fields = ("being__name", "building__area__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("building", "founder_character_sheet")


@admin.register(ConsecrationTier)
class ConsecrationTierAdmin(admin.ModelAdmin):
    list_display = ("scope", "name", "min_points", "bonus_percent")
    list_filter = ("scope",)


@admin.register(Prayer)
class PrayerAdmin(admin.ModelAdmin):
    """The freeform channel staff read (#3779): newest first, answerable from the vision admin."""

    list_display = (
        "prayed_at",
        "character_sheet",
        "being",
        "devotion_granted",
        "dire_straits",
        "intervention",
    )
    list_filter = ("being", "dire_straits")
    search_fields = ("text", "character_sheet__character__db_key", "being__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("character_sheet", "room_profile", "game_week", "intervention")
    readonly_fields = ("prayed_at",)


@admin.register(Vision)
class VisionAdmin(admin.ModelAdmin):
    list_display = ("sent_at", "recipient", "being", "reveal_source", "sent_by", "prayer")
    list_filter = ("being", "reveal_source")
    search_fields = ("body", "recipient__character__db_key", "being__name")
    autocomplete_fields = ("being",)
    raw_id_fields = ("recipient", "sent_by", "prayer", "clue", "episode", "message")
    readonly_fields = ("sent_at", "resonance_spent")


@admin.register(Pledge)
class PledgeAdmin(admin.ModelAdmin):
    """Pledge types (#4333 slice 2), listed here and written on the Being Service
    builder: the one place a staff-owned being's pledge types are authored (Ruling 8).
    The change form's object tool opens the being's builder."""

    list_display = ("name", "being", "favor_target", "span_weeks", "closing_rite", "is_active")
    list_filter = ("being", "is_active")
    search_fields = ("name", "being__name")
    readonly_fields = (
        "being",
        "name",
        "description",
        "favor_target",
        "span_weeks",
        "closing_rite",
        "is_active",
        "service_builder",
    )
    fields = readonly_fields

    @admin.display(description="Edit")
    def service_builder(self, obj: Pledge) -> str:
        from django.utils.html import format_html  # noqa: PLC0415

        url = reverse("admin_being_service", args=[obj.being_id])
        return format_html('<a href="{}">Open the Being Service builder</a>', url)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False


class PledgeCreditInline(admin.TabularInline):
    model = PledgeCredit
    extra = 0
    can_delete = False
    fields = ("source", "base", "earning_rate_percent", "credited", "game_week", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False


@admin.register(PledgeDetails)
class PledgeDetailsAdmin(admin.ModelAdmin):
    """Characters' pledges (#4333 slice 2), read-only: each one's credits, attempts
    and closing rite. Pledges are opened, credited and closed only through play."""

    list_display = ("character_sheet", "pledge", "project", "close_attempts", "created_at")
    list_filter = ("pledge__being",)
    raw_id_fields = ("character_sheet", "project", "prayer", "closing_performance")
    readonly_fields = (
        "project",
        "character_sheet",
        "pledge",
        "prayer",
        "closing_performance",
        "close_attempts",
        "created_at",
    )
    inlines = (PledgeCreditInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False


class AnswerSacrificeLineInline(admin.TabularInline):
    model = AnswerSacrificeLine
    formset = OneRowPerFormSet
    extra = 0
    fields = ("facet", "text")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    """Answers (#4333 slice 3), listed here and written on the Answer builder: the one
    place a staff-owned being's answers are authored (Ruling 8). The change form is
    read-only and opens the builder at the answer's cell. Registered so the builder's
    clue and pool pickers can use admin's autocomplete for this model's fields."""

    list_display = ("being", "pledge", "outcome_tier", "weight", "conceals_source", "is_active")
    list_filter = ("being", "outcome_tier", "is_active")
    search_fields = ("being__name", "pledge__name", "delay_text", "answer_text")
    raw_id_fields = ("fact_clue", "cost_pool", "follow_up_clue")
    readonly_fields = (
        "being",
        "pledge",
        "outcome_tier",
        "delay_text",
        "answer_text",
        "fact_text",
        "fact_clue",
        "cost_text",
        "cost_pool",
        "follow_up_text",
        "follow_up_clue",
        "onlooker_line",
        "conceals_source",
        "weight",
        "is_active",
        "answer_builder",
    )
    fields = readonly_fields
    inlines = (AnswerSacrificeLineInline,)

    @admin.display(description="Edit")
    def answer_builder(self, obj: Answer) -> str:
        from urllib.parse import urlencode  # noqa: PLC0415

        from django.utils.html import format_html  # noqa: PLC0415

        query = urlencode(
            {
                "pledge": obj.pledge_id or "none",
                "tier": obj.outcome_tier_id,
                "answer": obj.pk,
            }
        )
        url = f"{reverse('admin_answer_builder', args=[obj.being_id])}?{query}"
        return format_html('<a href="{}">Open the Answer builder</a>', url)

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False


@admin.register(PendingAnswer)
class PendingAnswerAdmin(admin.ModelAdmin):
    """Answers held until the being's worship pool can pay (#4333 slice 3), read-only.
    The daily tick delivers them; staff see them here and on the being's dashboard."""

    list_display = ("character_sheet", "answer", "pledge_details", "created_at")
    list_filter = ("answer__being",)
    raw_id_fields = ("character_sheet", "answer", "pledge_details")
    readonly_fields = ("character_sheet", "answer", "pledge_details", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        del request, obj
        return False
