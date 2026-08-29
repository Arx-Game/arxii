"""Admin for the `npc_services` app (#3428).

Every other ``NPCServiceOffer`` kind's per-kind details model (Permit,
Mission, Loan, ...) is authored through the Mission Studio React editor
(`frontend/src/npc_services/pages/NPCRoleEditorPage.tsx`), and none of them
carry a Django admin registration — `NPCServiceOffer` itself has none either.
``ClueRevealOfferDetails`` gets one anyway: it is structurally the same kind
of "clue placement" row as ``RoomClue``/``ClueTrigger``/``ItemClueTrigger``
(`world.clues.admin`), which already use Django admin as a staff authoring
surface for placing an existing clue somewhere in the world. This registration
follows that idiom rather than growing a first NPCServiceOffer-wide admin
surface, which is out of this issue's scope.
"""

from django.contrib import admin

from world.npc_services.models import ClueRevealOfferDetails


@admin.register(ClueRevealOfferDetails)
class ClueRevealOfferDetailsAdmin(admin.ModelAdmin):
    """Staff view of which clue an NPC-role offer reveals (data, not code)."""

    # `offer` (NPCServiceOffer) carries no ModelAdmin of its own anywhere in the
    # codebase (Django admin.E039 requires autocomplete_fields' target to be
    # registered), so it gets the registration-agnostic raw-id widget instead.
    autocomplete_fields = ["clue"]
    raw_id_fields = ["offer"]
    list_display = ["offer", "clue"]
    search_fields = ["clue__name", "offer__label", "offer__role__name"]
