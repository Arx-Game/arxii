"""Utilities for sending protocol-aware messages."""

from collections.abc import Iterable


def _iter_sessions(target, session):
    if session is not None:
        return [session]
    try:
        sessions_iter = target.sessions.all()
        return (
            list(sessions_iter)
            if isinstance(sessions_iter, Iterable)
            else sessions_iter
        )
    except AttributeError:
        return [target]


def send(
    session_or_account,
    text: str | None = None,
    *,
    payload=None,
    payload_key: str = "rich",
    session=None,
    use_text_kwarg: bool = True,
    **kwargs,
) -> None:
    """Send ``text`` and optional ``payload`` to the appropriate sessions.

    Args:
        session_or_account: Target session or account.
        text: Message text.
        payload: Structured data sent only to webclient sessions.
        payload_key: OOB command name for ``payload``. Defaults to ``"rich"``.
        session: Specific session to target.
        use_text_kwarg: Use ``text=`` keyword when calling ``msg``.
        **kwargs: Additional parameters forwarded to ``msg``.
    """
    if session_or_account is None:
        return

    if text is not None:
        text_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if session is not None:
            text_kwargs["session"] = session
        try:
            if use_text_kwarg:
                session_or_account.msg(text=text, **text_kwargs)
            else:
                session_or_account.msg(text, **text_kwargs)
        except AttributeError:
            pass

    if payload is None:
        return

    for sess in _iter_sessions(session_or_account, session):
        try:
            if "webclient" in getattr(sess, "protocol_key", ""):
                # Evennia's OOB system expects (args, kwargs). We have no
                # positional args, so provide an empty tuple.
                sess.msg(**{payload_key: ((), payload)})
        except AttributeError:
            continue
