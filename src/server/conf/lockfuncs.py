"""

Lockfuncs

Lock functions are functions available when defining lock strings,
which in turn limits access to various game systems.

All functions defined globally in this module are assumed to be
available for use in lockstrings to determine access. See the
Evennia documentation for more info on locks.

A lock function is always called with two arguments, accessing_obj and
accessed_obj, followed by any number of arguments. All possible
arguments should be handled with *args, **kwargs. The lock function
should handle all eventual tracebacks by logging the error and
returning False.

Lock functions in this module extend (and will overload same-named)
lock functions from evennia.locks.lockfuncs.

"""

# def myfalse(accessing_obj, accessed_obj, *args, **kwargs):
#    """
#    called in lockstring with myfalse().
#    A simple logger that always returns false. Prints to stdout
#    for simplicity, should use utils.logger for real operation.
#    """
#    print "%s tried to access %s. Access denied." % (accessing_obj, accessed_obj)
#    return False


def can_play(accessing_obj, accessed_obj, *_args, **_kwargs) -> bool:
    """``can_play()``: the account may play this character right now (#4418).

    The account's own availability check (``Account.can_puppet_character``: a current
    tenure, or an active NPC loan, and not retired) is the one gate for playing a
    character, so a puppet lock built on this defers to it instead of naming an
    account id that goes stale when the NPC is lent or handed on. Anything but an
    account (a character, a script) is refused.
    """
    from typeclasses.accounts import Account  # noqa: PLC0415

    if not isinstance(accessing_obj, Account):
        return False
    allowed, _reason = accessing_obj.can_puppet_character(accessed_obj)
    return bool(allowed)
