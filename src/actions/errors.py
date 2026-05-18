class ActionDispatchError(Exception):
    TECHNIQUE_NOT_COMBAT_READY = "technique_not_combat_ready"
    UNKNOWN_ACTION_REF = "unknown_action_ref"
    ROUND_DECLARATION_CLOSED = "round_declaration_closed"

    _SAFE_MESSAGES = {
        TECHNIQUE_NOT_COMBAT_READY: "That technique cannot be used in combat.",
        UNKNOWN_ACTION_REF: "That action is no longer available.",
        ROUND_DECLARATION_CLOSED: "The declaration window for this round is closed.",
    }
    _FALLBACK = "That action could not be completed."

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    @property
    def user_message(self) -> str:
        return self._SAFE_MESSAGES.get(self.code, self._FALLBACK)
