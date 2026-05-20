from django.test import TestCase

from actions.errors import ActionDispatchError


class ActionDispatchErrorTests(TestCase):
    def test_user_message_returns_allowlisted_message(self) -> None:
        err = ActionDispatchError(ActionDispatchError.TECHNIQUE_NOT_COMBAT_READY)
        assert err.user_message == "That technique cannot be used in combat."

    def test_user_message_falls_back_for_unknown_code(self) -> None:
        err = ActionDispatchError("something internal: secret path")
        assert err.user_message == "That action could not be completed."
