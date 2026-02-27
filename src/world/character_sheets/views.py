"""
Views for the character sheets API.
"""

from django.db.models import QuerySet
from django.db.models.query import Prefetch
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from world.character_sheets.serializers import CharacterSheetSerializer
from world.distinctions.models import CharacterDistinction
from world.forms.models import CharacterForm, CharacterFormValue, FormType
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    MotifResonance,
    MotifResonanceAssociation,
)
from world.progression.models import CharacterPathHistory
from world.roster.models import RosterEntry
from world.skills.models import CharacterSkillValue
from world.traits.models import CharacterTraitValue, TraitType


class CharacterSheetViewSet(RetrieveModelMixin, GenericViewSet):
    """
    Read-only detail endpoint for character sheets, keyed by RosterEntry pk.

    Returns character sheet data for a single roster entry. The response
    includes a `can_edit` flag based on whether the requesting user is
    the original creator or staff.
    """

    serializer_class = CharacterSheetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    def get_queryset(self) -> QuerySet[RosterEntry]:
        """Return roster entries with related data for character sheets."""
        return RosterEntry.objects.select_related(
            "character",
            # CharacterSheet FK lookups
            "character__sheet_data__gender",
            "character__sheet_data__species",
            "character__sheet_data__heritage",
            "character__sheet_data__family",
            "character__sheet_data__tarot_card",
            "character__sheet_data__origin_realm",
            "character__sheet_data__build",
            # Magic: aura (OneToOne to ObjectDB directly)
            "character__aura",
            # Magic: anima ritual (OneToOne to CharacterSheet)
            "character__sheet_data__anima_ritual__stat",
            "character__sheet_data__anima_ritual__skill__trait",
            "character__sheet_data__anima_ritual__resonance",
        ).prefetch_related(
            # can_edit check
            "tenures__player_data__account",
            # Path history (newest first for latest-path lookup)
            Prefetch(
                "character__path_history",
                queryset=(
                    CharacterPathHistory.objects.select_related("path").order_by("-selected_at")
                ),
            ),
            # TRUE forms with their trait values
            Prefetch(
                "character__forms",
                queryset=CharacterForm.objects.filter(form_type=FormType.TRUE),
            ),
            Prefetch(
                "character__forms__values",
                queryset=(CharacterFormValue.objects.select_related("trait", "option")),
            ),
            # Stats: trait values filtered to stat type
            Prefetch(
                "character__trait_values",
                queryset=(
                    CharacterTraitValue.objects.filter(
                        trait__trait_type=TraitType.STAT
                    ).select_related("trait")
                ),
            ),
            # Skills: skill values with skill and trait for name/category
            Prefetch(
                "character__skill_values",
                queryset=CharacterSkillValue.objects.select_related("skill__trait"),
            ),
            # Specializations: values with specialization for name and parent_skill_id
            "character__specialization_values__specialization",
            # Distinctions with their definition
            Prefetch(
                "character__distinctions",
                queryset=CharacterDistinction.objects.select_related("distinction"),
            ),
            # Magic: character gifts with gift resonances
            Prefetch(
                "character__sheet_data__character_gifts",
                queryset=CharacterGift.objects.select_related("gift"),
            ),
            "character__sheet_data__character_gifts__gift__resonances",
            # Magic: character techniques with technique details
            Prefetch(
                "character__sheet_data__character_techniques",
                queryset=CharacterTechnique.objects.select_related(
                    "technique__gift",
                    "technique__style",
                ),
            ),
            # Magic: motif with resonances and facet assignments
            Prefetch(
                "character__sheet_data__motif__resonances",
                queryset=MotifResonance.objects.select_related("resonance"),
            ),
            Prefetch(
                "character__sheet_data__motif__resonances__facet_assignments",
                queryset=MotifResonanceAssociation.objects.select_related("facet"),
            ),
        )
