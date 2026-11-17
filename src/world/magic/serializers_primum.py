"""Serializers for the Primum a character senses and can extract where she stands (#5125).

``primum_block`` is the viewer-relative ``primum`` block of the ``room_state`` frame: the
substances she senses here (a row each, for the "You sense" panel), the one-sentence line the
``look`` command also ends with, and what she can extract. It reads only what the viewer
perceives, so it never names a substance she has not sensed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rest_framework import serializers

from world.magic.services.harvest import harvest_offers
from world.magic.services.primum import primum_steps
from world.magic.services.primum_perception import (
    perceived_substance_ids,
    sense_line,
    sensed_primum,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


class PrimumSenseSerializer(serializers.Serializer):
    """One substance the viewer senses in this place, and the step it reads at."""

    substance_id = serializers.IntegerField(read_only=True)
    substance_name = serializers.CharField(read_only=True)
    step_name = serializers.CharField(read_only=True)
    from_sighting = serializers.BooleanField(
        read_only=True,
        help_text="Sensed through a sighting here, not her own gift: gone when she leaves.",
    )


class HarvestOfferSerializer(serializers.Serializer):
    """One Primum the viewer can extract here: from the lair, or from a slain creature."""

    substance_id = serializers.IntegerField(read_only=True)
    substance_name = serializers.CharField(read_only=True)
    source = serializers.CharField(read_only=True, help_text="place | creature.")
    opponent_id = serializers.IntegerField(
        read_only=True, allow_null=True, help_text="The slain foe's pk; null for a lair."
    )
    opponent_name = serializers.CharField(read_only=True)
    step_name = serializers.CharField(read_only=True)
    check_name = serializers.CharField(
        read_only=True, help_text="The harvest check she rolls; empty while none is set."
    )
    ap_cost = serializers.IntegerField(
        read_only=True, help_text="Action points one attempt costs, good roll or bad."
    )


class OpponentHarvestOfferSerializer(HarvestOfferSerializer):
    """A slain foe's offer to one character: which character presses Harvest."""

    character_id = serializers.IntegerField(
        read_only=True, help_text="The played character this offer belongs to."
    )


class PrimumBlockSerializer(serializers.Serializer):
    """The ``primum`` block of a ``room_state`` frame, for one viewer."""

    sensed = PrimumSenseSerializer(many=True, read_only=True)
    line = serializers.CharField(read_only=True, help_text="The look sentence; empty if none.")
    harvestable = HarvestOfferSerializer(many=True, read_only=True)


def primum_block(character: ObjectDB, room: ObjectDB) -> dict[str, Any]:  # noqa: OBJECTDB_PARAM - a character and a room
    """What ``character`` senses in ``room`` and can extract there, as the frame carries it."""
    perceived = perceived_substance_ids(character, room)
    steps = primum_steps()
    senses = sensed_primum(character, room, perceived=perceived, steps=steps)
    # A dreamside viewer's room is the dream, not the place she stands: nothing to extract.
    offers = (
        harvest_offers(character, perceived=perceived, steps=steps)
        if room == character.location
        else []
    )
    return dict(
        PrimumBlockSerializer(
            {
                "sensed": senses,
                "line": sense_line(senses),
                "harvestable": offers,
            }
        ).data
    )
