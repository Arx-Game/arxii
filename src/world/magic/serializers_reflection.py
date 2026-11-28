"""Serializers for reflections (#5124): the "Reflecting on" row's choices, and the three
optional fields a pose or a journal entry carries to say what it reflects on."""

from __future__ import annotations

from rest_framework import serializers

from world.magic.constants import ReflectionChoice, ReflectionTargetKind, SineatingPoseRole


class ReflectionFieldsMixin(serializers.Serializer):
    """The optional reflection a pose or journal entry carries.

    ``reflect_choice`` with exactly one of ``reflect_grant_id`` (a deed), ``reflect_resonance_id``
    (the resonance unsettling the writer) or ``reflect_tether_id`` (a burden: the id a burden
    option carries, the Sineater's own side of the tether). All four omitted means no
    reflection. ``reflect_choice`` is Embrace or Disown for a deed or the resonance and
    Absolve, Condemn or Succumb for a burden. Whether the target is the writer's to reflect on,
    and that the choice fits it, is checked by the action.
    """

    reflect_choice = serializers.ChoiceField(choices=ReflectionChoice.choices, required=False)
    reflect_grant_id = serializers.IntegerField(required=False, allow_null=True)
    reflect_resonance_id = serializers.IntegerField(required=False, allow_null=True)
    reflect_tether_id = serializers.IntegerField(required=False, allow_null=True)


class SineatingFieldsMixin(serializers.Serializer):
    """The optional Sineating a pose carries (#5177).

    ``sineating_role`` (``entreat``: the Sinner's plea, or ``perform``: the Sineater's ritual)
    with ``sineating_partner_id`` (the other character's sheet id) and ``sineating_units``.
    All three omitted means no Sineating. Whether the plea or the ritual can happen is checked
    by the service before the pose posts.
    """

    sineating_role = serializers.ChoiceField(choices=SineatingPoseRole.choices, required=False)
    sineating_partner_id = serializers.IntegerField(required=False, allow_null=True)
    sineating_units = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class ReachFieldsMixin(serializers.Serializer):
    """The optional reach or mark a pose or journal entry carries (#5308, #5327).

    ``reach_resonance_id`` is the resonance the writing is about, in the writer's aura or not.
    Alone, on a pose, it is a reach: an endorsement of the pose pays it. With ``reach_act_id``,
    one of the writer's recorded acts, it is a mark: it pays at once and the act is marked. A
    journal entry needs both. Omitted or null means nothing is reached or marked. Whether the
    ids are valid is checked by the service before anything is written.
    """

    reach_resonance_id = serializers.IntegerField(required=False, allow_null=True)
    reach_act_id = serializers.IntegerField(required=False, allow_null=True)


class ReflectionOptionSerializer(serializers.Serializer):
    """One entry of the "Reflecting on" row."""

    kind = serializers.ChoiceField(choices=ReflectionTargetKind.choices)
    id = serializers.IntegerField()
    label = serializers.CharField()
    replaces_waiting = serializers.BooleanField()
