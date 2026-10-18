"""The live answer panel (#4333 slice 5): what a scene GM reads and sends."""

from __future__ import annotations

from rest_framework import serializers

from world.gm.prompt_services import prompt_subject_name
from world.worship.live_services import live_panel


class _LiveAnswerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    outcome_tier_name = serializers.CharField()
    delay_text = serializers.CharField()
    answer_text = serializers.CharField()
    onlooker_line = serializers.CharField()
    used_count = serializers.IntegerField()


class _LiveMiracleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    favor_threshold = serializers.IntegerField()
    resonance_pool_cost = serializers.IntegerField()
    reason = serializers.CharField(help_text="Why it is greyed out; empty when it may be sent.")


class LivePromptSerializer(serializers.Serializer):
    """A ``BEING_ANSWER`` prompt raised by a rite in the GM's scene, as its panel reads it."""

    id = serializers.IntegerField()
    being_name = serializers.CharField()
    rite_name = serializers.CharField()
    subject_name = serializers.CharField()
    outcome_tier_name = serializers.CharField()
    answers = _LiveAnswerSerializer(many=True)
    miracles = _LiveMiracleSerializer(many=True)
    may_adapt = serializers.BooleanField()
    limit_reason = serializers.CharField(help_text="Non-empty when nothing can be sent this week.")

    def to_representation(self, prompt) -> dict:
        account = self.context["request"].user
        panel = live_panel(prompt, account=account)
        return {
            "id": prompt.pk,
            "being_name": panel.being.name,
            "rite_name": panel.rite.name,
            "subject_name": prompt_subject_name(prompt),
            "outcome_tier_name": panel.tier.name,
            "answers": [
                {
                    "id": option.answer.pk,
                    "outcome_tier_name": option.answer.outcome_tier.name,
                    "delay_text": option.answer.delay_text,
                    "answer_text": option.answer.answer_text,
                    "onlooker_line": option.answer.onlooker_line,
                    "used_count": option.used_count,
                }
                for option in panel.answers
            ],
            "miracles": [
                {
                    "id": option.miracle.pk,
                    "name": option.miracle.name,
                    "favor_threshold": option.miracle.favor_threshold,
                    "resonance_pool_cost": option.miracle.resonance_pool_cost,
                    "reason": option.reason,
                }
                for option in panel.miracles
            ],
            "may_adapt": panel.may_adapt,
            "limit_reason": panel.limit_reason,
        }


class LiveSendSerializer(serializers.Serializer):
    """The panel's send: one answer (with edited text only for a level that may
    adapt answers), or one miracle."""

    answer = serializers.IntegerField(required=False, allow_null=True)
    miracle = serializers.IntegerField(required=False, allow_null=True)
    text = serializers.CharField(required=False, allow_blank=True, default="")
