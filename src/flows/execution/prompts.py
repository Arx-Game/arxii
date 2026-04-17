"""In-memory registry of pending player prompts.

Flow steps that need to wait for player input register a prompt here.
The returned ``Deferred`` fires when the player responds (via
``resolve_pending_prompt``) or when the prompt times out (via
``timeout_pending_prompt``, which fires with ``default_answer``).

Module-level dict — NOT a DB model. Prompt state is ephemeral and
process-local.
"""

from typing import Any

from twisted.internet.defer import Deferred

_pending_prompts: dict[tuple[int, str], tuple[Deferred, Any]] = {}


def register_pending_prompt(
    *,
    account_id: int,
    prompt_key: str,
    default_answer: Any = None,
) -> Deferred:
    """Create and register a new pending prompt. Returns the Deferred."""
    deferred: Deferred = Deferred()
    _pending_prompts[(account_id, prompt_key)] = (deferred, default_answer)
    return deferred


def resolve_pending_prompt(
    *,
    account_id: int,
    prompt_key: str,
    answer: Any,
) -> bool:
    """Fire the prompt's Deferred with ``answer``. No-op if key unknown.

    Returns True if a prompt was found and fired, False otherwise.
    """
    key = (account_id, prompt_key)
    entry = _pending_prompts.pop(key, None)
    if entry is None:
        return False
    deferred, _ = entry
    deferred.callback(answer)
    return True


def timeout_pending_prompt(*, account_id: int, prompt_key: str) -> bool:
    """Fire the Deferred with its registered ``default_answer``.

    Returns True if a prompt was found and fired, False otherwise.
    """
    key = (account_id, prompt_key)
    entry = _pending_prompts.pop(key, None)
    if entry is None:
        return False
    deferred, default_answer = entry
    deferred.callback(default_answer)
    return True
