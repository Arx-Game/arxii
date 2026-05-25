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
    NO_PRIMARY_PERSONA = "no_primary_persona"

    _SAFE_MESSAGES = {
        TECHNIQUE_NOT_COMBAT_READY: "That technique cannot be used in combat.",
        UNKNOWN_ACTION_REF: "That action is no longer available.",
        ROUND_DECLARATION_CLOSED: "The declaration window for this round is closed.",
        NO_PRIMARY_PERSONA: "Character has no primary persona; cannot record action.",
    }
    _FALLBACK = "That action could not be completed."

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGES.get(self.code, self._FALLBACK)
