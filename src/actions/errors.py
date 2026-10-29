from world.magic.exceptions import (
    ResonanceBurnInvalid,
    ResonanceBurnNeedsPull,
    ResonanceBurnUnavailable,
)


class ActionDispatchError(Exception):
    """User-safe error from action-dispatch / combat-resolution operations.

    Always raised with one of the class-level code constants. Use
    ``exc.user_message`` in API responses instead of ``str(exc)`` to avoid
    leaking internal details. Unlike EventError/ProgressionError (which raise
    the message string itself), this class raises an opaque *code* string and
    resolves it to a safe message in ``user_message`` — an intentional, cleaner
    variation, not an accidental divergence.
    """

    TECHNIQUE_NOT_COMBAT_READY = "technique_not_combat_ready"
    UNKNOWN_ACTION_REF = "unknown_action_ref"
    ROUND_DECLARATION_CLOSED = "round_declaration_closed"
    TARGET_OUT_OF_REACH = "target_out_of_reach"
    ANTI_SPAM_COOLDOWN = "anti_spam_cooldown"
    ROUND_REPEAT_BLOCKED = "round_repeat_blocked"
    PULL_ALREADY_COMMITTED = "pull_already_committed"
    PULL_INVALID = "pull_invalid"
    PARTICIPANT_MID_CROSSING = "participant_mid_crossing"
    BURN_NEEDS_PULL = "burn_needs_pull"
    BURN_UNAVAILABLE = "burn_unavailable"
    BURN_NO_FALL_RATE = "burn_no_fall_rate"
    BURN_INVALID = "burn_invalid"
    PULL_NEEDS_SOULFRAY_CONSENT = "pull_needs_soulfray_consent"
    FURY_OVER_CAP = "fury_over_cap"

    _SAFE_MESSAGES = {
        TECHNIQUE_NOT_COMBAT_READY: "That technique cannot be used in combat.",
        UNKNOWN_ACTION_REF: "That action is no longer available.",
        ROUND_DECLARATION_CLOSED: "The declaration window for this round is closed.",
        TARGET_OUT_OF_REACH: "Target is out of reach for this technique.",
        ANTI_SPAM_COOLDOWN: "You must wait before acting again.",
        ROUND_REPEAT_BLOCKED: "You have already acted this round.",
        PULL_ALREADY_COMMITTED: "You have already pulled a thread this round.",
        PULL_INVALID: "That pull cannot be applied to this action.",
        PARTICIPANT_MID_CROSSING: "A participant needs a moment; try again shortly.",
        BURN_NEEDS_PULL: ResonanceBurnNeedsPull.user_message,
        BURN_UNAVAILABLE: ResonanceBurnUnavailable.user_message,
        BURN_NO_FALL_RATE: "No Fall rate is set up for burning that resonance.",
        BURN_INVALID: ResonanceBurnInvalid.user_message,
        PULL_NEEDS_SOULFRAY_CONSENT: (
            "Accept the Soulfray risk before pulling a thread on this cast."
        ),
        FURY_OVER_CAP: "That Fury tier exceeds your provocation cap with that anchor.",
    }
    _FALLBACK = "That action could not be completed."

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGES.get(self.code, self._FALLBACK)
