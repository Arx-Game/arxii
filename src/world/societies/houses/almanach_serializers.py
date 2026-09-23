"""DRF serializers for the Almanach de Catenys API (#3983).

Mirrors ``world.societies.houses.almanach_reads``: ``LadderRow``/``LadderPayload``
are dataclasses so their fields are declared explicitly; ``HouseDocument``'s
sections are already plain dicts/lists of dicts (built once in the read layer)
so those ride ``DictField``/``ListField(child=DictField())`` rather than
re-declaring every key — except ``house``, which gets its own nested
serializer so the schema documents its keys (spec decision, #3983 Task 5).
"""

from __future__ import annotations

from rest_framework import serializers

from world.realms.models import Realm
from world.societies.houses.almanach_reads import ladder_for_realm
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import LandShape
from world.societies.models import Organization


def _full_unclaimed_by_tier(counts: dict[str, int]) -> dict[str, int]:
    """Zero-fill every ladder tier (``almanach_reads`` only emits a key for
    a tier with at least one unclaimed rung) — the API's per-tier summary
    always has all six columns, never a missing key for "none unclaimed"."""
    return {tier: counts.get(tier, 0) for tier in TitleTier.values}


class LadderRowSerializer(serializers.Serializer):
    """One rung of the realm ladder (mirrors ``almanach_reads.LadderRow``)."""

    title_id = serializers.IntegerField()
    name = serializers.SerializerMethodField()
    is_defined = serializers.BooleanField()
    tier = serializers.CharField()
    level = serializers.IntegerField()
    parent_title_id = serializers.IntegerField(allow_null=True)
    house_id = serializers.IntegerField(allow_null=True)
    house_name = serializers.CharField(allow_blank=True)
    state = serializers.CharField()
    is_seat_of = serializers.CharField(allow_blank=True)
    sworn_to = serializers.CharField(allow_blank=True)
    demesne = serializers.IntegerField()
    vassals = serializers.IntegerField()
    claimable = serializers.BooleanField()
    seat_domain_id = serializers.IntegerField(allow_null=True)
    comes_with = serializers.CharField(allow_blank=True)
    chain_top_id = serializers.IntegerField()
    claimant_name = serializers.CharField(allow_blank=True)

    def get_name(self, obj) -> str:
        """The dataclass keeps the raw (possibly empty) name; the API
        renders an undefined rung's name as "Undefined" for display."""
        return obj.name if obj.is_defined else "Undefined"


class LadderPayloadSerializer(serializers.Serializer):
    """A realm's whole ladder (mirrors ``almanach_reads.LadderPayload``)."""

    rows = LadderRowSerializer(many=True)
    unclaimed_by_tier = serializers.SerializerMethodField()

    def get_unclaimed_by_tier(self, obj) -> dict[str, int]:
        return _full_unclaimed_by_tier(obj.unclaimed_by_tier)


class AlmanachRealmSerializer(serializers.ModelSerializer):
    """A realm as the Almanach's realm picker lists it, plus its unclaimed
    counts. Computing a full ladder per row is one extra Title+Area query
    pair per realm — acceptable at realm scale (six realms today; #3983
    Task 5 decision) but not something to do per-row on a large list."""

    unclaimed_by_tier = serializers.SerializerMethodField()

    class Meta:
        model = Realm
        fields = ["id", "name", "formal_name", "default_tithe_pct", "unclaimed_by_tier"]

    def get_unclaimed_by_tier(self, obj: Realm) -> dict[str, int]:
        return _full_unclaimed_by_tier(ladder_for_realm(obj).unclaimed_by_tier)


class AlmanachHouseSummarySerializer(serializers.ModelSerializer):
    """A house row in the Almanach's house list/detail (not the document).

    ``family_id`` (nullable, read-only — the raw FK column,
    ``Organization.family_id``, needs no join) is what a "born into" picker
    needs for ``almanach_edit_kin``'s ``born_into_family_id`` kwarg — that
    kwarg takes a ``Family`` pk, never this row's own ``Organization`` id,
    and this is the only house-summary surface the Almanach exposes for a
    house pick (#3983 Task 10 fold-in).
    """

    family_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "house_state", "published_at", "family_id"]


class AlmanachSuccessionLawSerializer(serializers.Serializer):
    """``house.default_succession_law`` on the document (mirrors
    ``almanach_reads._house_payload``'s ``law_payload``)."""

    name = serializers.CharField()
    codex_entry_id = serializers.IntegerField(allow_null=True)


class AlmanachHouseAspectSerializer(serializers.Serializer):
    definition = serializers.CharField()
    option = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class AlmanachHouseFeatureSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class AlmanachHouseOfficeSerializer(serializers.Serializer):
    slug = serializers.CharField()
    title = serializers.CharField()
    holder_name = serializers.CharField(allow_blank=True)


class AlmanachHouseDocumentHouseSerializer(serializers.Serializer):
    """The document's ``house`` section (mirrors ``_house_payload``) — the
    only section given its own nested serializer, per the #3983 Task 5
    decision, so the schema documents its keys instead of a bare dict."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    words = serializers.CharField(allow_blank=True)
    colors = serializers.CharField(allow_blank=True)
    sigil_description = serializers.CharField(allow_blank=True)
    house_state = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    particle_example = serializers.CharField(allow_blank=True)
    default_succession_law = AlmanachSuccessionLawSerializer(allow_null=True)
    aspects = AlmanachHouseAspectSerializer(many=True)
    features = AlmanachHouseFeatureSerializer(many=True)
    offices = AlmanachHouseOfficeSerializer(many=True)


class HouseDocumentSerializer(serializers.Serializer):
    """The Almanach house document (mirrors ``almanach_reads.HouseDocument``).

    ``family``/``household``/``realm``/``lands``/``estate`` are already
    plain dicts/lists of dicts in the read layer, so they ride
    ``DictField``/``ListField(child=DictField())`` rather than re-declaring
    every key here.
    """

    house = AlmanachHouseDocumentHouseSerializer()
    family = serializers.DictField()
    household = serializers.ListField(child=serializers.DictField())
    realm = serializers.DictField()
    lands = serializers.DictField()
    estate = serializers.ListField(child=serializers.DictField())


class LandShapeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandShape
        fields = ["id", "name", "description", "sort_order"]


class RealmCharterParticleSerializer(serializers.Serializer):
    """Mirrors ``almanach_reads.charter_for_realm``'s ``particle`` dict."""

    born = serializers.CharField(allow_blank=True)
    taken_in = serializers.CharField(allow_blank=True)


class RealmCharterSerializer(serializers.Serializer):
    """The realm's charter defaults for the founder ladder (mirrors
    ``almanach_reads.RealmCharter``, #3983 Plan B Task 3); ``succession_law``
    reuses ``AlmanachSuccessionLawSerializer``'s ``{name, codex_entry_id}``
    shape, the same one the house document already renders."""

    succession_law = AlmanachSuccessionLawSerializer(allow_null=True)
    particle = RealmCharterParticleSerializer()
    quiddity_prompt = serializers.CharField(allow_blank=True)
    capital_name = serializers.CharField(allow_blank=True)
