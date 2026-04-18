"""
Command for replying to pending flow prompts.
"""

from typing import ClassVar

from evennia import Command

from flows.execution.prompts import resolve_pending_prompt


class CmdPromptReply(Command):  # ty: ignore[invalid-base]
    """
    Reply to a pending flow prompt.

    Usage:
        @reply <prompt-key> <answer>

    Sends your answer to a suspended flow that is waiting for player input.
    The prompt-key identifies which prompt you are responding to.

    Example:
        @reply confirm-sacrifice yes
        @reply choose-path north
    """

    key = "@reply"
    aliases: ClassVar[list[str]] = ["reply"]
    locks = "cmd:all()"
    help_category = "Account"

    def func(self) -> None:
        """Parse args and resolve the pending prompt."""
        args = self.args.strip()
        parts = args.split(None, 1)

        if len(parts) < 2:  # noqa: PLR2004 — comparing against literal 2 is clearer than a named constant here
            self.caller.msg("Usage: @reply <prompt-key> <answer>")
            return

        prompt_key, answer = parts[0], parts[1]

        found = resolve_pending_prompt(
            account_id=self.account.pk,
            prompt_key=prompt_key,
            answer=answer,
        )

        if found:
            self.caller.msg("Reply sent.")
        else:
            self.caller.msg("No pending prompt with that key.")
