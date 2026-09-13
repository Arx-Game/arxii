"""Admin for the `npc_services` app (#3428, #3831).

``ClueRevealOfferDetails`` was the first per-kind details model registered — it is
structurally the same kind of "clue placement" row as ``RoomClue``/``ClueTrigger``/
``ItemClueTrigger`` (`world.clues.admin`), which already use Django admin as a staff
authoring surface for placing an existing clue somewhere in the world. #3831 (staff
cannot configure a table that has no admin page) then registered the rest of this
app's authored/configuration tables: every other `NPCServiceOffer` kind's per-kind
details model, `NPCRole`/`NPCServiceOffer` themselves, name/personality/staffing
vocabulary, reaction lines, and the regard-seed/regard-event-config tables.
"""

from django.contrib import admin

from world.npc_services.models import (
    ClueRevealOfferDetails,
    CourtGrantOfferDetails,
    DistinctionRegardSeed,
    LoanOfferDetails,
    MissionOfferDetails,
    NameCulture,
    NameCultureEntry,
    NPCReactionLine,
    NPCRole,
    NPCServiceOffer,
    PermitOfferDetails,
    PersonalityTrait,
    ProfileRecordingOfferDetails,
    RegardEventConfig,
    StaffingProfile,
    StaffingProfileLine,
    StylingOfferDetails,
    TrainOfferDetails,
)


@admin.register(ClueRevealOfferDetails)
class ClueRevealOfferDetailsAdmin(admin.ModelAdmin):
    """Staff view of which clue an NPC-role offer reveals (data, not code)."""

    autocomplete_fields = ["offer", "clue"]
    list_display = ["offer", "clue"]
    search_fields = ["clue__name", "offer__label", "offer__role__name"]


@admin.register(NPCRole)
class NPCRoleAdmin(admin.ModelAdmin):
    """#3831 - a kind of NPC role staff bundle offers onto."""

    list_display = ["name", "faction_affiliation", "teaches_tradition", "is_active"]
    list_filter = ["is_active", "faction_affiliation", "teaches_tradition"]
    search_fields = ["name", "description"]
    list_select_related = ["faction_affiliation", "teaches_tradition"]
    autocomplete_fields = ["faction_affiliation", "teaches_tradition"]


@admin.register(NPCServiceOffer)
class NPCServiceOfferAdmin(admin.ModelAdmin):
    """#3831 - one offerable thing on an NPC role, of a specific kind."""

    list_display = ["role", "kind", "label", "draw_mode", "is_final"]
    list_filter = ["kind", "draw_mode", "is_final"]
    search_fields = ["label", "role__name"]
    list_select_related = ["role", "check_type"]
    autocomplete_fields = ["role", "check_type"]


@admin.register(MissionOfferDetails)
class MissionOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - mission-specific knobs for a kind=MISSION offer."""

    list_display = ["offer", "mission_template", "weight", "draw_priority"]
    list_filter = ["draw_priority"]
    search_fields = ["offer__label", "mission_template__name"]
    list_select_related = ["offer", "role"]
    autocomplete_fields = ["offer", "role"]
    raw_id_fields = ["mission_template", "source_beat", "target_project"]


@admin.register(PermitOfferDetails)
class PermitOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - which BuildingKind a kind=PERMIT offer authorizes, and its cost."""

    list_display = ["offer", "building_kind", "default_max_target_size", "permit_cost_currency"]
    search_fields = ["offer__label", "building_kind__name"]
    autocomplete_fields = ["offer", "default_approved_wards"]
    raw_id_fields = ["building_kind"]


@admin.register(LoanOfferDetails)
class LoanOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - fixed loan terms for a kind=LOAN offer."""

    list_display = ["offer", "principal", "interest_bps_monthly", "creditor_organization"]
    search_fields = ["offer__label", "creditor_organization__name"]
    list_select_related = ["offer", "creditor_organization"]
    autocomplete_fields = ["offer", "creditor_organization"]


@admin.register(TrainOfferDetails)
class TrainOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - one teachable technique on a kind=TRAIN offer."""

    list_display = ["offer", "technique", "learn_ap_cost", "gold_cost"]
    search_fields = ["offer__label", "technique__name"]
    list_select_related = ["offer", "technique"]
    autocomplete_fields = ["offer", "technique"]


@admin.register(CourtGrantOfferDetails)
class CourtGrantOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - the Court covenant a kind=COURT_GRANT petition offer raises."""

    list_display = ["offer", "covenant"]
    search_fields = ["offer__label", "covenant__name"]
    list_select_related = ["offer", "covenant"]
    autocomplete_fields = ["offer", "covenant"]


@admin.register(StylingOfferDetails)
class StylingOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - the cosmetic trait+option a kind=STYLING offer restyles to."""

    list_display = ["offer", "trait", "target_option", "price_coppers"]
    list_filter = ["trait"]
    search_fields = ["offer__label", "trait__name", "target_option__name"]
    list_select_related = ["offer", "trait", "target_option"]
    autocomplete_fields = ["offer", "trait", "target_option"]


@admin.register(ProfileRecordingOfferDetails)
class ProfileRecordingOfferDetailsAdmin(admin.ModelAdmin):
    """#3831 - the Archive-sitting price for a kind=PROFILE_RECORDING offer."""

    list_display = ["offer", "price_coppers"]
    search_fields = ["offer__label"]
    autocomplete_fields = ["offer"]


class NameCultureEntryInline(admin.TabularInline):
    """One name in a culture's pool, weighted for random draw (#3831)."""

    model = NameCultureEntry
    extra = 1


@admin.register(NameCulture)
class NameCultureAdmin(admin.ModelAdmin):
    """#3831 - a pool of names reinforcing a region's (or society's) theme."""

    list_display = ["name", "area", "society"]
    list_filter = ["area", "society"]
    search_fields = ["name"]
    list_select_related = ["area", "society"]
    autocomplete_fields = ["area", "society"]
    inlines = [NameCultureEntryInline]


@admin.register(NameCultureEntry)
class NameCultureEntryAdmin(admin.ModelAdmin):
    """#3831 - one name in a culture's pool, weighted for random draw."""

    list_display = ["culture", "part", "value", "weight"]
    list_filter = ["part"]
    search_fields = ["value", "culture__name"]
    list_select_related = ["culture"]
    autocomplete_fields = ["culture"]


@admin.register(PersonalityTrait)
class PersonalityTraitAdmin(admin.ModelAdmin):
    """#3831 - an authored like/dislike axis for instantiated NPCs."""

    list_display = ["name", "eased_check", "ease_magnitude", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    list_select_related = ["eased_check"]
    autocomplete_fields = ["eased_check"]


class StaffingProfileLineInline(admin.TabularInline):
    """One role the venue keeps staffed (#3831)."""

    model = StaffingProfileLine
    extra = 1


@admin.register(StaffingProfile)
class StaffingProfileAdmin(admin.ModelAdmin):
    """#3831 - default staffing for buildings of a kind."""

    list_display = ["building_kind"]
    search_fields = ["building_kind__name"]
    raw_id_fields = ["building_kind"]
    inlines = [StaffingProfileLineInline]


@admin.register(StaffingProfileLine)
class StaffingProfileLineAdmin(admin.ModelAdmin):
    """#3831 - one role a staffing profile keeps staffed."""

    list_display = ["profile", "role"]
    search_fields = ["profile__building_kind__name", "role__name"]
    list_select_related = ["profile", "role"]
    autocomplete_fields = ["profile", "role"]


@admin.register(NPCReactionLine)
class NPCReactionLineAdmin(admin.ModelAdmin):
    """#3831 - a banded, data-authored NPC reaction line."""

    list_display = ["role", "functionary", "metric", "band_floor"]
    list_filter = ["metric"]
    search_fields = ["role__name", "template"]
    list_select_related = ["role"]
    autocomplete_fields = ["role"]
    raw_id_fields = ["functionary"]


@admin.register(DistinctionRegardSeed)
class DistinctionRegardSeedAdmin(admin.ModelAdmin):
    """#3831 - a Distinction pre-attaching a bond to a specific notable NPC."""

    list_display = ["distinction", "npc_persona", "starting_value"]
    search_fields = ["distinction__name", "npc_persona__name", "reason"]
    list_select_related = ["distinction", "npc_persona"]
    autocomplete_fields = ["distinction", "npc_persona"]


@admin.register(RegardEventConfig)
class RegardEventConfigAdmin(admin.ModelAdmin):
    """#3831 - the singleton NpcRegardEvent buildup tuning dials."""

    list_display = [
        "max_event_delta",
        "combat_defeat_amount",
        "combat_harm_amount",
        "story_vital_threshold",
    ]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not RegardEventConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False
